"""routes/pm.py — Proposal Manager endpoints."""
from flask import Blueprint, request, session
import datetime  # <-- ADD THIS IMPORT
from database import query, execute, push_notification, log_activity
from auth import login_required
from utils import ok, err, not_found
from utils.notify import emit_realtime

pm_bp = Blueprint('pm', __name__)
PM    = ['proposal_manager']


@pm_bp.route('/pm/dashboard')
@login_required(roles=PM)
def pm_dashboard():
    uid       = session['user_id']
    proposals = query(
        "SELECT prop.*,pr.title,pr.client_id,u.full_name as client_name "
        "FROM proposals prop JOIN projects pr ON prop.project_id=pr.id "
        "JOIN users u ON pr.client_id=u.id ORDER BY prop.sent_at DESC"
    )
    incoming  = query(
        "SELECT p.*,u.full_name as client_name FROM projects p "
        "JOIN users u ON p.client_id=u.id WHERE p.status='requested' ORDER BY p.created_at DESC"
    )

    total_sent     = len(proposals)
    total_accepted = sum(1 for p in proposals if p['status'] == 'accepted')
    total_rejected = sum(1 for p in proposals if p['status'] == 'rejected')
    acceptance_rate = round(total_accepted / total_sent * 100) if total_sent else 0
    total_value     = sum(p['cost'] or 0 for p in proposals if p['status'] == 'accepted')

    return ok({
        'incoming':   incoming,
        'proposals':  proposals,
        'stats': {
            'total_sent':      total_sent,
            'total_accepted':  total_accepted,
            'total_rejected':  total_rejected,
            'acceptance_rate': acceptance_rate,
            'total_value':     round(total_value, 2),
            'pending_count':   len(incoming),
        }
    })


@pm_bp.route('/pm/proposals', methods=['POST'])
@login_required(roles=PM)
def send_proposal():
    data    = request.get_json(silent=True) or {}
    pid     = data.get('project_id')
    content = (data.get('content') or '').strip()
    cost    = data.get('cost')

    if not pid or not content or cost is None:
        return err('project_id, content, and cost are required')
    try:
        cost = float(cost)
        if cost <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return err('Cost must be a positive number')

    project = query("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not project:
        return not_found('Project not found')

    # Check for existing pending proposal
    existing = query("SELECT id FROM proposals WHERE project_id=? AND status='pending'", (pid,), one=True)
    if existing:
        return err('A pending proposal already exists for this project')

    prop_id = execute(
        "INSERT INTO proposals (project_id,pm_id,content,cost) VALUES (?,?,?,?)",
        (pid, session['user_id'], content, cost)
    )
    execute("UPDATE projects SET status='proposal_sent' WHERE id=?", (pid,))
    log_activity(session['user_id'], 'send_proposal', 'proposal', prop_id)

    # Notify client via database (persistent)
    push_notification(project['client_id'], 'New Proposal Received',
                      f'A proposal has been sent for your project: {project["title"]}', 'info')

    # ========== REAL‑TIME NOTIFICATIONS (MOVED BEFORE RETURN) ==========
    # Notify client in real time
    emit_realtime(
        'notification',
        {
            'type': 'new_proposal',
            'title': 'New Proposal Received',
            'message': f'A proposal for "{project["title"]}" has been sent.',
            'project_id': pid,
            'proposal_id': prop_id,
            'cost': cost,
            'timestamp': datetime.datetime.utcnow().isoformat()
        },
        user_id=project['client_id']
    )
    # Also trigger dashboard update for client
    emit_realtime('dashboard_update', {'entity': 'proposals'}, user_id=project['client_id'])
    # ===================================================================

    return ok({'proposal_id': prop_id}, 'Proposal sent')


@pm_bp.route('/pm/proposals/<int:prop_id>', methods=['PUT'])
@login_required(roles=PM)
def update_proposal(prop_id):
    data = request.get_json(silent=True) or {}
    prop = query("SELECT * FROM proposals WHERE id=?", (prop_id,), one=True)
    if not prop:
        return not_found()
    if prop['status'] != 'pending':
        return err('Cannot edit a responded proposal')

    fields, params = [], []
    if 'content' in data:
        fields.append("content=?"); params.append(data['content'])
    if 'cost' in data:
        fields.append("cost=?"); params.append(float(data['cost']))
    if not fields:
        return err('Nothing to update')
    params.append(prop_id)
    execute(f"UPDATE proposals SET {','.join(fields)} WHERE id=?", params)
    return ok(message='Proposal updated')


@pm_bp.route('/pm/proposals')
@login_required(roles=PM)
def list_proposals():
    proposals = query(
        "SELECT prop.*,pr.title,u.full_name as client_name "
        "FROM proposals prop JOIN projects pr ON prop.project_id=pr.id "
        "JOIN users u ON pr.client_id=u.id ORDER BY prop.sent_at DESC"
    )
    return ok(proposals)