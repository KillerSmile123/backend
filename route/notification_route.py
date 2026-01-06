from flask import Blueprint, request, jsonify
from datetime import datetime
from functools import wraps

notification_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')

# Mock database (replace with actual database in production)
notifications_db = []
notification_id_counter = 1

# Mock authentication decorator (replace with actual auth in production)
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Authorization header required'}), 401
        # Add your actual authentication logic here
        return f(*args, **kwargs)
    return decorated_function

@notification_bp.route('/', methods=['GET'])
@require_auth
def get_notifications():
    """Get all notifications for the authenticated user"""
    user_id = request.args.get('user_id')
    status = request.args.get('status')  # 'read', 'unread', or None for all
    
    filtered_notifications = notifications_db
    
    if user_id:
        filtered_notifications = [n for n in filtered_notifications if n['user_id'] == user_id]
    
    if status:
        is_read = status.lower() == 'read'
        filtered_notifications = [n for n in filtered_notifications if n['is_read'] == is_read]
    
    return jsonify({
        'notifications': filtered_notifications,
        'count': len(filtered_notifications)
    }), 200

@notification_bp.route('/<int:notification_id>', methods=['GET'])
@require_auth
def get_notification(notification_id):
    """Get a specific notification by ID"""
    notification = next((n for n in notifications_db if n['id'] == notification_id), None)
    
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    return jsonify(notification), 200

@notification_bp.route('/', methods=['POST'])
@require_auth
def create_notification():
    """Create a new notification"""
    global notification_id_counter
    
    data = request.get_json()
    
    if not data or 'user_id' not in data or 'message' not in data:
        return jsonify({'error': 'user_id and message are required'}), 400
    
    notification = {
        'id': notification_id_counter,
        'user_id': data['user_id'],
        'title': data.get('title', 'New Notification'),
        'message': data['message'],
        'type': data.get('type', 'info'),  # info, success, warning, error
        'is_read': False,
        'created_at': datetime.utcnow().isoformat(),
        'metadata': data.get('metadata', {})
    }
    
    notifications_db.append(notification)
    notification_id_counter += 1
    
    return jsonify(notification), 201

@notification_bp.route('/<int:notification_id>', methods=['PATCH'])
@require_auth
def update_notification(notification_id):
    """Update a notification (typically to mark as read)"""
    notification = next((n for n in notifications_db if n['id'] == notification_id), None)
    
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    data = request.get_json()
    
    if 'is_read' in data:
        notification['is_read'] = data['is_read']
    
    if 'is_read' in data and data['is_read']:
        notification['read_at'] = datetime.utcnow().isoformat()
    
    return jsonify(notification), 200

@notification_bp.route('/mark-all-read', methods=['POST'])
@require_auth
def mark_all_read():
    """Mark all notifications as read for a user"""
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400
    
    updated_count = 0
    for notification in notifications_db:
        if notification['user_id'] == user_id and not notification['is_read']:
            notification['is_read'] = True
            notification['read_at'] = datetime.utcnow().isoformat()
            updated_count += 1
    
    return jsonify({
        'message': f'{updated_count} notifications marked as read',
        'updated_count': updated_count
    }), 200

@notification_bp.route('/<int:notification_id>', methods=['DELETE'])
@require_auth
def delete_notification(notification_id):
    """Delete a specific notification"""
    global notifications_db
    
    notification = next((n for n in notifications_db if n['id'] == notification_id), None)
    
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    notifications_db = [n for n in notifications_db if n['id'] != notification_id]
    
    return jsonify({'message': 'Notification deleted successfully'}), 200

@notification_bp.route('/bulk-delete', methods=['POST'])
@require_auth
def bulk_delete_notifications():
    """Delete multiple notifications"""
    global notifications_db
    
    data = request.get_json()
    notification_ids = data.get('notification_ids', [])
    
    if not notification_ids:
        return jsonify({'error': 'notification_ids array is required'}), 400
    
    initial_count = len(notifications_db)
    notifications_db = [n for n in notifications_db if n['id'] not in notification_ids]
    deleted_count = initial_count - len(notifications_db)
    
    return jsonify({
        'message': f'{deleted_count} notifications deleted',
        'deleted_count': deleted_count
    }), 200

@notification_bp.route('/count', methods=['GET'])
@require_auth
def get_unread_count():
    """Get count of unread notifications for a user"""
    user_id = request.args.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'user_id parameter is required'}), 400
    
    unread_count = sum(1 for n in notifications_db 
                       if n['user_id'] == user_id and not n['is_read'])
    
    return jsonify({
        'user_id': user_id,
        'unread_count': unread_count
    }), 200