from models import Member,db, Loan
from flask import jsonify,request, Blueprint
from werkzeug.security import generate_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
import re
from email_validator import validate_email, EmailNotValidError


member_bp = Blueprint("member_bp", __name__)



# Add Member 
@member_bp.route("/members", methods=["POST"])
def add_members():
    data = request.get_json()
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    username = data.get('username')
    email = data.get('email')
    raw_password = data.get('password')
    is_admin = data.get("is_admin", False)
    is_analyst = data.get("is_analyst", False)
    profile_picture = data.get('profile_picture', "https://media.istockphoto.com/id/1337144146/vector/default-avatar-profile-icon-vector.jpg?s=612x612&w=0&k=20&c=BIbFwuv7FxTWvh5S3vB6bkT0Qv8Vn8N5Ffseq84ClGI=")

    # Validation for password length before hashing it
    if not isinstance(raw_password, str) or len(raw_password) != 8:
        return jsonify({"error": "Password must be exactly 8 characters"}), 400
    
    password = generate_password_hash(raw_password)  # Hash the password
    
    # Email validation using email-validator
    try:
        valid_email = validate_email(email)
    except EmailNotValidError as e:
        return jsonify({"error": f"Invalid email address: {str(e)}"}), 400

    
    # Check if username or email already exists
    check_username = Member.query.filter_by(username=username).first()
    check_email = Member.query.filter_by(email=email).first()

    if check_email or check_username:
        return jsonify({"error": "Username or email already exists"}), 400

    # Add new member to the database
    new_member = Member(
        first_name=first_name,
        last_name=last_name,
        username=username,
        email=email,
        password=password,
        is_admin=is_admin,
        is_analyst= is_analyst,
        profile_picture=profile_picture
    )
    db.session.add(new_member)
    db.session.commit()
    return jsonify({"success": "Member added successfully!"}), 200


@member_bp.route('/update_profile', methods=['PUT'])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = Member.query.get(user_id)

    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json()

    if "profile_picture" in data:
        user.profile_picture = data["profile_picture"]
        
    db.session.commit()
    return jsonify({'success': 'Profile updated successfully'}), 200


# Delete Member
def has_unpaid_loans(member_id):
    unpaid_loans = Loan.query.filter_by(member_id=member_id).filter(Loan.status != 'paid').all()
    return len(unpaid_loans) > 0

@member_bp.route('/delete_account/<int:member_id>', methods=['DELETE'])
@jwt_required()
def delete_account(member_id):
    current_user_id = get_jwt_identity()

    if member_id != current_user_id:
        return jsonify({"error": "Unauthorized"}), 403

    member = Member.query.get(current_user_id)
    if not member:
        return jsonify({"error": "Member you are trying to delete doesn't exist"}), 404 

    if has_unpaid_loans(current_user_id):
        return jsonify({'error': 'Cannot delete account with unpaid loans'}), 400

    # Optionally delete related account, transactions, etc.
    db.session.delete(member)
    db.session.commit()
    return jsonify({'message': 'Account deleted successfully'}), 200


# {
#   "username": "Joseph Mwongela",
#   "first_name": "Joseph",
#   "last_name":"Mwongela",
#   "email": "joseph@gmail.com",
#   "password": "joseph12",
#   "is_admin": false,
# }


