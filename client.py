"""routes/client.py — Client project requests, proposals, payments, tracking."""
from flask import Blueprint, request, session
import datetime  # <-- ADD THIS IMPORT
from database import query, execute, push_notification, log_activity
from auth import login_required
from utils import ok, err, not_found
from utils.notify import emit_realtime

client_bp = Blueprint('client', __name__)
CLIENT = ['client']


def _owned(project_id, client_id):
    return query("SELECT id FROM projects WHERE id=? AND client_id=?", (project_id, client_id), one=True)


@client_bp.route('/client/dashboard')
@login_required(roles=CLIENT)
def client_dashboard():
    uid      = session['user_id']
    projects = query(
        "SELECT p.*,u.full_name as gm_name FROM projects p "
        "LEFT JOIN users u ON p.gm_id=u.id WHERE p.client_id=? ORDER BY p.created_at DESC", (uid,)
    )
    proposals = query(
        "SELECT prop.*,pr.title FROM proposals prop "
        "JOIN projects pr ON prop.project_id=pr.id WHERE pr.client_id=? ORDER BY prop.sent_at DESC", (uid,)
    )
    total_spent = sum((p['paid_deposit'] or 0) + (p['paid_remaining'] or 0) for p in projects)
    payments = query(
        "SELECT py.*,pr.title as project_title FROM payments py "
        "JOIN projects pr ON py.project_id=pr.id WHERE py.payer_id=? ORDER BY py.paid_at DESC LIMIT 20",
        (uid,)
    )
    return ok({
        'projects':    projects,
        'proposals':   proposals,
        'payments':    payments,
        'stats': {
            'total_projects':    len(projects),
            'in_progress':       sum(1 for p in projects if p['status'] == 'in_progress'),
            'completed':         sum(1 for p in projects if p['status'] in ('completed','delivered')),
            'pending_proposals': sum(1 for p in proposals if p['status'] == 'pending'),
            'total_spent':       round(total_spent, 2),
        }
    })


@client_bp.route('/client/projects', methods=['POST'])
@login_required(roles=CLIENT)
def request_project():
    data  = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    desc  = (data.get('description') or '').strip()
    if not title:
        return err('Project title is required')

    pid = execute(
        "INSERT INTO projects (title,description,client_id,status) VALUES (?,?,?,'requested')",
        (title, desc, session['user_id'])
    )
    log_activity(session['user_id'], 'request_project', 'project', pid)

    # Notify proposal managers
    pms = query("SELECT id FROM users WHERE role='proposal_manager' AND status='active'")
    for pm in pms:
        push_notification(pm['id'], 'New Project Request',
                          f'Client requested: {title}', 'info')
        # Real‑time notification to each proposal manager
        emit_realtime(
            'notification',
            {
                'type': 'new_project_request',
                'title': 'New Project Request',
                'message': f'Client requested: {title}',
                'project_id': pid,
                'client_id': session['user_id'],
                'timestamp': datetime.datetime.utcnow().isoformat()
            },
            user_id=pm['id']
        )
        emit_realtime('dashboard_update', {'entity': 'incoming_projects'}, user_id=pm['id'])

    return ok({'project_id': pid}, 'Project request submitted')


@client_bp.route('/client/projects/<int:pid>')
@login_required(roles=CLIENT)
def project_detail(pid):
    if not _owned(pid, session['user_id']):
        return not_found('Project not found')

    project  = query("SELECT p.*,u.full_name as client_name FROM projects p JOIN users u ON p.client_id=u.id WHERE p.id=?", (pid,), one=True)
    phases   = query("SELECT * FROM phases WHERE project_id=? ORDER BY order_num", (pid,))
    comments = query(
        "SELECT c.*,u.full_name,u.role FROM comments c JOIN users u ON c.author_id=u.id "
        "WHERE c.project_id=? ORDER BY c.created_at", (pid,)
    )
    # Enrich phases with task progress
    for ph in phases:
        tasks       = query("SELECT status FROM tasks WHERE phase_id=?", (ph['id'],))
        ph['total_tasks']    = len(tasks)
        ph['accepted_tasks'] = sum(1 for t in tasks if t['status'] == 'accepted')
        ph['progress']       = round(ph['accepted_tasks'] / ph['total_tasks'] * 100) if tasks else 0

    return ok({'project': project, 'phases': phases, 'comments': comments})


@client_bp.route('/client/proposals/<int:prop_id>/accept', methods=['POST'])
@login_required(roles=CLIENT)
def accept_proposal(prop_id):
    uid  = session['user_id']
    prop = query("SELECT prop.*,pr.client_id,pr.title FROM proposals prop JOIN projects pr ON prop.project_id=pr.id WHERE prop.id=?",
                 (prop_id,), one=True)
    if not prop or prop['client_id'] != uid:
        return not_found('Proposal not found')
    if prop['status'] != 'pending':
        return err('Proposal already responded to')

    deposit = round(prop['cost'] * 0.30, 2)
    execute("UPDATE proposals SET status='accepted', responded_at=? WHERE id=?",
            (datetime.datetime.utcnow(), prop_id))
    execute("UPDATE projects SET status='proposal_accepted', total_cost=?, paid_deposit=? WHERE id=?",
            (prop['cost'], deposit, prop['project_id']))
    execute("INSERT INTO payments (project_id,payer_id,amount,payment_type,description) VALUES (?,?,?,'deposit','30% deposit on proposal acceptance')",
            (prop['project_id'], uid, deposit))

    log_activity(uid, 'accept_proposal', 'proposal', prop_id)

    # Notify GMs (database + real-time)
    gms = query("SELECT id FROM users WHERE role='general_manager' AND status='active'")
    for gm in gms:
        push_notification(gm['id'], 'Proposal Accepted',
                          f'Client accepted proposal. Deposit ${deposit} received.', 'success')
        emit_realtime(
            'notification',
            {
                'type': 'proposal_accepted',
                'title': 'Proposal Accepted',
                'message': f'Client accepted the proposal for "{prop["title"]}". Deposit ${deposit} received.',
                'project_id': prop['project_id'],
                'proposal_id': prop_id,
                'deposit': deposit
            },
            user_id=gm['id']
        )
        emit_realtime('dashboard_update', {'entity': 'projects'}, user_id=gm['id'])

    # Also notify the proposal manager who sent the proposal
    pm_id = query("SELECT pm_id FROM proposals WHERE id=?", (prop_id,), one=True)
    if pm_id and pm_id['pm_id']:
        emit_realtime(
            'notification',
            {
                'type': 'proposal_accepted',
                'title': 'Your Proposal Was Accepted',
                'message': f'Client accepted your proposal for "{prop["title"]}".',
                'project_id': prop['project_id'],
                'proposal_id': prop_id
            },
            user_id=pm_id['pm_id']
        )

    return ok({'deposit': deposit}, 'Proposal accepted')


@client_bp.route('/client/proposals/<int:prop_id>/reject', methods=['POST'])
@login_required(roles=CLIENT)
def reject_proposal(prop_id):
    uid  = session['user_id']
    prop = query("SELECT prop.*,pr.client_id,pr.title FROM proposals prop JOIN projects pr ON prop.project_id=pr.id WHERE prop.id=?",
                 (prop_id,), one=True)
    if not prop or prop['client_id'] != uid:
        return not_found()
    execute("UPDATE proposals SET status='rejected', responded_at=? WHERE id=?",
            (datetime.datetime.utcnow(), prop_id))
    execute("UPDATE projects SET status='requested' WHERE id=?", (prop['project_id'],))
    log_activity(uid, 'reject_proposal', 'proposal', prop_id)

    # Notify GM and PM about rejection
    gms = query("SELECT id FROM users WHERE role='general_manager' AND status='active'")
    for gm in gms:
        emit_realtime(
            'notification',
            {
                'type': 'proposal_rejected',
                'title': 'Proposal Rejected',
                'message': f'Client rejected the proposal for "{prop["title"]}".',
                'project_id': prop['project_id'],
                'proposal_id': prop_id
            },
            user_id=gm['id']
        )
    pm_id = query("SELECT pm_id FROM proposals WHERE id=?", (prop_id,), one=True)
    if pm_id and pm_id['pm_id']:
        emit_realtime(
            'notification',
            {
                'type': 'proposal_rejected',
                'title': 'Your Proposal Was Rejected',
                'message': f'Client rejected your proposal for "{prop["title"]}".',
                'project_id': prop['project_id'],
                'proposal_id': prop_id
            },
            user_id=pm_id['pm_id']
        )

    return ok(message='Proposal rejected')


@client_bp.route('/client/projects/<int:pid>/accept-delivery', methods=['POST'])
@login_required(roles=CLIENT)
def accept_delivery(pid):
    uid     = session['user_id']
    project = query("SELECT * FROM projects WHERE id=? AND client_id=?", (pid, uid), one=True)
    if not project:
        return not_found()
    if project['status'] != 'completed':
        return err('Project is not yet marked as completed')

    remaining = round(project['total_cost'] - (project['paid_deposit'] or 0), 2)
    execute("UPDATE projects SET status='delivered', paid_remaining=? WHERE id=?", (remaining, pid))
    execute("INSERT INTO payments (project_id,payer_id,amount,payment_type,description) VALUES (?,?,?,'remaining','70% final payment on delivery acceptance')",
            (pid, uid, remaining))

    log_activity(uid, 'accept_delivery', 'project', pid)

    # Notify GM
    gms = query("SELECT id FROM users WHERE role='general_manager' AND status='active'")
    for gm in gms:
        push_notification(gm['id'], 'Delivery Accepted',
                          f'Final payment ${remaining} received.', 'success')
        emit_realtime(
            'notification',
            {
                'type': 'delivery_accepted',
                'title': 'Delivery Accepted',
                'message': f'Client accepted delivery for project "{project["title"]}". Final payment ${remaining} received.',
                'project_id': pid
            },
            user_id=gm['id']
        )
        emit_realtime('dashboard_update', {'entity': 'projects'}, user_id=gm['id'])

    return ok({'final_payment': remaining}, 'Delivery accepted')


@client_bp.route('/client/comments', methods=['POST'])
@login_required(roles=CLIENT)
def add_comment():
    uid  = session['user_id']
    data = request.get_json(silent=True) or {}
    pid  = data.get('project_id')
    content = (data.get('content') or '').strip()
    if not pid or not content:
        return err('project_id and content are required')
    if not _owned(pid, uid):
        return err('Not your project')

    cid = execute(
        "INSERT INTO comments (project_id,author_id,content) VALUES (?,?,?)",
        (pid, uid, content)
    )
    # Notify GM
    project = query("SELECT gm_id, title FROM projects WHERE id=?", (pid,), one=True)
    if project and project['gm_id']:
        push_notification(project['gm_id'], 'Client Comment',
                          f'Client commented on {project["title"]}', 'info')
        # Real‑time notification to GM
        emit_realtime(
            'notification',
            {
                'type': 'new_comment',
                'title': 'New Client Comment',
                'message': f'Client commented on project "{project["title"]}"',
                'project_id': pid,
                'comment_id': cid,
                'timestamp': datetime.datetime.utcnow().isoformat()
            },
            user_id=project['gm_id']
        )
    return ok({'comment_id': cid}, 'Comment added')