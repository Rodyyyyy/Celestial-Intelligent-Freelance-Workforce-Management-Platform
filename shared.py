"""routes/shared.py — Endpoints accessible by multiple roles."""
from flask import Blueprint, session
from database import query, execute
from auth import login_required
from utils import ok, err

# Define the blueprint FIRST
shared_bp = Blueprint('shared', __name__)


@shared_bp.route('/dashboard/stats')
@login_required()
def global_stats():
    """Return high-level stats available to any authenticated user."""
    uid = session['user_id']
    role = session['role']

    stats = {}

    if role == 'client':
        projects = query("SELECT status FROM projects WHERE client_id=?", (uid,))
        stats = {
            'total_projects': len(projects),
            'in_progress': sum(1 for p in projects if p['status'] == 'in_progress'),
            'completed': sum(1 for p in projects if p['status'] in ('completed', 'delivered')),
            'pending_proposals': len(query(
                "SELECT id FROM proposals p JOIN projects pr ON p.project_id=pr.id WHERE pr.client_id=? AND p.status='pending'",
                (uid,)))
        }

    elif role in ('team_leader', 'team_member', 'freelancer'):
        tasks = query(
            "SELECT t.status FROM tasks t "
            "JOIN phases ph ON t.phase_id=ph.id "
            "JOIN projects pr ON ph.project_id=pr.id "
            "JOIN team_members tm ON tm.project_id=pr.id "
            "WHERE tm.user_id=?", (uid,)
        )
        stats = {
            'total_tasks': len(tasks),
            'pending': sum(1 for t in tasks if t['status'] == 'pending'),
            'submitted': sum(1 for t in tasks if t['status'] == 'submitted'),
            'accepted': sum(1 for t in tasks if t['status'] == 'accepted'),
        }

    elif role == 'general_manager':
        projects = query("SELECT status FROM projects")
        stats = {
            'total_projects': len(projects),
            'in_progress': sum(1 for p in projects if p['status'] == 'in_progress'),
            'completed': sum(1 for p in projects if p['status'] in ('completed', 'delivered')),
            'requested': sum(1 for p in projects if p['status'] == 'requested'),
        }

    return ok(stats)


@shared_bp.route('/activity')
@login_required()
def activity_feed():
    uid = session['user_id']
    role = session['role']

    if role == 'admin':
        rows = query(
            "SELECT a.*, u.full_name, u.role FROM activity_log a "
            "JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC LIMIT 50"
        )
    else:
        rows = query(
            "SELECT a.*, u.full_name, u.role FROM activity_log a "
            "JOIN users u ON a.user_id=u.id "
            "WHERE a.user_id=? ORDER BY a.created_at DESC LIMIT 30",
            (uid,)
        )
    return ok(rows)


# Test endpoint for real-time notifications (add this at the bottom)
@shared_bp.route('/test-notify')
def test_notify():
    from utils.notify import emit_realtime
    emit_realtime('test', {'message': 'Hello from WebSocket!'}, broadcast=True)
    return ok({'sent': True})