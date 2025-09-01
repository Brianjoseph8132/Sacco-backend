from models import Account,db, Member, Transaction
from flask import jsonify,request, Blueprint
from werkzeug.security import generate_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
import re


account_bp = Blueprint("account_bp", __name__)

# Validate Kenyan phone number format
def validate_kenyan_phone_number(phone):
    pattern = r'^\+254\d{9}$'  # +254 followed by exactly 9 digits
    if not re.match(pattern, phone):
        return False
    return True


MIN_DEPOSIT = 100.0

# create account 
@account_bp.route("/create_account", methods=["POST"])
@jwt_required()
def create_account():
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)

    if not member:  
        return jsonify({"error": "Member not found"}), 404  

    if member.account:
        return jsonify({"error": "Member already has a bank account"}), 400

    data = request.get_json()
    initial_deposit = float(data.get('initial_deposit', 0.0))
    pin = data.get('pin')
    phone = data.get('phone')
    occupation = data.get('occupation')
    id_number = data.get("id_number")

    # validate pin
    if not pin:
        return jsonify({"error": "Pin is required"}), 400

    # Ensure pin is a 4-digit number 
    if not pin.isdigit() or len(pin) != 4:
        return jsonify({"error": "Pin must be a 4-digit number"}), 400

    # Validate deposit amount  
    if initial_deposit < MIN_DEPOSIT:
        return jsonify({"error": f"Minimum deposit is {MIN_DEPOSIT}"}), 400

    # Phone validation (Kenyan phone number validation)
    if not validate_kenyan_phone_number(phone):
        return jsonify({"error": "Phone number must start with +254 and be followed by 9 digits."}), 400

    # Validation for ID number (should be 9 digits)
    if not isinstance(id_number, int) or len(str(id_number)) != 9:
        return jsonify({"error": "ID number should be exactly 9 digits"}), 400

    # Create new bank account
    new_account = Account(
        balance=initial_deposit, 
        member_id=member.id,
        phone=phone, 
        occupation=occupation,
        id_number=id_number,
    )

    # Set the pin after hashing
    new_account.set_pin(pin)

    db.session.add(new_account)
    db.session.flush()  # This assigns an ID to new_account without committing

    # Record initial deposit if amount > 0
    if initial_deposit > 0:
        transaction = Transaction(
            type="deposit",
            amount=initial_deposit,
            account_id=new_account.id
        )
        db.session.add(transaction)

    db.session.commit()
    
    return jsonify({
        "success": "Account created successfully",
        "account_id": new_account.id,
        "balance": new_account.balance
    }), 201



# has an account(check if a user has a account)
@account_bp.route("/has_account", methods=["GET"])
@jwt_required()
def has_account():
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)

    if not member:
        return jsonify({"error": "Member not found"}), 404

    has_account = member.account is not None 
    return jsonify({"has_account": has_account}), 200




# get the balance of the members account
@account_bp.route("/balance", methods=["GET"])
@jwt_required()
def balance():
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)

    if not member or not member.account:
        return jsonify({"error": "Unauthorized or No Account"}), 401

    return jsonify({"balance": member.account.balance})