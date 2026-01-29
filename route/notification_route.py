# notification_route.py - UPDATED with real database
from flask import Blueprint, request, jsonify
from datetime import datetime
from functools import wraps
from sqlalchemy import text
from database import db
import traceback

notification_bp = Blueprint('notifications', __name__)

# Simple auth check (you can enhance this later)
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # For now, we'll skip strict auth since your app uses localStorage userId
        # You can add JWT or session auth later
        return f(*args, **kwargs)
    return decorated_function

# ========================================
# GET ALL NOTIFICATIONS FOR A USER
# ========================================
@notification_bp.route('/get_user_notifications/<user_id>', methods=['GET', 'OPTIONS'])
def get_user_notifications(user_id):
    """Get all notifications for a specific user"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        with db.engine.connect() as conn:
            query = text("""
                SELECT * FROM notifications 
                WHERE user_id = :user_id 
                ORDER BY timestamp DESC
            """)
            result = conn.execute(query, {'user_id': user_id})
            
            notifications = []
            for row in result:
                notifications.append({
                    'id': row.id,
                    'user_id': row.user_id,
                    'type': row.type,
                    'title': row.title,
                    'message': row.message,
                    'alertId': row.alert_id,
                    'alertLocation': row.alert_location,
                    'resolveTime': row.resolve_time,
                    'timestamp': row.timestamp.isoformat() if row.timestamp else None,
                    'read': bool(row.read)
                })
        
        return jsonify({
            'success': True,
            'notifications': notifications,
            'count': len(notifications)
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting notifications: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========================================
# MARK NOTIFICATION AS READ
# ========================================
@notification_bp.route('/mark_notification_read/<notification_id>', methods=['POST', 'OPTIONS'])
def mark_notification_read(notification_id):
    """Mark a specific notification as read"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        with db.engine.connect() as conn:
            query = text("""
                UPDATE notifications 
                SET `read` = TRUE 
                WHERE id = :notification_id
            """)
            conn.execute(query, {'notification_id': notification_id})
            conn.commit()
        
        print(f"✅ Notification {notification_id} marked as read")
        
        return jsonify({
            'success': True,
            'message': 'Notification marked as read'
        }), 200
        
    except Exception as e:
        print(f"❌ Error marking notification as read: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========================================
# MARK ALL NOTIFICATIONS AS READ
# ========================================
@notification_bp.route('/mark-all-read', methods=['POST', 'OPTIONS'])
def mark_all_read():
    """Mark all notifications as read for a user"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'user_id is required'
            }), 400
        
        with db.engine.connect() as conn:
            query = text("""
                UPDATE notifications 
                SET `read` = TRUE 
                WHERE user_id = :user_id AND `read` = FALSE
            """)
            result = conn.execute(query, {'user_id': user_id})
            conn.commit()
            updated_count = result.rowcount
        
        print(f"✅ Marked {updated_count} notifications as read for user {user_id}")
        
        return jsonify({
            'success': True,
            'message': f'{updated_count} notifications marked as read',
            'updated_count': updated_count
        }), 200
        
    except Exception as e:
        print(f"❌ Error marking all as read: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========================================
# DELETE NOTIFICATION
# ========================================
@notification_bp.route('/<notification_id>', methods=['DELETE', 'OPTIONS'])
def delete_notification(notification_id):
    """Delete a specific notification"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        with db.engine.connect() as conn:
            # Check if notification exists
            check_query = text("SELECT id FROM notifications WHERE id = :id")
            result = conn.execute(check_query, {'id': notification_id})
            
            if not result.fetchone():
                return jsonify({
                    'success': False,
                    'error': 'Notification not found'
                }), 404
            
            # Delete notification
            delete_query = text("DELETE FROM notifications WHERE id = :id")
            conn.execute(delete_query, {'id': notification_id})
            conn.commit()
        
        print(f"✅ Notification {notification_id} deleted")
        
        return jsonify({
            'success': True,
            'message': 'Notification deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting notification: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========================================
# GET UNREAD COUNT
# ========================================
@notification_bp.route('/count/<user_id>', methods=['GET', 'OPTIONS'])
def get_unread_count(user_id):
    """Get count of unread notifications for a user"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        with db.engine.connect() as conn:
            query = text("""
                SELECT COUNT(*) as unread_count 
                FROM notifications 
                WHERE user_id = :user_id AND `read` = FALSE
            """)
            result = conn.execute(query, {'user_id': user_id})
            row = result.fetchone()
            unread_count = row.unread_count if row else 0
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'unread_count': unread_count
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting unread count: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========================================
# BULK DELETE NOTIFICATIONS
# ========================================
@notification_bp.route('/bulk-delete', methods=['POST', 'OPTIONS'])
def bulk_delete_notifications():
    """Delete multiple notifications"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.get_json()
        notification_ids = data.get('notification_ids', [])
        
        if not notification_ids:
            return jsonify({
                'success': False,
                'error': 'notification_ids array is required'
            }), 400
        
        with db.engine.connect() as conn:
            # Convert list to comma-separated string for SQL IN clause
            placeholders = ','.join([f':id_{i}' for i in range(len(notification_ids))])
            params = {f'id_{i}': nid for i, nid in enumerate(notification_ids)}
            
            query = text(f"DELETE FROM notifications WHERE id IN ({placeholders})")
            result = conn.execute(query, params)
            conn.commit()
            deleted_count = result.rowcount
        
        print(f"✅ Deleted {deleted_count} notifications")
        
        return jsonify({
            'success': True,
            'message': f'{deleted_count} notifications deleted',
            'deleted_count': deleted_count
        }), 200
        
    except Exception as e:
        print(f"❌ Error bulk deleting notifications: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500