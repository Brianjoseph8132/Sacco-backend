from models import Notification,db,Member
from flask import jsonify,request, Blueprint
from werkzeug.security import generate_password_hash
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from sqlalchemy import desc 


notification_bp = Blueprint("notification_bp", __name__)


# get notification
@notification_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_user_notifications():
    """Get paginated notifications for the authenticated user"""
    current_user_id = get_jwt_identity()
    
    # Pagination and filtering
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    unread_only = request.args.get('unread', '').lower() == 'true'
    notification_type = request.args.get('type')
    loan_id = request.args.get('loan_id')

    query = Notification.query.filter_by(recipient_username=current_user_id)

    if unread_only:
        query = query.filter_by(is_read=False)
    if notification_type:
        query = query.filter_by(type=notification_type)
    if loan_id:
        query = query.filter_by(loan_id=loan_id)

    notifications = query.order_by(desc(Notification.timestamp))\
                       .paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "notifications": [{
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "is_read": n.is_read,
            "timestamp": n.timestamp.isoformat(),
            "loan_id": n.loan_id,
            "sender": {
                "username": n.sender.username,
                "name": f"{n.sender.first_name} {n.sender.last_name}"
            } if n.sender else None
        } for n in notifications.items],
        "meta": {
            "total": notifications.total,
            "pages": notifications.pages,
            "current_page": notifications.page,
            "unread_count": Notification.query.filter_by(
                recipient_username=current_user_id,
                is_read=False
            ).count()
        }
    })


# Mark Notification as Read
@notification_bp.route('/read/<int:notification_id>', methods=['PATCH'])
@jwt_required()
def mark_notification_read(notification_id):
    """Mark a specific notification as read"""
    current_user_id = get_jwt_identity()
    notification = Notification.query.get(notification_id)

    if not notification:
        return jsonify({'error': 'Notification not found'}), 404

    notification.is_read = True
    db.session.commit()

    return jsonify({"success": "Notification marked as read"}), 200


# Mark All Notifications as Read
@notification_bp.route('/read-all', methods=['PATCH'])
@jwt_required()
def mark_all_notifications_read():
    """Mark all user notifications as read"""
    current_user_id = get_jwt_identity()
    
    updated_count = Notification.query.filter_by(
        recipient_username=current_user_id,
        is_read=False
    ).update({'is_read': True})

    db.session.commit()
    return jsonify({
        "success": f"Marked {updated_count} notifications as read"
    }), 200


# Get Unread Notifications Count
@notification_bp.route('/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count():
    """Get count of unread notifications"""
    current_user_id = get_jwt_identity()
    
    count = Notification.query.filter_by(
        recipient_username=current_user_id,
        is_read=False
    ).count()

    return jsonify({"count": count}), 200



# Delete notification
@notification_bp.route('/notification/<int:notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    """Delete a specific notification"""
    current_user_id = get_jwt_identity()
    notification = Notification.query.get(notification_id)

    if not notification:
        return jsonify({'message': 'Notification not found'}), 404

    db.session.delete(notification)
    db.session.commit()

    return jsonify({"success": "Notification deleted successfully"}), 200