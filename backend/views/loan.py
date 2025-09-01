from models import Loan,db, Member,Notification,LoanRepayment
from flask import jsonify,request, Blueprint
from werkzeug.security import generate_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from datetime import datetime
from sqlalchemy import or_


loan_bp = Blueprint("loan_bp", __name__)



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


# Apply loan
@loan_bp.route('/loan', methods=['POST'])
@jwt_required()
def create_loan():
    current_user_id = get_jwt_identity()
    current_member = Member.query.get(current_user_id)

    if not current_member:
        return jsonify({"error": "Member not found"}), 404

    data = request.get_json()

    # Validate required fields
    if not data.get('amount') or not data.get('purpose'):
        return jsonify({"error": "Amount and purpose are required"}), 400

    # Validate guarantor
    guarantor_username = data.get('guarantor_username')
    if guarantor_username:
        guarantor = Member.query.filter_by(username=guarantor_username).first()
        if not guarantor:
            return jsonify({"error": "Guarantor not found"}), 404
        if guarantor.id == current_member.id:
            return jsonify({"error": "Cannot be your own guarantor"}), 400

    # Create loan
    new_loan = Loan(
        member_id=current_member.id,
        amount=data['amount'],
        purpose=data['purpose'],
        term_months=data.get('term_months', 6),
        guarantor_username=guarantor_username
    )

    db.session.add(new_loan)
    db.session.flush()  # Get loan ID before commit

    # Notification for applicant
    member_notification = Notification(
        recipient_username=current_member.id,
        title="Loan Application Submitted",
        message=f"Your loan request of {data['amount']} is under review",
        type="loan_application",
        loan_id=new_loan.id
    )
    db.session.add(member_notification)

    # Notification for all admins
    admins = Member.query.filter_by(is_admin=True).all()
    for admin in admins:
        admin_notification = Notification(
            recipient_username=admin.id,
            title="New Loan Application",
            message=(
                f"Member: {current_member.first_name} {current_member.last_name}\n"
                f"Username: @{current_member.username}\n"
                f"Amount: {data['amount']}\n"
                f"Purpose: {data['purpose']}\n"
                f"Applied: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
            ),
            type="admin_loan_alert",
            loan_id=new_loan.id
        )
        db.session.add(admin_notification)

    try:
        db.session.commit()
        return jsonify({
            "success": "Loan application submitted",
            "loan_id": new_loan.id,
            "notifications_sent": len(admins) + 1  # Count of admins + applicant
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500



# loan history
@loan_bp.route('/history', methods=['GET'])
@jwt_required()
def loan_history():
    # Get authenticated member
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)

    if not member:
        return jsonify({"error": "Member not found"}), 404  

    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Query all loans for the member
    loans = Loan.query.filter_by(member_id=member.id)\
                     .order_by(Loan.application_date.desc())\
                     .paginate(page=page, per_page=per_page, error_out=False)

    # Build detailed history
    history = []
    for loan in loans.items:
        loan_entry = {
            "loan_id": loan.id,
            "amount": float(loan.amount),
            "purpose": loan.purpose,
            "status": loan.status,
            "application_date": loan.application_date.isoformat(),
            "approval_date": loan.approval_date.isoformat() if loan.approval_date else None,
            "term_months": loan.term_months, 
            "interest_rate": loan.interest_rate,
            "repayments": [],
            "notifications": []
        }

        # Add repayments
        for repayment in loan.repayments:
            loan_entry["repayments"].append({
                "amount": float(repayment.amount),
                "date": repayment.payment_date.isoformat(),
                "method": repayment.payment_method
            })

        # Add status change notifications
        status_notifications = Notification.query.filter(
            Notification.loan_id == loan.id,
            or_(
                Notification.type == 'loan_approved',
                Notification.type == 'loan_rejected',
                Notification.type == 'loan_paid'
            )
        ).all()

        for note in status_notifications:
            loan_entry["notifications"].append({
                "date": note.timestamp.isoformat(),
                "message": note.message,
                "type": note.type
            })

        history.append(loan_entry)

    return jsonify({
        "loans": history,
        "meta": {
            "total_loans": loans.total,
            "current_page": loans.page,
            "per_page": loans.per_page,
            "total_pages": loans.pages
        }
    })

# loan reypayment history
@loan_bp.route('/<int:loan_id>/repayments', methods=['GET'])
@jwt_required()
def get_repayments(loan_id):
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)
    loan = Loan.query.get_or_404(loan_id)
    
    if loan.member_id != current_user.id and not current_user.is_admin:
        return jsonify({"error": "Unauthorized access"}), 403

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    repayments = LoanRepayment.query.filter_by(loan_id=loan_id)\
                                   .order_by(desc(LoanRepayment.payment_date))\
                                   .paginate(page=page, per_page=per_page)

    return jsonify({
        "repayments": [{
            "id": r.id,
            "amount": float(r.amount),
            "date": r.payment_date.isoformat(),
            "method": r.payment_method,
            "status": r.status
        } for r in repayments.items],
        "meta": {
            "total": repayments.total,
            "pages": repayments.pages,
            "current_page": repayments.page
        }
    })


@loan_bp.route('/check-loan-status/<int:loan_id>', methods=['GET'])
@jwt_required()
def check_loan_payment_status(loan_id):
    # Get authenticated member
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)
    if not member:
        return jsonify({"message": "Member not found"}), 404

    # Fetch the loan
    loan = Loan.query.get(loan_id)
    if not loan:
        return jsonify({"message": "Loan not found"}), 404

    # Ensure the loan belongs to the authenticated member
    if loan.member_id != member.id:
        return jsonify({"message": "You are not authorized to view this loan"}), 403

    # Calculate total repayment amount
    total_repaid = sum([float(r.amount) for r in loan.repayments])

    # Calculate total payable (loan amount + interest)
    loan_amount = float(loan.amount)
    interest_amount = loan_amount * (float(loan.interest_rate) / 100)
    total_payable = loan_amount + interest_amount

    # Check if loan is fully paid
    is_fully_paid = total_repaid >= total_payable

    return jsonify({
        "loan_id": loan.id,
        "member_id": loan.member_id,
        "original_amount": loan_amount,
        "interest_rate": float(loan.interest_rate),
        "total_payable": round(total_payable, 2),
        "total_repaid": round(total_repaid, 2),
        "is_fully_paid": is_fully_paid  
    })




# {
#   "amount": 5000,
#   "purpose": "Business expansion",
#   "term_months": 6,
#   "guarantor_username": "jane_doe"
# }