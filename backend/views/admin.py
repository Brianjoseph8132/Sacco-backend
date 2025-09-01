from models import Account,db, Member, Transaction,LoanRepayment, Loan,Notification
from flask import jsonify,request, Blueprint
from werkzeug.security import generate_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from decorator import admin_required
from datetime import datetime
from sqlalchemy import desc 

admin_bp = Blueprint("admin_bp", __name__)



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



@admin_bp.route('/approve/<int:loan_id>', methods=['PATCH'])
@jwt_required()
@admin_required
def approve_loan(loan_id):
    
    # Verify admin privileges
    current_user_id = get_jwt_identity()
    admin = Member.query.get(current_user_id)
    if not admin or not admin.is_admin:
        return jsonify({"error": "Admin privileges required"}), 403

    # Get loan and validate status
    loan = Loan.query.get_or_404(loan_id)
    if loan.status != 'pending':
        return jsonify({"error": "Loan has already been processed"}), 400

    # Parse request
    data = request.get_json()
    action = data.get('action')
    if action not in ['approve', 'reject']:
        return jsonify({"error": "Invalid action. Use 'approve' or 'reject'"}), 400

    # Process approval/rejection
    if action == 'approve':
        loan.status = 'approved'
        loan.approval_date = datetime.utcnow()
        loan.approved_by = admin.id  

        member_account = Account.query.filter_by(member_id=loan.member_id).first()
        if not member_account:
            return jsonify({"error": "Member account not found"}), 404

        member_account.deposit(float(loan.amount))

        transaction = Transaction(
            type="loan_disbursement",
            amount=float(loan.amount),
            account_id=member_account.id,
            loan_id=loan.id
        )
        db.session.add(transaction)

        notification_message = (
            f"Your loan of {loan.amount} has been approved!\n"
            f"Amount credited: {loan.amount}\n"
            f"New balance: {member_account.balance}\n"
            f"Term_months: {loan.term_months}"
        )
    else:
        loan.status = 'rejected'
        notification_message = (
            f"Your loan application of {loan.amount} has been rejected.\n"
            f"Reason: {data.get('reason', 'Not specified')}"
        )

    notification = Notification(
        recipient_username = loan.borrower.username,
        title=f"Loan {action.title()}",
        message=notification_message,
        type=f"loan_{action}",
        loan_id=loan.id
    )
    db.session.add(notification)

    try:
        db.session.commit()
        return jsonify({
            "success": f"Loan {action} successfully",
            "new_balance": member_account.balance if action == 'approve' else None
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 500


# repayment management
@admin_bp.route('/repayments/<int:repayment_id>', methods=['GET', 'DELETE'])
@jwt_required()
@admin_required
def manage_repayment(repayment_id):
    # Admin verification
    current_user_id = get_jwt_identity()
    current_user = Member.query.get(current_user_id)
    if not current_user or not current_user.is_admin:
        return jsonify({"error": "Admin privileges required"}), 403


    repayment = LoanRepayment.query.get_or_404(repayment_id)
    loan = repayment.loan

    if request.method == 'GET':
        return jsonify({
            "repayment": {
                "id": repayment.id,
                "loan_id": repayment.loan_id,
                "amount": float(repayment.amount),
                "date": repayment.payment_date.isoformat(),
                "method": repayment.payment_method
            },
            "loan_details": {
                "member": loan.member.username,
                "original_amount": float(loan.amount),
                "status": loan.status
            }
        })

    elif request.method == 'DELETE':
        # Recalculate loan status
        db.session.delete(repayment)
        
        # Check if loan status needs to be reverted
        if loan.status == 'paid':
            total_repaid = sum(r.amount for r in loan.repayments if r.id != repayment_id)
            if total_repaid < (loan.amount * (1 + loan.interest_rate/100)):
                loan.status = 'approved'
        
        try:
            db.session.commit()
            return jsonify({"message": "Repayment deleted successfully"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500


#  Admin: Send Notification to Member
@admin_bp.route('/send', methods=['POST'])
@jwt_required()
@admin_required
def send_notification():
    """Send a notification to a specific member (admin only)"""
    current_user_id = get_jwt_identity()
    admin = Member.query.get(current_user_id)
    
    if not admin or not admin.is_admin:
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json()
    required_fields = ['recipient_username', 'title', 'message', 'type']
    if not all(field in data for field in required_fields):
        return jsonify({"error": f"Missing required fields: {', '.join(required_fields)}"}), 400

    notification = Notification(
        recipient_username=data['recipient_username'],
        sender_id=current_user_id,
        title=data['title'],
        message=data['message'],
        type=data['type'],
        loan_id=data.get('loan_id')
    )

    db.session.add(notification)
    db.session.commit()

    return jsonify({
        "success": "Notification sent successfully",
        "notification_id": notification.id
    }), 201



# Admin: Broadcast Notification
@admin_bp.route('/broadcast', methods=['POST'])
@jwt_required()
@admin_required
def broadcast_notification():
    """Broadcast notification to all members (admin only)"""
    current_user_id = get_jwt_identity()
    admin = Member.query.get(current_user_id)
    
    if not admin or not admin.is_admin:
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json()
    required_fields = ['title', 'message', 'type']
    if not all(field in data for field in required_fields):
        return jsonify({"error": f"Missing required fields: {', '.join(required_fields)}"}), 400

    members = Member.query.filter(Member.id != current_user_id).all()
    notifications = []
    
    for member in members:
        notifications.append(Notification(
            recipient_username=member.id,
            sender_id=current_user_id,
            title=data['title'],
            message=data['message'],
            type=data['type'],
            loan_id=data.get('loan_id')
        ))

    db.session.bulk_save_objects(notifications)
    db.session.commit()

    return jsonify({
        "success": f"Notification broadcasted to {len(members)} members"
    }), 201


@admin_bp.route('/admin/notifications', methods=['GET'])
@jwt_required()
@admin_required
def get_admin_notifications():
    """Get notifications meant for admins only"""
    # Verify admin privileges
    current_user_id = get_jwt_identity()
    admin = Member.query.get(current_user_id)
    if not admin or not admin.is_admin:
        return jsonify({"error": "Admin privileges required"}), 403

    # Pagination and filtering
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    notification_type = request.args.get('type')
    is_read = request.args.get('is_read')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Base query: Only notifications where recipient is an admin
    query = Notification.query.join(Member, Notification.recipient_username == Member.id)\
                              .filter(Member.is_admin == True)

    # Apply filters
    if notification_type:
        query = query.filter(Notification.type == notification_type)
    if is_read and is_read.lower() in ['true', 'false']:
        query = query.filter(Notification.is_read == (is_read.lower() == 'true'))
    
    # Date range filter
    if start_date:
        try:
            start_date = datetime.fromisoformat(start_date)
            query = query.filter(Notification.timestamp >= start_date)
        except ValueError:
            return jsonify({"error": "Invalid start_date format (use ISO format)"}), 400
    
    if end_date:
        try:
            end_date = datetime.fromisoformat(end_date)
            query = query.filter(Notification.timestamp <= end_date)
        except ValueError:
            return jsonify({"error": "Invalid end_date format (use ISO format)"}), 400

    # Execute query
    notifications = query.order_by(desc(Notification.timestamp))\
                       .paginate(page=page, per_page=per_page, error_out=False)

    # Build response
    return jsonify({
        "notifications": [{
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "is_read": n.is_read,
            "timestamp": n.timestamp.isoformat(),
            "loan_id": n.loan_id,
            "loan_status": n.loan.status if n.loan else None,
            "recipient": {
                "id": n.recipient.id,
                "username": n.recipient.username,
                "name": f"{n.recipient.first_name} {n.recipient.last_name}"
            } if n.recipient else None,
            "sender": {
                "id": n.sender.id,
                "username": n.sender.username,
                "name": f"{n.sender.first_name} {n.sender.last_name}"
            } if n.sender else None
        } for n in notifications.items],
        "meta": {
            "total": notifications.total,
            "pages": notifications.pages,
            "current_page": notifications.page,
            "filters": {
                "type": notification_type,
                "is_read": is_read,
                "start_date": start_date,
                "end_date": end_date
            }
        }
    })





@admin_bp.route('/loans-repayments', methods=['GET'])
@jwt_required()
@admin_required
def get_loans_with_repayments():
    # Filters from query params
    status_filter = request.args.get('status')
    member_username_filter = request.args.get('member_username')

    # Pagination params
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Base query
    query = Loan.query

    # Apply filters
    if status_filter:
        query = query.filter(Loan.status == status_filter)
    if member_username_filter:
        query = query.join(Member).filter(Member.username.ilike(f"%{member_username_filter}%"))

    # Paginate
    loans_pagination = query.order_by(Loan.application_date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    loans = loans_pagination.items

    result = []
    for loan in loans:
        # Manually access the member's username
        member = Member.query.get(loan.member_id)
        member_username = member.username if member else "Unknown"

        # Calculate totals
        loan_amount = float(loan.amount)
        interest = loan_amount * (float(loan.interest_rate) / 100)
        total_due = loan_amount + interest
        total_repaid = sum(float(r.amount) for r in loan.repayments)
        remaining_balance = max(total_due - total_repaid, 0)

        result.append({
            "loan_id": loan.id,
            "member_username": member_username,
            "original_amount": loan_amount,
            "interest_rate": float(loan.interest_rate),
            "term_months": loan.term_months,
            "purpose": loan.purpose,
            "status": loan.status,
            "application_date": loan.application_date.isoformat() if loan.application_date else None,
            "approval_date": loan.approval_date.isoformat() if loan.approval_date else None,
            "total_due": round(total_due, 2),
            "total_repaid": round(total_repaid, 2),
            "remaining_balance": round(remaining_balance, 2),
            "repayments": [{
                "repayment_id": r.id,
                "amount": float(r.amount),
                "payment_date": r.payment_date.isoformat() if r.payment_date else None,
                "payment_method": r.payment_method
            } for r in loan.repayments]
        })

    return jsonify({
        "loans": result,
        "meta": {
            "total": loans_pagination.total,
            "pages": loans_pagination.pages,
            "current_page": loans_pagination.page,
            "per_page": per_page,
            "filters": {
                "status": status_filter,
                "member_username": member_username_filter
            }
        }
    })



# fetching all members
@admin_bp.route('/members', methods=['GET'])
@jwt_required()
@admin_required
def get_all_members():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    pagination = Member.query.paginate(page=page, per_page=per_page, error_out=False)
    members = []

    for member in pagination.items:
        account = member.account  # Access the related account
        members.append({
            'id': member.id,
            'username': member.username,
            'email': member.email,
            'first_name': member.first_name,
            'last_name': member.last_name,
            'join_date': member.join_date.strftime('%Y-%m-%d'),
            'phone': account.phone if account else None,
            'occupation': account.occupation if account else None,
            'id_number': account.id_number if account else None
        })

    return jsonify({
        'members': members,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': pagination.page
    }), 200