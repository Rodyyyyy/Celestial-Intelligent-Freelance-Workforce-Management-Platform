"""routes/member.py — Team Member endpoints."""
from flask import Blueprint, request, session
import datetime
from database import query, execute, push_notification, log_activity
from auth import login_required
from utils import ok, err, not_found

member_bp = Blueprint('member', __name__)
MEMBER    = ['team_member']


@member_bp.route('/member/dashboard')
@login_required(roles=MEMBER)
def member_dashboard():
    uid   = session['user_id']
    tasks = query(
        "SELECT t.*,ph.name as phase_name,pr.title as project_title,pr.id as project_id "
        "FROM tasks t JOIN phases ph ON t.phase_id=ph.id JOIN projects pr ON ph.project_id=pr.id "
        "WHERE t.freelancer_id=? ORDER BY t.created_at DESC", (uid,)
    )
    return ok({
        'tasks': tasks,
        'stats': {
            'total':     len(tasks),
            'pending':   sum(1 for t in tasks if t['status'] == 'pending'),
            'submitted': sum(1 for t in tasks if t['status'] == 'submitted'),
            'accepted':  sum(1 for t in tasks if t['status'] == 'accepted'),
            'rejected':  sum(1 for t in tasks if t['status'] == 'rejected'),
        }
    })


@member_bp.route('/member/tasks/<int:tid>/submit', methods=['POST'])
@login_required(roles=MEMBER)
def submit_task(tid):
    uid  = session['user_id']
    data = request.get_json(silent=True) or {}
    task = query("SELECT * FROM tasks WHERE id=? AND freelancer_id=?", (tid, uid), one=True)
    if not task:
        return not_found('Task not found')
    if task['status'] not in ('pending', 'rejected', 'in_progress'):
        return err('Task cannot be submitted in its current state')

    submission = (data.get('submission') or '').strip()
    if not submission:
        return err('Submission content is required')

    execute("UPDATE tasks SET status='submitted', submission=?, submitted_at=? WHERE id=?",
            (submission, datetime.datetime.utcnow(), tid))
    log_activity(uid, 'submit_task', 'task', tid)

    # Notify TL
    phase = query("SELECT ph.*,pr.team_leader_id FROM phases ph JOIN projects pr ON ph.project_id=pr.id WHERE ph.id=?",
                  (task['phase_id'],), one=True)
    if phase and phase['team_leader_id']:
        push_notification(phase['team_leader_id'], 'Task Submitted for Review',
                          f'A team member submitted their task for review.', 'info')
    return ok(message='Task submitted')


@member_bp.route('/member/tasks/<int:tid>/start', methods=['POST'])
@login_required(roles=MEMBER)
def start_task(tid):
    uid  = session['user_id']
    task = query("SELECT * FROM tasks WHERE id=? AND freelancer_id=?", (tid, uid), one=True)
    if not task:
        return not_found()
    execute("UPDATE tasks SET status='in_progress' WHERE id=?", (tid,))
    return ok(message='Task started')
