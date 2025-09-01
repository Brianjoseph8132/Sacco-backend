from models import LoanRepayment,db, Loan, Notification, Member, Account
from flask import jsonify,request, Blueprint
from werkzeug.security import generate_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from decimal import Decimal
from datetime import datetime


repayment_bp = Blueprint("repayment_bp", __name__)


def create_notification(recipient_username, message, type, loan_id=None, sender_id=None):
    notif = Notification(
        recipient_username=recipient_username,
        sender_id=sender_id,
        message=message,
        type=type,
        loan_id=loan_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(notif)
    db.session.commit()


@repayment_bp.route('/repayments/<int:loan_id>', methods=['POST'])
@jwt_required()
def create_repayment(loan_id):
    current_user_id = get_jwt_identity()
    current_user = Member.query.get(current_user_id)
    
    loan = Loan.query.get_or_404(loan_id)
    
    if loan.member_id != current_user.id:
        return jsonify({"error": "You can only repay your own loans"}), 403
    
    if loan.status != 'approved':
        return jsonify({"error": "Cannot repay non-approved loans"}), 400

    data = request.get_json()
    
    try:
        amount = Decimal(str(data['amount']))
        payment_method = data.get('payment_method', 'M-Pesa')
    except (ValueError, KeyError):
        return jsonify({"error": "Invalid payment details"}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    # --- Calculate totals ---
    total_due = loan.amount * (Decimal('1') + loan.interest_rate / Decimal('100'))
    total_repaid = sum((r.amount for r in loan.repayments), Decimal('0.00'))
    new_total_repaid = total_repaid + amount

    # --- Calculate how much is interest vs principal ---
    total_interest_due = loan.amount * (loan.interest_rate / Decimal('100'))
    total_principal_due = loan.amount

    # Already repaid breakdown
    repaid_interest = sum((r.interest_component for r in loan.repayments), Decimal('0.00'))
    repaid_principal = sum((r.principal_component for r in loan.repayments), Decimal('0.00'))

    # Remaining breakdown
    remaining_interest = total_interest_due - repaid_interest
    remaining_principal = total_principal_due - repaid_principal

    # Allocate repayment
    interest_component = min(amount, remaining_interest)
    principal_component = amount - interest_component

    # Create repayment with split
    repayment = LoanRepayment(
        loan_id=loan_id,
        amount=amount,
        payment_method=payment_method,
        principal_component=principal_component,
        interest_component=interest_component
    )
    db.session.add(repayment)

    balance = total_due - new_total_repaid

    # Member account
    member_account = Account.query.filter_by(member_id=current_user.id).first()
    if not member_account:
        return jsonify({"error": "Member account not found"}), 404

    # Fully paid or overpaid
    excess_amount = Decimal('0.00')
    if new_total_repaid >= total_due:
        loan.status = 'paid'
        loan.due_date = datetime.utcnow()

        notification = Notification(
            recipient_username=current_user.id,
            title="Loan Fully Repaid",
            message=f"Loan #{loan_id} has been fully settled. Total paid: {new_total_repaid}",
            type="loan_paid",
            loan_id=loan_id
        )
        db.session.add(notification)

        # Handle overpayment
        excess_amount = new_total_repaid - total_due
        if excess_amount > 0:
            member_account.deposit(excess_amount)

    try:
        db.session.commit()
        return jsonify({
            "success": "Repayment recorded",
            "principal_component": float(principal_component),
            "interest_component": float(interest_component),
            "balance_remaining": float(balance if balance > 0 else 0),
            "loan_status": loan.status,
            "overpaid_amount": float(excess_amount) if excess_amount > 0 else 0.0
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# repayment history
@repayment_bp.route('/history/<int:loan_id>', methods=['GET'])
@jwt_required()
def repayment_history(loan_id):
    current_user_id = get_jwt_identity()
    current_user = Member.query.get(current_user_id)

    loan = Loan.query.get_or_404(loan_id)

    # Only the loan owner can view the history
    if loan.member_id != current_user.id:
        return jsonify({"error": "You can only view your own loan history"}), 403

    repayments = LoanRepayment.query.filter_by(loan_id=loan_id).order_by(LoanRepayment.payment_date.asc()).all()

    loan_total_with_interest = loan.amount + loan.amount * (loan.interest_rate / 100)

    history_list = []
    running_total_paid = Decimal('0.00')

    for r in repayments:
        running_total_paid += r.amount
        balance_remaining = loan_total_with_interest - running_total_paid

        history_list.append({
            "repayment_id": r.id,
            "amount_paid": float(r.amount),
            "payment_method": r.payment_method,
            "payment_date": r.payment_date.strftime('%Y-%m-%d %H:%M:%S'),
            "total_paid_so_far": float(running_total_paid),
            "balance_remaining": float(balance_remaining)
        })

    return jsonify({
        "loan_id": loan_id,
        "loan_amount": float(loan.amount),
        "interest_rate": float(loan.interest_rate),
        "loan_total_with_interest": float(loan_total_with_interest),
        "repayments": history_list
    }), 200



@repayment_bp.route('/repayment-history/<int:loan_id>', methods=['GET'])
@jwt_required()
def get_repayment_history(loan_id):
    # Get authenticated member
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)

    # Fetch the loan
    loan = Loan.query.get(loan_id)
    if not loan:
        return jsonify({"message": "Loan not found"}), 404

    # Ensure the member owns this loan
    if loan.member_id != member.id:
        return jsonify({"message": "Unauthorized access to this loan"}), 403

    # Get all repayments
    repayments = loan.repayments

    # Calculate total repaid
    total_repaid = sum(float(r.amount) for r in repayments)

    # Calculate total due (loan amount + interest)
    loan_amount = float(loan.amount)
    interest_amount = loan_amount * (float(loan.interest_rate) / 100)
    total_due = loan_amount + interest_amount

    # Calculate balance (total due - total repaid)
    balance = total_due - total_repaid

    # Format repayment history
    repayment_history = []
    for r in repayments:
        repayment_history.append({
            "repayment_id": r.id,
            "amount": float(r.amount),
            "payment_date": r.payment_date.isoformat() if r.payment_date else None,
            "payment_method": r.payment_method
        })

    return jsonify({
        "loan_id": loan.id,
        "repayment_history": repayment_history,
        "total_repaid": round(total_repaid, 2),
        "total_due": round(total_due, 2),
        "balance": round(balance, 2)
    })