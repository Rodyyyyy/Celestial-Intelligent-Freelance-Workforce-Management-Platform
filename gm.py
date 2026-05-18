"""routes/gm.py — General Manager: project lifecycle, team assignment, RL feedback."""
from flask import Blueprint, request, session
import json, datetime
from database import query, execute, push_notification, log_activity
from auth import login_required
from rl_engine import division_rl, skill_matcher
from utils import ok, err, not_found
from utils.notify import emit_realtime

gm_bp = Blueprint('gm', __name__)
GM    = ['general_manager']


@gm_bp.route('/gm/dashboard')
@login_required(roles=GM)
def gm_dashboard():
    projects = query(
        "SELECT p.*,u.full_name as client_name FROM projects p "
        "JOIN users u ON p.client_id=u.id ORDER BY p.updated_at DESC"
    )
    recent_activity = query(
        "SELECT a.*,u.full_name,u.role FROM activity_log a JOIN users u ON a.user_id=u.id "
        "ORDER BY a.created_at DESC LIMIT 20"
    )
    phase_stats = query(
        "SELECT status, COUNT(*) as count FROM phases GROUP BY status"
    )
    total_revenue = query(
        "SELECT SUM(paid_deposit+paid_remaining) as total FROM projects WHERE status IN ('completed','delivered')",
        one=True
    )
    pipeline_value = query(
        "SELECT SUM(total_cost) as total FROM projects WHERE status='in_progress'",
        one=True
    )

    return ok({
        'projects':       projects,
        'recent_activity': recent_activity,
        'phase_stats':    phase_stats,
        'stats': {
            'total_projects':  len(projects),
            'in_progress':     sum(1 for p in projects if p['status'] == 'in_progress'),
            'completed':       sum(1 for p in projects if p['status'] in ('completed', 'delivered')),
            'total_revenue':   round(total_revenue['total'] or 0, 2) if total_revenue else 0,
            'pipeline_value':  round(pipeline_value['total'] or 0, 2) if pipeline_value else 0,
        }
    })


@gm_bp.route('/gm/projects', methods=['POST'])
@login_required(roles=GM)
def create_project():
    data  = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return err('Project title is required')

    pid = execute(
        "INSERT INTO projects (title,description,client_id,gm_id,status,required_skills,num_freelancers,deadline) "
        "VALUES (?,?,?,?,'proposal_accepted',?,?,?)",
        (title, data.get('description',''), data.get('client_id'),
         session['user_id'], data.get('skills',''),
         data.get('num_freelancers', 1), data.get('deadline'))
    )
    log_activity(session['user_id'], 'create_project', 'project', pid)
    return ok({'project_id': pid}, 'Project created')


@gm_bp.route('/gm/projects/<int:pid>', methods=['DELETE'])
@login_required(roles=GM)
def delete_project(pid):
    project = query("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not project:
        return not_found()
    execute("DELETE FROM projects WHERE id=?", (pid,))
    log_activity(session['user_id'], 'delete_project', 'project', pid)
    return ok(message='Project deleted')


@gm_bp.route('/gm/projects/<int:pid>', methods=['PUT'])
@login_required(roles=GM)
def update_project(pid):
    data    = request.get_json(silent=True) or {}
    project = query("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not project:
        return not_found()

    fields, params = [], []
    for f in ['title','description','required_skills','num_freelancers','deadline','total_cost']:
        if f in data:
            fields.append(f"{f}=?"); params.append(data[f])
    if not fields:
        return err('Nothing to update')
    fields.append("updated_at=?"); params.append(datetime.datetime.utcnow())
    params.append(pid)
    execute(f"UPDATE projects SET {','.join(fields)} WHERE id=?", params)
    return ok(message='Project updated')

    for m in members:
        emit_realtime(
            'project_update',
            {'project_id': pid, 'status': new_status, 'updated_by': session['username']},
            user_id=m['user_id']
    )

@gm_bp.route('/gm/projects/<int:pid>/setup-division', methods=['POST'])
@login_required(roles=GM)
def setup_division(pid):
    data    = request.get_json(silent=True) or {}
    method  = data.get('method', 'manual')
    project = query("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not project:
        return not_found()

    execute("UPDATE projects SET division_method=? WHERE id=?", (method, pid))

    if method == 'auto':
        phases = division_rl.suggest_phases(project)
        for ph in phases:
            execute(
                "INSERT INTO phases (project_id,name,description,deadline,order_num) VALUES (?,?,?,?,?)",
                (pid, ph['name'], ph['description'], ph['deadline'], ph['order_num'])
            )
        log_activity(session['user_id'], 'auto_division', 'project', pid)
        return ok({'phases': phases}, 'Auto-division applied')

    # Manual: accept phases from body if provided
    manual_phases = data.get('phases', [])
    for i, ph in enumerate(manual_phases):
        execute(
            "INSERT INTO phases (project_id,name,description,deadline,order_num) VALUES (?,?,?,?,?)",
            (pid, ph.get('name', f'Phase {i+1}'), ph.get('description',''), ph.get('deadline'), i+1)
        )
    log_activity(session['user_id'], 'manual_division', 'project', pid)
    return ok(message='Division method set')


@gm_bp.route('/gm/projects/<int:pid>/rl-feedback', methods=['POST'])
@login_required(roles=GM)
def rl_feedback(pid):
    data   = request.get_json(silent=True) or {}
    rating = data.get('rating')
    if rating not in (-1, 0, 1):
        return err('Rating must be -1, 0, or 1')
    phases = query("SELECT * FROM phases WHERE project_id=?", (pid,))
    division_rl.record_feedback(pid, json.dumps(phases), rating)
    execute("UPDATE projects SET auto_div_rating=? WHERE id=?", (str(rating), pid))
    return ok(message='Feedback recorded — model will improve!')


@gm_bp.route('/gm/projects/<int:pid>/assign-team', methods=['POST'])
@login_required(roles=GM)
def assign_team(pid):
    data      = request.get_json(silent=True) or {}
    leader_id = data.get('team_leader')
    member_ids = data.get('members', [])
    project   = query("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not project:
        return not_found()

    # Skill alerts
    required  = project.get('required_skills', '')
    all_ids   = ([leader_id] if leader_id else []) + list(member_ids)
    alerts    = []
    for uid in all_ids:
        user = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
        if user:
            info = skill_matcher.score_freelancer(user, [s.strip() for s in required.split(',') if s.strip()])
            if info.get('alert'):
                alerts.append(info['alert'])

    # Proceed with assignment
    if leader_id:
        execute("INSERT OR IGNORE INTO team_members (project_id,user_id,role_in_team) VALUES (?,?,'team_leader')", (pid, leader_id))
        execute("UPDATE projects SET team_leader_id=? WHERE id=?", (leader_id, pid))
        push_notification(leader_id, 'Assigned as Team Leader',
                          f'You have been assigned as team leader for project #{pid}', 'success')

    for mid in member_ids:
        execute("INSERT OR IGNORE INTO team_members (project_id,user_id,role_in_team) VALUES (?,?,'team_member')", (pid, mid))
        push_notification(mid, 'Added to Project Team',
                          f'You have been added to project #{pid}', 'info')

    # Activate first phase
    first_phase = query("SELECT id FROM phases WHERE project_id=? ORDER BY order_num LIMIT 1", (pid,), one=True)
    if first_phase:
        execute("UPDATE phases SET status='active' WHERE id=?", (first_phase['id'],))

    execute("UPDATE projects SET status='in_progress', updated_at=? WHERE id=?",
            (datetime.datetime.utcnow(), pid))
    log_activity(session['user_id'], 'assign_team', 'project', pid)

    return ok({'alerts': alerts}, 'Team assigned and project started')


@gm_bp.route('/gm/phases/<int:phase_id>/accept', methods=['POST'])
@login_required(roles=GM)
def accept_phase(phase_id):
    phase = query("SELECT * FROM phases WHERE id=?", (phase_id,), one=True)
    if not phase:
        return not_found()
    execute("UPDATE phases SET status='completed' WHERE id=?", (phase_id,))

    # Activate next phase
    next_ph = query(
        "SELECT id FROM phases WHERE project_id=? AND order_num>? AND status='pending' ORDER BY order_num LIMIT 1",
        (phase['project_id'], phase['order_num']), one=True
    )
    if next_ph:
        execute("UPDATE phases SET status='active' WHERE id=?", (next_ph['id'],))
    else:
        # All phases done
        execute("UPDATE projects SET status='completed', updated_at=? WHERE id=?",
                (datetime.datetime.utcnow(), phase['project_id']))
        project = query("SELECT * FROM projects WHERE id=?", (phase['project_id'],), one=True)
        if project and project['client_id']:
            push_notification(project['client_id'], 'Project Completed!',
                              f'Project "{project["title"]}" has been completed. Please review and accept.', 'success')

    log_activity(session['user_id'], 'accept_phase', 'phase', phase_id)
    # Get all team members of the project
    members = query("SELECT user_id FROM team_members WHERE project_id=?", (phase['project_id'],))
    for m in members:
        emit_realtime(
            'phase_completed',
            {'phase_id': phase_id, 'phase_name': phase['name'], 'project_id': phase['project_id']},
            user_id=m['user_id']
        )

@gm_bp.route('/gm/phases/<int:phase_id>/reject', methods=['POST'])
@login_required(roles=GM)
def reject_phase(phase_id):
    data = request.get_json(silent=True) or {}
    execute("UPDATE phases SET status='rejected' WHERE id=?", (phase_id,))
    log_activity(session['user_id'], 'reject_phase', 'phase', phase_id)
    return ok(message='Phase rejected — team will revise')


@gm_bp.route('/gm/projects/<int:pid>/rate-team', methods=['POST'])
@login_required(roles=GM)
def rate_team(pid):
    data    = request.get_json(silent=True) or {}
    ratings = data.get('ratings', [])
    gm_id   = session['user_id']

    for r in ratings:
        uid    = r.get('user_id')
        rating = r.get('rating')
        comment = r.get('comment', '')
        if uid and rating is not None:
            execute("INSERT INTO ratings (rated_by,rated_user_id,project_id,rating,comment) VALUES (?,?,?,?,?)",
                    (gm_id, uid, pid, rating, comment))
            # Update user performance (rolling avg)
            all_ratings = query("SELECT AVG(rating) as avg FROM ratings WHERE rated_user_id=?", (uid,), one=True)
            avg = all_ratings['avg'] if all_ratings and all_ratings['avg'] else 0
            execute("UPDATE users SET performance=? WHERE id=?", (round(avg, 2), uid))
            # Award training center if top performer
            if rating >= 4.0:
                execute("UPDATE users SET training_centers=training_centers+1 WHERE id=?", (uid,))
                push_notification(uid, 'Training Center Awarded!',
                                  'Great performance! You earned a free training center.', 'success')

    log_activity(gm_id, 'rate_team', 'project', pid)
    return ok(message='Ratings submitted')


@gm_bp.route('/gm/available-freelancers')
@login_required(roles=GM)
def available_freelancers():
    pid = request.args.get('project_id')
    skills_filter = request.args.get('skills', '')

    freelancers = query(
        "SELECT id,full_name,skills,performance,training_centers FROM users "
        "WHERE role IN ('freelancer','team_leader','team_member') AND status='active'"
    )

    if pid:
        # Exclude already assigned
        assigned = query("SELECT user_id FROM team_members WHERE project_id=?", (pid,))
        assigned_ids = {r['user_id'] for r in assigned}
        freelancers = [f for f in freelancers if f['id'] not in assigned_ids]

    if skills_filter:
        freelancers = skill_matcher.rank_freelancers(freelancers, skills_filter)

    return ok(freelancers)


@gm_bp.route('/gm/clients')
@login_required(roles=GM)
def list_clients():
    clients = query("SELECT id,full_name,email FROM users WHERE role='client' AND status='active' ORDER BY full_name")
    return ok(clients)


@gm_bp.route('/gm/projects/<int:pid>/phases', methods=['POST'])
@login_required(roles=GM)
def add_phase(pid):
    data = request.get_json(silent=True) or {}
    last = query("SELECT MAX(order_num) as m FROM phases WHERE project_id=?", (pid,), one=True)
    order = (last['m'] or 0) + 1
    ph_id = execute(
        "INSERT INTO phases (project_id,name,description,deadline,order_num) VALUES (?,?,?,?,?)",
        (pid, data.get('name', f'Phase {order}'), data.get('description',''), data.get('deadline'), order)
    )
    return ok({'phase_id': ph_id}, 'Phase added')


@gm_bp.route('/gm/phases')
@login_required(roles=GM)
def all_phases():
    """Phases awaiting GM review."""
    phases = query(
        "SELECT ph.*,pr.title as project_title FROM phases ph "
        "JOIN projects pr ON ph.project_id=pr.id "
        "WHERE ph.status='submitted_for_review' ORDER BY ph.created_at"
    )
    return ok(phases)
