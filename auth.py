"""routes/auth.py — Authentication endpoints."""
from flask import Blueprint, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import query, execute, push_notification, log_activity
from auth import set_session, clear_session, login_required
from utils import ok, err, created, validate_email, clean_skills

auth_bp = Blueprint('auth', __name__)

ROLE_REDIRECTS = {
    'admin':            '/dashboard/admin',
    'proposal_manager': '/dashboard/pm',
    'general_manager':  '/dashboard/gm',
    'freelancer':       '/dashboard/freelancer',
    'team_leader':      '/dashboard/tl',
    'team_member':      '/dashboard/member',
    'accountant':       '/dashboard/accountant',
    'client':           '/dashboard/client',
    'bank_rep':         '/dashboard/bank',
}


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return err('Username and password are required')

    user = query("SELECT * FROM users WHERE username=?", (username,), one=True)

    if not user or not check_password_hash(user['password_hash'], password):
        return err('Invalid username or password', 401)

    if user['status'] != 'active':
        return err('Account is suspended or inactive', 403)

    set_session(user)
    log_activity(user['id'], 'login')

    return ok({
        'role':      user['role'],
        'full_name': user['full_name'],
        'redirect':  ROLE_REDIRECTS.get(user['role'], '/dashboard/client'),
        'user_id':   user['id'],
    }, 'Login successful')


@auth_bp.route('/signup', methods=['POST'])
def signup():
    data  = request.get_json(silent=True) or {}
    role  = data.get('role', '').strip()
    uname = data.get('username', '').strip()
    pw    = data.get('password', '').strip()
    name  = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    skills = clean_skills(data.get('skills', ''))

    # ── Validation ──
    if role not in ('client', 'freelancer'):
        return err('Self-registration only allowed for client or freelancer')
    if not uname or len(uname) < 3:
        return err('Username must be at least 3 characters')
    if not pw or len(pw) < 6:
        return err('Password must be at least 6 characters')
    if not name:
        return err('Full name is required')
    if email and not validate_email(email):
        return err('Invalid email address')

    existing = query("SELECT id FROM users WHERE username=?", (uname,), one=True)
    if existing:
        return err('Username already taken')

    uid = execute(
        "INSERT INTO users (username,password_hash,role,full_name,email,phone,skills) VALUES (?,?,?,?,?,?,?)",
        (uname, generate_password_hash(pw), role, name, email, phone, skills)
    )
    push_notification(uid, 'Welcome to Celestial!',
                      'Your account has been created successfully.', 'success')
    return created({'user_id': uid}, 'Account created successfully')


@auth_bp.route('/logout', methods=['POST', 'GET'])
def logout():
    uid = session.get('user_id')
    if uid:
        log_activity(uid, 'logout')
    clear_session()
    return ok(message='Logged out')


@auth_bp.route('/me')
def me():
    if 'user_id' not in session:
        return ok({'authenticated': False})

    user = query("SELECT id,username,role,full_name,email,performance,training_centers,status FROM users WHERE id=?",
                 (session['user_id'],), one=True)
    if not user:
        clear_session()
        return ok({'authenticated': False})

    unread = query(
        "SELECT COUNT(*) as cnt FROM notifications WHERE user_id=? AND is_read=0",
        (session['user_id'],), one=True
    )

    return ok({
        'authenticated':    True,
        'user_id':          user['id'],
        'username':         user['username'],
        'role':             user['role'],
        'full_name':        user['full_name'],
        'email':            user['email'],
        'performance':      user['performance'],
        'training_centers': user['training_centers'],
        'theme':            session.get('theme', 'dark'),
        'unread_count':     unread['cnt'] if unread else 0,
        'redirect':         ROLE_REDIRECTS.get(user['role'], '/dashboard/client'),
    })


@auth_bp.route('/toggle-theme', methods=['POST'])
@login_required()
def toggle_theme():
    session['theme'] = 'light' if session.get('theme') == 'dark' else 'dark'
    return ok({'theme': session['theme']})


@auth_bp.route('/notifications')
@login_required()
def notifications():
    notifs = query(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (session['user_id'],)
    )
    return ok(notifs)


@auth_bp.route('/notifications/read-all', methods=['POST'])
@login_required()
def read_all_notifications():
    execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (session['user_id'],))
    return ok(message='All notifications marked as read')


@auth_bp.route('/notifications/<int:nid>/read', methods=['POST'])
@login_required()
def read_notification(nid):
    execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
            (nid, session['user_id']))
    return ok()


@auth_bp.route('/change-password', methods=['POST'])
@login_required()
def change_password():
    data     = request.get_json(silent=True) or {}
    old_pw   = data.get('old_password', '')
    new_pw   = data.get('new_password', '')

    if not new_pw or len(new_pw) < 6:
        return err('New password must be at least 6 characters')

    user = query("SELECT * FROM users WHERE id=?", (session['user_id'],), one=True)
    if not check_password_hash(user['password_hash'], old_pw):
        return err('Current password is incorrect')

    execute("UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(new_pw), session['user_id']))
    log_activity(session['user_id'], 'change_password')
    return ok(message='Password updated successfully')
