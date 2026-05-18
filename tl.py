"""routes/tl.py — Team Leader endpoints."""
from flask import Blueprint, request, session
import datetime
from database import query, execute, push_notification, log_activity
from auth import login_required
from utils import ok, err, not_found
from utils.notify import emit_realtime

tl_bp = Blueprint('tl', __name__)
TL = ['team_leader']


@tl_bp.route('/tl/dashboard')
@login_required(roles=TL)
def tl_dashboard():
    uid = session['user_id']
    projects = query(
        "SELECT p.*,u.full_name as client_name FROM projects p "
        "JOIN team_members tm ON p.id=tm.project_id "
        "JOIN users u ON p.client_id=u.id "
        "WHERE tm.user_id=? AND tm.role_in_team='team_leader'", (uid,)
    )
    all_tasks = query(
        "SELECT t.* FROM tasks t JOIN phases ph ON t.phase_id=ph.id "
        "JOIN team_members tm ON ph.project_id=tm.project_id WHERE tm.user_id=?", (uid,)
    )
    pending_reviews = query(
        "SELECT t.*,u.full_name as freelancer_name,ph.name as phase_name,pr.title as project_title "
        "FROM tasks t JOIN users u ON t.freelancer_id=u.id "
        "JOIN phases ph ON t.phase_id=ph.id JOIN projects pr ON ph.project_id=pr.id "
        "JOIN team_members tm ON pr.id=tm.project_id "
        "WHERE tm.user_id=? AND tm.role_in_team='team_leader' AND t.status='submitted'", (uid,)
    )
    submitted_phases = query(
        "SELECT ph.*,pr.title as project_title FROM phases ph "
        "JOIN projects pr ON ph.project_id=pr.id "
        "JOIN team_members tm ON pr.id=tm.project_id "
        "WHERE tm.user_id=? AND tm.role_in_team='team_leader' AND ph.status='submitted_for_review'", (uid,)
    )
    return ok({
        'projects': projects,
        'pending_reviews': pending_reviews,
        'submitted_phases': submitted_phases,
        'stats': {
            'total_projects': len(projects),
            'active_projects': sum(1 for p in projects if p['status'] == 'in_progress'),
            'total_tasks': len(all_tasks),
            'pending_review': len(pending_reviews),
        }
    })


@tl_bp.route('/tl/projects/<int:pid>/active-phase')
@login_required(roles=TL)
def active_phase(pid):
    uid = session['user_id']
    assigned = query("SELECT id FROM team_members WHERE project_id=? AND user_id=? AND role_in_team='team_leader'",
                     (pid, uid), one=True)
    if not assigned:
        return err('Not assigned to this project', 403)

    phase = query("SELECT * FROM phases WHERE project_id=? AND status='active'", (pid,), one=True)
    if not phase:
        return ok({'phase': None, 'tasks': [], 'members': []})

    tasks = query(
        "SELECT t.*,u.full_name,u.skills FROM tasks t JOIN users u ON t.freelancer_id=u.id WHERE t.phase_id=?",
        (phase['id'],)
    )
    members = query(
        "SELECT tm.user_id,u.full_name,u.skills,u.performance FROM team_members tm "
        "JOIN users u ON tm.user_id=u.id WHERE tm.project_id=? AND tm.role_in_team='team_member'", (pid,)
    )
    return ok({'phase': phase, 'tasks': tasks, 'members': members})


@tl_bp.route('/tl/tasks', methods=['POST'])
@login_required(roles=TL)
def create_task():
    data = request.get_json(silent=True) or {}
    required = ['phase_id', 'freelancer_id', 'description']
    for f in required:
        if not data.get(f):
            return err(f'{f} is required')

    tid = execute(
        "INSERT INTO tasks (phase_id,freelancer_id,title,description,deadline) VALUES (?,?,?,?,?)",
        (data['phase_id'], data['freelancer_id'],
         data.get('title', 'Task'), data['description'], data.get('deadline'))
    )
    push_notification(data['freelancer_id'], 'New Task Assigned',
                      f'You have been assigned a new task.', 'info')
    log_activity(session['user_id'], 'create_task', 'task', tid)

    # Real‑time notification to freelancer
    emit_realtime(
        'notification',
        {
            'type': 'task_assigned',
            'title': 'New Task Assigned',
            'message': f'Task "{data.get("title", "Task")}" has been assigned to you.',
            'task_id': tid,
            'deadline': data.get('deadline')
        },
        user_id=data['freelancer_id']
    )
    emit_realtime('dashboard_update', {'entity': 'tasks'}, user_id=data['freelancer_id'])

    return ok({'task_id': tid}, 'Task created')


@tl_bp.route('/tl/tasks/<int:tid>/review', methods=['POST'])
@login_required(roles=TL)
def review_task(tid):
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in ('accept', 'reject'):
        return err('action must be accept or reject')

    task = query("SELECT * FROM tasks WHERE id=?", (tid,), one=True)
    if not task:
        return not_found()

    new_status = 'accepted' if action == 'accept' else 'rejected'
    ts = datetime.datetime.utcnow()
    execute("UPDATE tasks SET status=?, tl_comment=?, completed_at=? WHERE id=?",
            (new_status, data.get('comment', ''), ts if action == 'accept' else None, tid))
    push_notification(task['freelancer_id'], f'Task {new_status.title()}',
                      data.get('comment', f'Your task has been {new_status}.'), 'success' if action == 'accept' else 'warning')
    log_activity(session['user_id'], f'task_{action}', 'task', tid)

    # Real‑time notification to freelancer
    emit_realtime(
        'notification',
        {
            'type': 'task_reviewed',
            'title': f'Task {new_status.title()}',
            'message': f'Your task has been {new_status}.',
            'task_id': tid,
        },
        user_id=task['freelancer_id']
    )
    emit_realtime('dashboard_update', {'entity': 'tasks'}, user_id=task['freelancer_id'])

    return ok(message=f'Task {new_status}')


@tl_bp.route('/tl/phases/<int:phase_id>/submit', methods=['POST'])
@login_required(roles=TL)
def submit_phase(phase_id):
    phase = query("SELECT * FROM phases WHERE id=?", (phase_id,), one=True)
    if not phase:
        return not_found()
    # Ensure all tasks are accepted before submission
    unfinished = query("SELECT id FROM tasks WHERE phase_id=? AND status NOT IN ('accepted','rejected')", (phase_id,))
    if unfinished:
        return err(f'{len(unfinished)} task(s) are still pending review')

    execute("UPDATE phases SET status='submitted_for_review' WHERE id=?", (phase_id,))

    # Notify GMs
    gms = query("SELECT id FROM users WHERE role='general_manager' AND status='active'")
    for gm in gms:
        push_notification(gm['id'], 'Phase Ready for Review',
                          f'Phase "{phase["name"]}" has been submitted for review.', 'info')
        emit_realtime(
            'notification',
            {
                'type': 'phase_submitted',
                'title': 'Phase Ready for Review',
                'message': f'Phase "{phase["name"]}" has been submitted for review.',
                'phase_id': phase_id,
                'project_id': phase['project_id']
            },
            user_id=gm['id']
        )
    log_activity(session['user_id'], 'submit_phase', 'phase', phase_id)
    return ok(message='Phase submitted for GM review')


@tl_bp.route('/tl/freelancers/<int:fid>/rate', methods=['POST'])
@login_required(roles=TL)
def rate_freelancer(fid):
    data = request.get_json(silent=True) or {}
    pid = data.get('project_id')
    rating = data.get('rating')
    if rating is None:
        return err('Rating required')
    execute("INSERT INTO ratings (rated_by,rated_user_id,project_id,rating,comment) VALUES (?,?,?,?,?)",
            (session['user_id'], fid, pid, float(rating), data.get('comment', '')))
    all_r = query("SELECT AVG(rating) as avg FROM ratings WHERE rated_user_id=?", (fid,), one=True)
    avg = all_r['avg'] if all_r and all_r['avg'] else 0
    execute("UPDATE users SET performance=? WHERE id=?", (round(avg, 2), fid))
    return ok(message='Rating submitted')