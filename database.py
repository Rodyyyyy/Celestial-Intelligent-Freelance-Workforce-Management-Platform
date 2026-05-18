"""
database.py — SQLite schema, connection pooling, and seed data.

All tables use INTEGER PRIMARY KEY AUTOINCREMENT and explicit FK constraints.
Row-level helpers return dict for clean JSON serialisation.
"""
import sqlite3, datetime, json
from flask import g, current_app
from werkzeug.security import generate_password_hash


# ── Connection ─────────────────────────────────────────────────────────────────

def get_db():
    """Return a per-request connection stored on Flask's g object."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query(sql, params=(), one=False):
    """Utility: run a SELECT and return dict(s)."""
    cur = get_db().execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    return rows[0] if (one and rows) else (None if one else rows)


def execute(sql, params=()):
    """Utility: run INSERT/UPDATE/DELETE, commit, return lastrowid."""
    db  = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur.lastrowid


# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    UNIQUE NOT NULL,
    password_hash    TEXT    NOT NULL,
    role             TEXT    NOT NULL
        CHECK(role IN ('admin','proposal_manager','general_manager',
                       'freelancer','team_leader','team_member',
                       'accountant','client','bank_rep')),
    full_name        TEXT,
    email            TEXT,
    phone            TEXT,
    skills           TEXT    DEFAULT '',
    performance      REAL    DEFAULT 0.0,
    training_centers INTEGER DEFAULT 0,
    quest_progress   TEXT    DEFAULT '{}',
    status           TEXT    DEFAULT 'active'
        CHECK(status IN ('active','inactive','suspended')),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    description      TEXT    DEFAULT '',
    client_id        INTEGER NOT NULL REFERENCES users(id),
    gm_id            INTEGER REFERENCES users(id),
    team_leader_id   INTEGER REFERENCES users(id),
    status           TEXT    DEFAULT 'requested'
        CHECK(status IN ('requested','proposal_sent','proposal_accepted',
                         'in_progress','completed','delivered','cancelled')),
    total_cost       REAL    DEFAULT 0.0,
    paid_deposit     REAL    DEFAULT 0.0,
    paid_remaining   REAL    DEFAULT 0.0,
    required_skills  TEXT    DEFAULT '',
    num_freelancers  INTEGER DEFAULT 1,
    division_method  TEXT    DEFAULT '',
    auto_div_rating  TEXT    DEFAULT '',
    deadline         DATE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proposals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    pm_id            INTEGER REFERENCES users(id),
    content          TEXT    DEFAULT '',
    cost             REAL    DEFAULT 0.0,
    status           TEXT    DEFAULT 'pending'
        CHECK(status IN ('pending','accepted','rejected')),
    sent_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    responded_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS phases (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name             TEXT    NOT NULL,
    description      TEXT    DEFAULT '',
    deadline         DATE,
    status           TEXT    DEFAULT 'pending'
        CHECK(status IN ('pending','active','submitted_for_review','completed','rejected')),
    order_num        INTEGER DEFAULT 0,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id         INTEGER NOT NULL REFERENCES phases(id) ON DELETE CASCADE,
    freelancer_id    INTEGER NOT NULL REFERENCES users(id),
    title            TEXT    DEFAULT '',
    description      TEXT    DEFAULT '',
    deadline         DATE,
    status           TEXT    DEFAULT 'pending'
        CHECK(status IN ('pending','in_progress','submitted','accepted','rejected')),
    submission       TEXT    DEFAULT '',
    tl_comment       TEXT    DEFAULT '',
    submitted_at     TIMESTAMP,
    completed_at     TIMESTAMP,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_members (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id          INTEGER NOT NULL REFERENCES users(id),
    role_in_team     TEXT    DEFAULT 'team_member',
    joined_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, user_id)
);

CREATE TABLE IF NOT EXISTS ratings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    rated_by         INTEGER REFERENCES users(id),
    rated_user_id    INTEGER REFERENCES users(id),
    project_id       INTEGER REFERENCES projects(id),
    rating           REAL    CHECK(rating BETWEEN 0 AND 5),
    comment          TEXT    DEFAULT '',
    rated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER REFERENCES projects(id),
    payer_id         INTEGER REFERENCES users(id),
    payee_id         INTEGER REFERENCES users(id),
    amount           REAL    DEFAULT 0.0,
    payment_type     TEXT    DEFAULT 'other'
        CHECK(payment_type IN ('deposit','remaining','salary','bonus','other')),
    description      TEXT    DEFAULT '',
    reference_no     TEXT,
    paid_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title            TEXT    NOT NULL,
    message          TEXT    DEFAULT '',
    type             TEXT    DEFAULT 'info'
        CHECK(type IN ('info','success','warning','error')),
    is_read          INTEGER DEFAULT 0,
    link             TEXT    DEFAULT '',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS comments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    phase_id         INTEGER REFERENCES phases(id) ON DELETE CASCADE,
    author_id        INTEGER NOT NULL REFERENCES users(id),
    content          TEXT    NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER REFERENCES users(id),
    action           TEXT    NOT NULL,
    entity_type      TEXT    DEFAULT '',
    entity_id        INTEGER DEFAULT 0,
    meta             TEXT    DEFAULT '{}',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rl_feedback (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER REFERENCES projects(id),
    division_data    TEXT    DEFAULT '{}',
    gm_rating        INTEGER CHECK(gm_rating IN (-1, 0, 1)),
    notes            TEXT    DEFAULT '',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ── Indexes ────────────────────────────────────────────────────────────────────

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_projects_client  ON projects(client_id);
CREATE INDEX IF NOT EXISTS idx_projects_status  ON projects(status);
CREATE INDEX IF NOT EXISTS idx_phases_project   ON phases(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_phase      ON tasks(phase_id);
CREATE INDEX IF NOT EXISTS idx_tasks_freelancer ON tasks(freelancer_id);
CREATE INDEX IF NOT EXISTS idx_team_project     ON team_members(project_id);
CREATE INDEX IF NOT EXISTS idx_notif_user       ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_activity_user    ON activity_log(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_project ON payments(project_id);
"""


def init_db():
    """Initialise schema, indexes and seed default accounts."""
    import sqlite3 as _sq
    from config import Config

    conn = _sq.connect(Config.DATABASE)
    conn.row_factory = _sq.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.executescript(INDEXES)

    # Seed system accounts (skip if already exist)
    seeds = [
        ('admin',    generate_password_hash('admin123'),    'admin',            'System Admin',      'admin@celestial.io'),
        ('pm',       generate_password_hash('pm123'),       'proposal_manager', 'Proposal Manager',  'pm@celestial.io'),
        ('gm',       generate_password_hash('gm123'),       'general_manager',  'General Manager',   'gm@celestial.io'),
        ('acc',      generate_password_hash('acc123'),      'accountant',       'Accountant',        'acc@celestial.io'),
        ('bank',     generate_password_hash('bank123'),     'bank_rep',         'Bank Representative','bank@celestial.io'),
        ('tl1',      generate_password_hash('tl123'),       'team_leader',      'Team Leader One',   'tl1@celestial.io'),
        ('fl1',      generate_password_hash('fl123'),       'freelancer',       'Freelancer One',    'fl1@celestial.io'),
        ('client1',  generate_password_hash('client123'),   'client',           'Demo Client',       'client@celestial.io'),
    ]
    for row in seeds:
        try:
            conn.execute(
                "INSERT INTO users (username,password_hash,role,full_name,email) VALUES (?,?,?,?,?)",
                row
            )
        except _sq.IntegrityError:
            pass

    conn.commit()
    conn.close()


# ── Notification helper ────────────────────────────────────────────────────────

def push_notification(user_id, title, message='', ntype='info', link=''):
    execute(
        "INSERT INTO notifications (user_id,title,message,type,link) VALUES (?,?,?,?,?)",
        (user_id, title, message, ntype, link)
    )


# ── Activity log helper ────────────────────────────────────────────────────────

def log_activity(user_id, action, entity_type='', entity_id=0, meta=None):
    execute(
        "INSERT INTO activity_log (user_id,action,entity_type,entity_id,meta) VALUES (?,?,?,?,?)",
        (user_id, action, entity_type, entity_id, json.dumps(meta or {}))
    )
