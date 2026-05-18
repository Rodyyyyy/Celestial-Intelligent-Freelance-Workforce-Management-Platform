"""routes/bank.py — Bank Representative: transaction monitoring."""
from flask import Blueprint, request
from database import query
from auth import login_required
from utils import ok

bank_bp = Blueprint('bank', __name__)
BANK = ['bank_rep']


@bank_bp.route('/bank/dashboard')
@login_required(roles=BANK)
def bank_dashboard():
    payments = query(
        "SELECT py.*,u.full_name as payee_name,pr.title as project_title "
        "FROM payments py LEFT JOIN users u ON py.payee_id=u.id "
        "LEFT JOIN projects pr ON py.project_id=pr.id ORDER BY py.paid_at DESC"
    )
    projects = query(
        "SELECT p.*,u.full_name as client_name FROM projects p "
        "JOIN users u ON p.client_id=u.id WHERE p.status IN ('proposal_accepted','in_progress','completed','delivered') "
        "ORDER BY p.updated_at DESC"
    )

    total_deposits   = sum(p['amount'] or 0 for p in payments if p['payment_type'] == 'deposit')
    total_remaining  = sum(p['amount'] or 0 for p in payments if p['payment_type'] == 'remaining')
    total_salaries   = sum(p['amount'] or 0 for p in payments if p['payment_type'] == 'salary')
    total_volume     = sum(p['amount'] or 0 for p in payments)

    monthly_volume = query(
        "SELECT strftime('%Y-%m', paid_at) as month, SUM(amount) as total, COUNT(*) as count "
        "FROM payments WHERE paid_at>=date('now','-12 months') GROUP BY month ORDER BY month"
    )
    by_type = query(
        "SELECT payment_type, SUM(amount) as total, COUNT(*) as count FROM payments GROUP BY payment_type"
    )

    return ok({
        'payments':       payments,
        'projects':       projects,
        'monthly_volume': monthly_volume,
        'by_type':        by_type,
        'stats': {
            'total_deposits':  round(total_deposits, 2),
            'total_remaining': round(total_remaining, 2),
            'total_salaries':  round(total_salaries, 2),
            'total_volume':    round(total_volume, 2),
            'total_transactions': len(payments),
        }
    })


@bank_bp.route('/bank/transactions')
@login_required(roles=BANK)
def transactions():
    payment_type = request.args.get('type')
    sql = (
        "SELECT py.*,u.full_name as payee_name,pr.title as project_title "
        "FROM payments py LEFT JOIN users u ON py.payee_id=u.id "
        "LEFT JOIN projects pr ON py.project_id=pr.id"
    )
    params = []
    if payment_type:
        sql += " WHERE py.payment_type=?"; params.append(payment_type)
    sql += " ORDER BY py.paid_at DESC LIMIT 200"
    return ok(query(sql, params))
