from models import Transaction,db,Member
from flask import jsonify,request, Blueprint
from werkzeug.security import generate_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from werkzeug.security import check_password_hash


transaction_bp = Blueprint("transaction_bp", __name__)

# transaction
@transaction_bp.route("/transaction", methods=["POST"])
@jwt_required()
def transaction():
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)

    if not member:
        return jsonify({"error": "User not found"}), 404

    if not member.account:
        return jsonify({"error": "No account found"}), 404

    data = request.get_json()
    action = data.get("action")
    amount = data.get("amount")
    pin = data.get("pin")  # pin provided by the user for transaction

    if not pin:
        return jsonify({"error": "Pin is required"}), 400

    # Verify if the provided pin matches the stored hashed pin
    if not check_password_hash(member.account.pin, pin):
        return jsonify({"error": "Incorrect pin"}), 401

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400

    if action == "deposit":
        member.account.deposit(amount)
        db.session.commit()
        return jsonify({"success": "Deposit successful"}), 200

    elif action == "withdraw":
        if member.account.balance >= amount:
            member.account.withdraw(amount)
            db.session.commit()
            return jsonify({"success": "Withdraw successful"}), 200
        else:
            return jsonify({"error": "Insufficient balance"}), 400

    else:
        return jsonify({"error": "Invalid action"}), 400


# transaction history
@transaction_bp.route("/transaction_history", methods=["GET"])
@jwt_required()
def transaction_history():
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)

    if not member:
        return jsonify({"error": "Member not found"}), 404

    if not member.account:
        return jsonify({"error": "No account found"}), 404

    # Get query parameters for pagination (default to page 1 and 10 transactions per page)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    # Fetch transactions with pagination
    transactions = Transaction.query.filter_by(account_id=member.account.id) \
                                     .paginate(page=page, per_page=per_page, error_out=False)

    # Format the transactions for the response
    transaction_history = [
        {
            "id": transaction.id,
            "type": transaction.type,
            "amount": transaction.amount,
            "timestamp": transaction.timestamp.isoformat(),
        }
        for transaction in transactions.items
    ]

    # Prepare pagination data for the response
    pagination_data = {
        "page": page,
        "per_page": per_page,
        "total": transactions.total,
        "pages": transactions.pages,
    }

    return jsonify({
        "transactions": transaction_history,
        "pagination": pagination_data
    }), 200