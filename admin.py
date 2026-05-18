"""routes/admin.py — Admin: user management, system overview."""
from flask import Blueprint, request, session
from werkzeug.security import generate_password_hash
from database import query, execute, push_notification, log_activity
from auth import login_required
from utils import ok, err, not_found, clean_skills, validate_email

admin_bp = Blueprint('admin', __name__)
ADMIN = ['admin']


@admin_bp.route('/admin/dashboard')
@login_required(roles=ADMIN)
def admin_dashboard():
    users    = query("SELECT role, status, created_at FROM users")
    projects = query("SELECT status, total_cost, paid_deposit, paid_remaining FROM projects")
    payments = query("SELECT amount, payment_type FROM payments")

    total_users    = len(users)
    active_users   = sum(1 for u in users if u['status'] == 'active')
    total_projects = len(projects)
    total_revenue  = sum((p['paid_deposit'] or 0) + (p['paid_remaining'] or 0) for p in projects)
    total_paid_out = sum(p['amount'] or 0 for p in payments if p['payment_type'] == 'salary')

    role_breakdown = {}
    for u in users:
        role_breakdown[u['role']] = role_breakdown.get(u['role'], 0) + 1

    recent_users = query(
        "SELECT id,username,role,full_name,email,status,created_at FROM users ORDER BY created_at DESC LIMIT 10"
    )
    recent_projects = query(
        "SELECT p.*,u.full_name as client_name FROM projects p JOIN users u ON p.client_id=u.id ORDER BY p.created_at DESC LIMIT 10"
    )
    recent_payments = query(
        "SELECT py.*,u.full_name as payee_name FROM payments py JOIN users u ON py.payee_id=u.id ORDER BY py.paid_at DESC LIMIT 10"
    )

    # Monthly signups (last 6 months)
    monthly_signups = query(
        "SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count "
        "FROM users WHERE created_at >= date('now','-6 months') "
        "GROUP BY month ORDER BY month"
    )

    return ok({
        'stats': {
            'total_users':    total_users,
            'active_users':   active_users,
            'total_projects': total_projects,
            'total_revenue':  round(total_revenue, 2),
            'total_paid_out': round(total_paid_out, 2),
        },
        'role_breakdown':   role_breakdown,
        'recent_users':     recent_users,
        'recent_projects':  recent_projects,
        'recent_payments':  recent_payments,
        'monthly_signups':  monthly_signups,
    })


@admin_bp.route('/admin/users')
@login_required(roles=ADMIN)
def list_users():
    role   = request.args.get('role')
    status = request.args.get('status')
    search = request.args.get('search', '').strip()

    sql    = "SELECT id,username,role,full_name,email,phone,skills,performance,training_centers,status,created_at FROM users WHERE 1=1"
    params = []
    if role:
        sql += " AND role=?"; params.append(role)
    if status:
        sql += " AND status=?"; params.append(status)
    if search:
        sql += " AND (full_name LIKE ? OR username LIKE ? OR email LIKE ?)"; params += [f'%{search}%']*3

    sql += " ORDER BY created_at DESC"
    return ok(query(sql, params))


@admin_bp.route('/admin/users', methods=['POST'])
@login_required(roles=ADMIN)
def create_user():
    data   = request.get_json(silent=True) or {}
    role   = data.get('role', '').strip()
    uname  = data.get('username', '').strip()
    pw     = data.get('password', 'celestial123').strip()
    name   = data.get('full_name', '').strip()
    email  = data.get('email', '').strip()
    phone  = data.get('phone', '').strip()
    skills = clean_skills(data.get('skills', ''))

    from auth import ROLES
    if role not in ROLES:
        return err('Invalid role')
    if not uname or len(uname) < 3:
        return err('Username must be at least 3 characters')
    if not name:
        return err('Full name is required')
    if email and not validate_email(email):
        return err('Invalid email')
    if query("SELECT id FROM users WHERE username=?", (uname,), one=True):
        return err('Username already exists')

    uid = execute(
        "INSERT INTO users (username,password_hash,role,full_name,email,phone,skills) VALUES (?,?,?,?,?,?,?)",
        (uname, generate_password_hash(pw), role, name, email, phone, skills)
    )
    push_notification(uid, 'Account Created', f'Your {role.replace("_"," ")} account has been created by Admin.', 'info')
    log_activity(session['user_id'], 'admin_create_user', 'user', uid, {'role': role, 'username': uname})
    return ok({'user_id': uid}, 'User created')


@admin_bp.route('/admin/users/<int:uid>', methods=['GET'])
@login_required(roles=ADMIN)
def get_user(uid):
    user = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not user:
        return not_found('User not found')
    user.pop('password_hash', None)
    return ok(user)


@admin_bp.route('/admin/users/<int:uid>', methods=['PUT', 'PATCH'])
@login_required(roles=ADMIN)
def update_user(uid):
    data   = request.get_json(silent=True) or {}
    user   = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not user:
        return not_found()

    fields, params = [], []
    allowed = ['full_name', 'email', 'phone', 'role', 'skills', 'status', 'performance', 'training_centers']
    for f in allowed:
        if f in data:
            val = clean_skills(data[f]) if f == 'skills' else data[f]
            fields.append(f"{f}=?"); params.append(val)

    if 'password' in data and data['password']:
        fields.append("password_hash=?"); params.append(generate_password_hash(data['password']))

    if not fields:
        return err('No fields to update')

    params.append(uid)
    execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", params)
    log_activity(session['user_id'], 'admin_update_user', 'user', uid)
    return ok(message='User updated')


@admin_bp.route('/admin/users/<int:uid>', methods=['DELETE'])
@login_required(roles=ADMIN)
def delete_user(uid):
    if uid == session['user_id']:
        return err('Cannot delete your own account')
    user = query("SELECT id,full_name FROM users WHERE id=?", (uid,), one=True)
    if not user:
        return not_found()
    execute("DELETE FROM users WHERE id=?", (uid,))
    log_activity(session['user_id'], 'admin_delete_user', 'user', uid, {'name': user['full_name']})
    return ok(message='User deleted')


@admin_bp.route('/admin/projects')
@login_required(roles=ADMIN)
def admin_projects():
    projects = query(
        "SELECT p.*,u.full_name as client_name FROM projects p "
        "JOIN users u ON p.client_id=u.id ORDER BY p.created_at DESC"
    )
    return ok(projects)


@admin_bp.route('/admin/payments')
@login_required(roles=ADMIN)
def admin_payments():
    rows = query(
        "SELECT py.*,u.full_name as payee_name,pr.title as project_title "
        "FROM payments py "
        "LEFT JOIN users u ON py.payee_id=u.id "
        "LEFT JOIN projects pr ON py.project_id=pr.id "
        "ORDER BY py.paid_at DESC LIMIT 100"
    )
    return ok(rows)


@admin_bp.route('/admin/system-stats')
@login_required(roles=ADMIN)
def system_stats():
    """Aggregated time-series data for admin charts."""
    project_by_status = query(
        "SELECT status, COUNT(*) as count FROM projects GROUP BY status"
    )
    revenue_monthly = query(
        "SELECT strftime('%Y-%m', paid_at) as month, SUM(amount) as total "
        "FROM payments WHERE paid_at >= date('now','-12 months') "
        "GROUP BY month ORDER BY month"
    )
    task_completion = query(
        "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
    )
    top_freelancers = query(
        "SELECT id,full_name,performance,training_centers,skills FROM users "
        "WHERE role IN ('freelancer','team_leader','team_member') "
        "ORDER BY performance DESC LIMIT 10"
    )
    return ok({
        'project_by_status': project_by_status,
        'revenue_monthly':   revenue_monthly,
        'task_completion':   task_completion,
        'top_freelancers':   top_freelancers,
    })
