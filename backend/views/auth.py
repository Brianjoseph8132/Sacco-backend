from models import Member,db, TokenBlocklist
from flask import jsonify,request, Blueprint
from werkzeug.security import check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from datetime import datetime
from datetime import timedelta
from datetime import timezone


auth_bp = Blueprint("auth_bp", __name__)


# LOGIN
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    member = Member.query.filter_by(email=email).first()

    if member and check_password_hash(member.password, password):
        access_token = create_access_token(identity=member.id)
        return jsonify({
            "access_token": access_token,
            "is_admin": member.is_admin
        }), 200
    else:
        return jsonify({"error": "Either email/password is incorrect"}), 404


# Current User
@auth_bp.route("/current_user", methods=["GET"])
@jwt_required()
def current_user():
    current_user_id = get_jwt_identity()
    member = Member.query.get(current_user_id)
    member_data ={
            'id':member.id,
            'email':member.email,
            'username':member.username,
            'is_admin':member.is_admin
        }

    return jsonify(member_data)


# Logout
@auth_bp.route("/logout", methods=["DELETE"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    now = datetime.now(timezone.utc)
    db.session.add(TokenBlocklist(jti=jti, created_at=now))
    db.session.commit()
    return jsonify({"success":"Logged out successfully"})