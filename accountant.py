"""routes/accountant.py — Accountant: salary processing, financial reports."""
from flask import Blueprint, request, session
import datetime
from database import query, execute, push_notification, log_activity
from auth import login_required
from utils import ok, err, not_found

accountant_bp = Blueprint('accountant', __name__)
ACC = ['accountant']


@accountant_bp.route('/accountant/dashboard')
@login_required(roles=ACC)
def acc_dashboard():
    employees = query(
        "SELECT id,full_name,role,performance,status FROM users "
        "WHERE role IN ('freelancer','team_leader','team_member') AND status='active' ORDER BY full_name"
    )
    payments = query(
        "SELECT py.*,u.full_name as payee_name,pr.title as project_title "
        "FROM payments py LEFT JOIN users u ON py.payee_id=u.id "
        "LEFT JOIN projects pr ON py.project_id=pr.id ORDER BY py.paid_at DESC LIMIT 50"
    )
    salary_payments = [p for p in payments if p['payment_type'] == 'salary']
    total_salaries  = sum(p['amount'] or 0 for p in salary_payments)

    # Monthly salary data for chart
    monthly_salaries = query(
        "SELECT strftime('%Y-%m', paid_at) as month, SUM(amount) as total "
        "FROM payments WHERE payment_type='salary' AND paid_at>=date('now','-12 months') "
        "GROUP BY month ORDER BY month"
    )
    # Project revenue
    project_revenue = query(
        "SELECT strftime('%Y-%m', updated_at) as month, SUM(total_cost) as total "
        "FROM projects WHERE status IN ('completed','delivered') AND updated_at>=date('now','-12 months') "
        "GROUP BY month ORDER BY month"
    )

    return ok({
        'employees':        employees,
        'payments':         payments,
        'monthly_salaries': monthly_salaries,
        'project_revenue':  project_revenue,
        'stats': {
            'total_employees':    len(employees),
            'total_salaries_paid': round(total_salaries, 2),
            'pending_payments':   len([e for e in employees]),  # all active = potentially unpaid
        }
    })


@accountant_bp.route('/accountant/pay-salary', methods=['POST'])
@login_required(roles=ACC)
def pay_salary():
    data    = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    amount  = data.get('amount', 1000.0)
    desc    = data.get('description', 'Monthly salary payment')

    if not user_id:
        return err('user_id is required')
    user = query("SELECT id,full_name FROM users WHERE id=?", (user_id,), one=True)
    if not user:
        return not_found('Employee not found')

    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return err('Invalid amount')

    pid = execute(
        "INSERT INTO payments (payee_id,amount,payment_type,description,reference_no) VALUES (?,?,?,?,?)",
        (user_id, amount, 'salary', desc, f'SAL-{datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")}')
    )
    push_notification(user_id, 'Salary Credited',
                      f'Your salary of ${amount:,.2f} has been processed.', 'success')
    log_activity(session['user_id'], 'pay_salary', 'user', user_id, {'amount': amount})
    return ok({'payment_id': pid}, f'Salary of ${amount:,.2f} paid to {user["full_name"]}')
    emit_realtime(
    'payment_received',
    {
        'type': 'salary',
        'amount': amount,
        'description': desc,
        'reference': reference_no
    },
    user_id=user_id
)

@accountant_bp.route('/accountant/pay-bulk', methods=['POST'])
@login_required(roles=ACC)
def pay_bulk():
    data    = request.get_json(silent=True) or {}
    amount  = float(data.get('amount', 1000.0))
    employees = query(
        "SELECT id FROM users WHERE role IN ('freelancer','team_leader','team_member') AND status='active'"
    )
    count = 0
    for e in employees:
        execute("INSERT INTO payments (payee_id,amount,payment_type,description) VALUES (?,?,?,?)",
                (e['id'], amount, 'salary', 'Bulk monthly salary'))
        push_notification(e['id'], 'Salary Credited', f'Salary ${amount:,.2f} processed.', 'success')
        count += 1
    log_activity(session['user_id'], 'bulk_salary', meta={'count': count, 'amount': amount})
    return ok({'count': count}, f'Salary paid to {count} employees')


@accountant_bp.route('/accountant/financial-report')
@login_required(roles=ACC)
def financial_report():
    total_revenue = query(
        "SELECT SUM(paid_deposit+paid_remaining) as total FROM projects WHERE status IN ('completed','delivered')",
        one=True
    )
    total_salaries = query("SELECT SUM(amount) as total FROM payments WHERE payment_type='salary'", one=True)
    pending_payments = query(
        "SELECT SUM(total_cost*(1-(COALESCE(paid_deposit,0)+COALESCE(paid_remaining,0))/NULLIF(total_cost,0))) as total "
        "FROM projects WHERE status='in_progress'",
        one=True
    )
    by_type = query("SELECT payment_type, SUM(amount) as total, COUNT(*) as count FROM payments GROUP BY payment_type")
    monthly = query(
        "SELECT strftime('%Y-%m', paid_at) as month, payment_type, SUM(amount) as total "
        "FROM payments WHERE paid_at>=date('now','-12 months') GROUP BY month, payment_type ORDER BY month"
    )
    return ok({
        'total_revenue':     round(total_revenue['total'] or 0, 2) if total_revenue else 0,
        'total_salaries':    round(total_salaries['total'] or 0, 2) if total_salaries else 0,
        'pending_payments':  round(pending_payments['total'] or 0, 2) if pending_payments else 0,
        'by_type':           by_type,
        'monthly':           monthly,
    })
