"""routes/freelancer.py — Freelancer profile, quests, training."""
from flask import Blueprint, request, session
from database import query, execute, push_notification, log_activity
from auth import login_required
from utils import ok, err

freelancer_bp = Blueprint('freelancer', __name__)
FL = ['freelancer']

QUEST_DEFINITIONS = [
    {'id': 'first_submit',    'title': 'First Step',       'description': 'Submit your first task',            'icon': 'bi-send-fill',           'xp': 50},
    {'id': 'five_on_time',    'title': 'Speed Demon',      'description': 'Submit 5 tasks on time',            'icon': 'bi-lightning-charge-fill','xp': 150},
    {'id': 'three_projects',  'title': 'Project Veteran',  'description': 'Complete 3 projects',               'icon': 'bi-trophy-fill',          'xp': 300},
    {'id': 'first_training',  'title': 'Skill Seeker',     'description': 'Use your first training center',    'icon': 'bi-mortarboard-fill',     'xp': 100},
    {'id': 'top_performer',   'title': 'Top Performer',    'description': 'Achieve 90%+ performance',          'icon': 'bi-star-fill',            'xp': 200},
    {'id': 'ten_tasks',       'title': 'Task Master',      'description': 'Complete 10 accepted tasks',        'icon': 'bi-check-circle-fill',    'xp': 200},
    {'id': 'five_projects',   'title': 'Galaxy Explorer',  'description': 'Participate in 5 projects',         'icon': 'bi-globe2',               'xp': 400},
    {'id': 'perfect_project', 'title': 'Perfectionist',    'description': 'Complete a project with 5/5 rating','icon': 'bi-gem',                  'xp': 500},
]


def _compute_quests(uid: int) -> list:
    accepted_tasks = query("SELECT COUNT(*) as c FROM tasks WHERE freelancer_id=? AND status='accepted'", (uid,), one=True)
    submitted_tasks = query("SELECT COUNT(*) as c FROM tasks WHERE freelancer_id=? AND status IN ('submitted','accepted')", (uid,), one=True)
    project_count  = query(
        "SELECT COUNT(DISTINCT project_id) as c FROM team_members WHERE user_id=?", (uid,), one=True
    )
    completed_projects = query(
        "SELECT COUNT(DISTINCT pr.id) as c FROM projects pr JOIN team_members tm ON pr.id=tm.project_id "
        "WHERE tm.user_id=? AND pr.status IN ('completed','delivered')", (uid,), one=True
    )
    user = query("SELECT performance, training_centers FROM users WHERE id=?", (uid,), one=True)
    perf = (user['performance'] or 0) if user else 0
    tc   = (user['training_centers'] or 0) if user else 0
    best_rating = query("SELECT MAX(rating) as m FROM ratings WHERE rated_user_id=?", (uid,), one=True)

    n_accepted  = accepted_tasks['c']  if accepted_tasks  else 0
    n_submitted = submitted_tasks['c'] if submitted_tasks else 0
    n_projects  = project_count['c']   if project_count   else 0
    n_completed = completed_projects['c'] if completed_projects else 0
    best_r      = (best_rating['m'] or 0) if best_rating else 0

    earned_map = {
        'first_submit':    n_submitted >= 1,
        'five_on_time':    n_submitted >= 5,
        'three_projects':  n_completed >= 3,
        'first_training':  tc > 0,
        'top_performer':   perf >= 4.5,
        'ten_tasks':       n_accepted >= 10,
        'five_projects':   n_projects >= 5,
        'perfect_project': best_r >= 5.0,
    }
    return [{**q, 'earned': earned_map.get(q['id'], False)} for q in QUEST_DEFINITIONS]


@freelancer_bp.route('/freelancer/dashboard')
@login_required(roles=FL)
def fl_dashboard():
    uid   = session['user_id']
    user  = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if user:
        user.pop('password_hash', None)

    tasks = query(
        "SELECT t.*,ph.name as phase_name,pr.title as project_title "
        "FROM tasks t JOIN phases ph ON t.phase_id=ph.id JOIN projects pr ON ph.project_id=pr.id "
        "WHERE t.freelancer_id=? ORDER BY t.created_at DESC", (uid,)
    )
    projects = query(
        "SELECT pr.*,u.full_name as client_name FROM projects pr "
        "JOIN team_members tm ON pr.id=tm.project_id JOIN users u ON pr.client_id=u.id "
        "WHERE tm.user_id=?", (uid,)
    )
    ratings = query("SELECT rating,comment,rated_at FROM ratings WHERE rated_user_id=? ORDER BY rated_at DESC LIMIT 10", (uid,))
    quests  = _compute_quests(uid)

    perf_pct = round((user['performance'] or 0) / 5 * 100) if user else 0

    return ok({
        'user':     user,
        'tasks':    tasks,
        'projects': projects,
        'ratings':  ratings,
        'quests':   quests,
        'stats': {
            'perf_pct':         perf_pct,
            'total_projects':   len(projects),
            'accepted_tasks':   sum(1 for t in tasks if t['status'] == 'accepted'),
            'pending_tasks':    sum(1 for t in tasks if t['status'] in ('pending','in_progress')),
            'training_centers': user['training_centers'] if user else 0,
            'earned_quests':    sum(1 for q in quests if q['earned']),
        }
    })


@freelancer_bp.route('/freelancer/training', methods=['POST'])
@login_required(roles=FL)
def use_training():
    uid  = session['user_id']
    user = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not user or (user['training_centers'] or 0) < 1:
        return err('No training centers available')

    data       = request.get_json(silent=True) or {}
    skill_area = data.get('skill_area', 'General')
    current    = [s.strip() for s in (user['skills'] or '').split(',') if s.strip()]
    new_skill  = f'{skill_area} (Advanced)'
    if new_skill not in current:
        current.append(new_skill)

    execute("UPDATE users SET training_centers=training_centers-1, skills=? WHERE id=?",
            (', '.join(current), uid))
    log_activity(uid, 'use_training', meta={'skill': new_skill})
    return ok({'new_skills': current}, f'Training complete! "{new_skill}" added to your profile.')
