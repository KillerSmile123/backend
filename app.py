#app.py

from flask import Flask, jsonify, request, render_template, send_from_directory, Response, stream_with_context
from flask_cors import CORS
import os
import traceback
from datetime import datetime, timedelta, timezone
import json
import time
import math
from queue import Queue
from threading import Lock

from sqlalchemy import text

from dijkstra import dijkstra
from graph_data import road_graph

# Import your database setup
from model.user import User
from model.alert_model import Alert
from model.notification_model import Notification  
from database import init_db, db
from route.register_route import register_bp
from route.alert_route import alert_bp
from route.adminauth_route import login_bp
from route.userauth_route import auth_bp
from route.notification_route import notification_bp

from node_coordinates import node_coords

from dotenv import load_dotenv

# Import Cloudinary functions
from cloudinary_config import init_cloudinary, upload_to_cloudinary, delete_from_cloudinary

load_dotenv()

# Philippine timezone is UTC+8
PHILIPPINE_OFFSET = timedelta(hours=8)
PHILIPPINE_TZ = timezone(PHILIPPINE_OFFSET)

def get_philippine_time():
    """Get current time in Philippine timezone (UTC+8)"""
    return datetime.now(PHILIPPINE_TZ)

def get_philippine_time_iso():
    """Get current time in Philippine timezone as ISO string"""
    return get_philippine_time().isoformat()

def get_philippine_timestamp():
    """Get current timestamp in Philippine timezone"""
    return int(get_philippine_time().timestamp())



app = Flask(__name__)

# CORS config
CORS(
    app,
    supports_credentials=True,
    resources={
        r"/*": {
            "origins": [
                "https://sunog-user.onrender.com",
                "https://sunog-admin.onrender.com",
                "http://localhost:*",
                "http://127.0.0.1:*"
            ],
            "allow_headers": ["*"],  # ✅ Allow all headers (simpler)
            "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "expose_headers": ["Content-Type"],
            "max_age": 3600
        }
    }
)

# Secret key
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')


# Initialize Cloudinary
try:
    init_cloudinary()
    print("✅ Cloudinary initialized successfully!")
    print(f"Cloud Name: {os.getenv('CLOUDINARY_CLOUD_NAME')}")
except Exception as e:
    print(f"❌ Cloudinary initialization failed: {e}")

# Uploads folder
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Init DB
init_db(app)

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/user')
app.register_blueprint(login_bp)
app.register_blueprint(register_bp)
app.register_blueprint(alert_bp)
app.register_blueprint(notification_bp, url_prefix='/notifications')


# ========================================
# SSE NOTIFICATION SYSTEM
# ========================================

# Store active SSE connections for each user
# Format: {user_id: [Queue(), Queue(), ...]}
active_sse_connections = {}
sse_lock = Lock()

def add_sse_connection(user_id, queue):
    """Add a new SSE connection for a user"""
    with sse_lock:
        if user_id not in active_sse_connections:
            active_sse_connections[user_id] = []
        active_sse_connections[user_id].append(queue)
        print(f"📡 SSE connection added for user {user_id}. Total: {len(active_sse_connections[user_id])}")

def remove_sse_connection(user_id, queue):
    """Remove an SSE connection for a user"""
    with sse_lock:
        if user_id in active_sse_connections:
            try:
                active_sse_connections[user_id].remove(queue)
                if not active_sse_connections[user_id]:
                    del active_sse_connections[user_id]
                print(f"📡 SSE connection removed for user {user_id}")
            except ValueError:
                pass

def send_sse_notification(user_id, notification_data):
    """Send notification to all active SSE connections for a user"""
    with sse_lock:
        if user_id in active_sse_connections:
            dead_queues = []
            for queue in active_sse_connections[user_id]:
                try:
                    queue.put(notification_data)
                    print(f"📤 SSE notification sent to user {user_id}")
                except:
                    dead_queues.append(queue)
            
            # Clean up dead connections
            for dead_queue in dead_queues:
                try:
                    active_sse_connections[user_id].remove(dead_queue)
                except ValueError:
                    pass

# app.py - FIXED SSE Endpoint

@app.route('/sse/notifications/<user_id>')
def sse_notifications(user_id):
    """
    SSE endpoint for real-time notifications
    Client connects here to receive notifications instantly
    """
    def event_stream():
        queue = Queue()
        add_sse_connection(user_id, queue)
        
        try:
            # Send initial connection confirmation
            yield f"data: {json.dumps({'type': 'connected', 'message': 'SSE connection established'})}\n\n"
            
            # Keep connection alive and send notifications
            while True:
                try:
                    # Wait for notification with timeout
                    notification = queue.get(timeout=30)
                    yield f"data: {json.dumps(notification)}\n\n"
                except:
                    # Send heartbeat every 30 seconds to keep connection alive
                    yield f": heartbeat\n\n"
                    
        except GeneratorExit:
            print(f"📡 SSE connection closed for user {user_id}")
        except Exception as e:
            print(f"❌ SSE error for user {user_id}: {e}")
        finally:
            remove_sse_connection(user_id, queue)
    
    response = Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream'
    )
    
    # ✅ FIXED: Use specific origin instead of wildcard
    origin = request.headers.get('Origin', 'https://sunog-user.onrender.com')
    
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Connection'] = 'keep-alive'
    response.headers['Access-Control-Allow-Origin'] = origin  # ✅ Specific origin
    response.headers['Access-Control-Allow-Credentials'] = 'true'  # ✅ Allow credentials
    
    return response


# ========================================
# SSE HEALTH CHECK
# ========================================

@app.route('/sse/health')
def sse_health():
    """Check SSE system status"""
    with sse_lock:
        return jsonify({
            'active_connections': len(active_sse_connections),
            'connected_users': list(active_sse_connections.keys()),
            'total_connections': sum(len(queues) for queues in active_sse_connections.values())
        })


# ========================================
# NOTIFICATION HELPER FUNCTIONS (UPDATED)
# ========================================

def save_notification(notification_data):
    """
    Save notification to database AND send via SSE
    """
    try:
        # Ensure all required fields exist
        notification_data.setdefault('resolve_time', None)
        
        # Save to database
        with db.engine.connect() as conn:
            query = text("""
                INSERT INTO notifications 
                (id, user_id, type, title, message, alert_id, alert_location, resolve_time, timestamp, `read`)
                VALUES 
                (:id, :user_id, :type, :title, :message, :alert_id, :alert_location, :resolve_time, :timestamp, :read)
            """)
            conn.execute(query, notification_data)
            conn.commit()
        
        print(f"✅ Notification saved: {notification_data['id']}")
        
        # 🔥 NEW: Send via SSE to connected clients
        user_id = notification_data.get('user_id')
        if user_id and user_id != 'unknown':
            send_sse_notification(user_id, notification_data)
            print(f"📡 SSE notification broadcasted to user {user_id}")
        
    except Exception as e:
        print(f"❌ Error saving notification: {e}")
        traceback.print_exc()


def get_notifications_by_user(user_id):
    """Get all notifications for a user"""
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
            
            return notifications
    except Exception as e:
        print(f"❌ Error getting notifications: {e}")
        return []


def mark_notification_as_read(notification_id):
    """Mark a notification as read"""
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
    except Exception as e:
        print(f"❌ Error marking notification as read: {e}")


def haversine_distance(coord1, coord2):
    """Calculate distance between two lat/lng coordinates in km"""
    R = 6371  # Earth's radius in km
    
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def find_nearest_node(target_lat, target_lng, node_coords):
    """Find the nearest node in the graph to the given coordinates"""
    min_distance = float('inf')
    nearest_node = None
    
    for node, coords in node_coords.items():
        distance = haversine_distance([target_lat, target_lng], coords)
        if distance < min_distance:
            min_distance = distance
            nearest_node = node
    
    return nearest_node, min_distance

# ========================================
# DIJKSTRA ROUTE
# ========================================

@app.route('/get_alert_route', methods=['GET', 'OPTIONS'])
def get_alert_route():
    """Calculate shortest route from fire station to alert location"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        # Get alert coordinates
        alert_lat = float(request.args.get('lat'))
        alert_lng = float(request.args.get('lng'))
        
        print(f"🚒 Calculating route to: {alert_lat}, {alert_lng}")
        
        # Fire station coordinates
        fire_station_coords = [8.476776975907958, 123.7968330650085]
        
        # Find nearest nodes to fire station and alert location
        start_node, start_dist = find_nearest_node(
            fire_station_coords[0], 
            fire_station_coords[1], 
            node_coords
        )
        
        end_node, end_dist = find_nearest_node(
            alert_lat, 
            alert_lng, 
            node_coords
        )
        
        print(f"📍 Nearest node to Fire Station: {start_node} ({start_dist:.3f} km away)")
        print(f"📍 Nearest node to Alert: {end_node} ({end_dist:.3f} km away)")
        
        # Calculate shortest path using Dijkstra
        path_nodes = dijkstra(road_graph, start_node, end_node)
        
        if not path_nodes:
            return jsonify({
                'success': False,
                'error': 'No route found'
            }), 404
        
        # Convert node names to coordinates
        route_coords = []
        
        # Add actual fire station as first point
        route_coords.append({
            'lat': fire_station_coords[0],
            'lng': fire_station_coords[1],
            'label': 'Fire Station'
        })
        
        # Add path nodes
        for i, node in enumerate(path_nodes):
            coords = node_coords[node]
            route_coords.append({
                'lat': coords[0],
                'lng': coords[1],
                'label': node,
                'isJunction': True
            })
        
        # Add actual alert location as last point
        route_coords.append({
            'lat': alert_lat,
            'lng': alert_lng,
            'label': 'Fire Incident'
        })
        
        # Calculate total distance
        total_distance = start_dist  # Fire station to first node
        for i in range(len(path_nodes) - 1):
            node1 = path_nodes[i]
            node2 = path_nodes[i + 1]
            if node2 in road_graph[node1]:
                total_distance += road_graph[node1][node2]
        total_distance += end_dist  # Last node to alert
        
        print(f"✅ Route calculated: {len(route_coords)} points, {total_distance:.2f} km")
        
        return jsonify({
            'success': True,
            'route': route_coords,
            'path_nodes': path_nodes,
            'total_distance': round(total_distance, 2),
            'start_node': start_node,
            'end_node': end_node
        }), 200
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': 'Invalid coordinates'
        }), 400
    except Exception as e:
        print(f"❌ Error calculating route: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/get-shortest-route')
def get_shortest_route():
    start = request.args.get('start')
    end = request.args.get('end')

    path = dijkstra(road_graph, start, end)

    if not path:
        return jsonify({"error": "No path found"}), 404

    try:
        coords = [node_coords[node] for node in path]
    except KeyError as e:
        return jsonify({"error": f"Missing node coordinate: {e}"}), 500

    return jsonify(coords)


# ========================================
# ALERTS ENDPOINTS
# ========================================

@app.route('/get_alerts', methods=['GET', 'OPTIONS'])
def get_alerts():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alerts = Alert.query.filter_by(resolved=False).order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in alerts:
            alerts_list.append({
                'id': alert.id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'location': alert.barangay,
                'photo_filename': alert.photo_filename,
                'video_filename': alert.video_filename,
                'photo_url': alert.photo_filename,
                'video_url': alert.video_filename,
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'status': 'resolved' if alert.resolved else 'pending',
                'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
            })
        
        print(f"📋 Retrieved {len(alerts_list)} active alerts")
        
        return jsonify({
            'alerts': alerts_list,
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print("❌ Error fetching alerts:", str(e))
        traceback.print_exc()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500


@app.route('/get_resolved_alerts', methods=['GET', 'OPTIONS'])
def get_resolved_alerts():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        resolved_alerts = Alert.query.filter_by(resolved=True).order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in resolved_alerts:
            alerts_list.append({
                'id': alert.id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'location': alert.barangay,
                'photo_url': alert.photo_filename,
                'video_url': alert.video_filename,
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'resolvedAt': alert.resolved_at.isoformat() if alert.resolved_at else None,
                'resolve_time': alert.resolve_time,
                'status': 'Resolved'
            })
        
        print(f"📋 Retrieved {len(alerts_list)} resolved alerts")
        
        return jsonify({
            'resolved': alerts_list,
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print("❌ Error fetching resolved alerts:", str(e))
        traceback.print_exc()
        return jsonify({
            'resolved': [],
            'count': 0
        }), 200


# ========================================
# ADMIN ACTION ENDPOINTS (WITH SSE)
# ========================================

@app.route('/respond_alert', methods=['POST', 'OPTIONS'])
def respond_alert():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json
        alert_id = data.get('alert_id')
        message = data.get('message')
        
        if not alert_id or not message:
            return jsonify({'error': 'Missing required fields'}), 400
        
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        if not alert.user_id:
            print(f"⚠️ Warning: Alert {alert_id} has no user_id")
            alert.admin_response = message
            alert.responded_at = get_philippine_time()  # ✅ FIXED
            alert.status = 'received'
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Response saved (no user to notify)'
            }), 200
        
        # Update alert with Philippine time
        alert.admin_response = message
        alert.responded_at = get_philippine_time()  # ✅ FIXED
        alert.status = 'received'
        db.session.commit()
        
        # Create notification with Philippine time
        notification_data = {
            'id': f'notif_{alert_id}_{get_philippine_timestamp()}',  # ✅ FIXED
            'user_id': str(alert.user_id),
            'type': 'response',
            'title': '🚒 Fire Station Response',
            'message': message,
            'alert_id': str(alert_id),
            'alert_location': alert.barangay or f"{alert.latitude}, {alert.longitude}",
            'timestamp': get_philippine_time_iso(),  # ✅ FIXED
            'read': False,
            'resolve_time': None
        }
        
        save_notification(notification_data)
        
        print(f"✅ Real-time notification sent to user {alert.user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Response sent and user notified in real-time!',
            'user_id': alert.user_id
        }), 200
        
    except Exception as e:
        print(f"❌ Error responding to alert: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/resolve_alert_with_time', methods=['POST', 'OPTIONS'])
def resolve_alert_with_time():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json
        alert_id = data.get('alert_id')
        resolve_time = data.get('resolve_time')
        
        if not alert_id or not resolve_time:
            return jsonify({'error': 'Missing required fields'}), 400
        
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        # Update alert with Philippine time
        alert.status = 'resolved'
        alert.resolved = True
        alert.resolved_at = get_philippine_time()  # ✅ FIXED
        alert.resolve_time = resolve_time
        db.session.commit()
        
        # Create notification with Philippine time
        notification_data = {
            'id': f'notif_{alert_id}_{get_philippine_timestamp()}',  # ✅ FIXED
            'user_id': str(alert.user_id) if alert.user_id else 'unknown',
            'type': 'resolved',
            'title': '✅ Fire Alert Resolved',
            'message': f'Fire at {alert.barangay or "your location"} has been extinguished at {resolve_time}.',
            'alert_id': str(alert_id),
            'alert_location': alert.barangay or f"{alert.latitude}, {alert.longitude}",
            'resolve_time': resolve_time,
            'timestamp': get_philippine_time_iso(),  # ✅ FIXED
            'read': False
        }
        
        save_notification(notification_data)
        
        print(f"✅ Alert {alert_id} resolved - real-time notification sent")
        
        return jsonify({
            'success': True,
            'message': 'Alert resolved and user notified!'
        }), 200
        
    except Exception as e:
        print(f"❌ Error resolving alert: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/delete_alert/<alert_id>', methods=['DELETE', 'OPTIONS'])
def delete_alert_new(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        user_id = str(alert.user_id) if alert.user_id else 'unknown'
        location = alert.barangay or f"{alert.latitude}, {alert.longitude}"
        
        # Create notification with Philippine time
        notification_data = {
            'id': f'notif_{alert_id}_{get_philippine_timestamp()}',  # ✅ FIXED
            'user_id': user_id,
            'type': 'deleted',
            'title': '🗑️ Alert Removed',
            'message': f'Your fire alert at {location} has been removed from the system.',
            'alert_id': str(alert_id),
            'timestamp': get_philippine_time_iso(),  # ✅ FIXED
            'read': False,
            'resolve_time': None
        }
        
        save_notification(notification_data)
        
        # Delete media from Cloudinary
        if alert.photo_filename and 'cloudinary.com' in alert.photo_filename:
            try:
                parts = alert.photo_filename.split('/')
                if 'fire_alerts' in parts:
                    idx = parts.index('fire_alerts')
                    public_id = '/'.join(parts[idx:]).split('.')[0]
                    delete_from_cloudinary(public_id, resource_type="image")
            except Exception as e:
                print(f"⚠️ Photo deletion failed: {e}")
        
        if alert.video_filename and 'cloudinary.com' in alert.video_filename:
            try:
                parts = alert.video_filename.split('/')
                if 'fire_alerts' in parts:
                    idx = parts.index('fire_alerts')
                    public_id = '/'.join(parts[idx:]).split('.')[0]
                    delete_from_cloudinary(public_id, resource_type="video")
            except Exception as e:
                print(f"⚠️ Video deletion failed: {e}")
        
        # Delete from database
        db.session.delete(alert)
        db.session.commit()
        
        print(f"✅ Alert {alert_id} deleted - real-time notification sent")
        
        return jsonify({
            'success': True,
            'message': 'Alert deleted and user notified!'
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting alert: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ========================================
# USER NOTIFICATION ENDPOINTS
# ========================================

@app.route('/get_user_notifications/<user_id>', methods=['GET', 'OPTIONS'])
def get_user_notifications(user_id):
    """Get all notifications for a specific user"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        notifications = get_notifications_by_user(user_id)
        
        return jsonify({
            'success': True,
            'notifications': notifications
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting notifications: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/mark_notification_read/<notification_id>', methods=['POST', 'OPTIONS'])
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        mark_notification_as_read(notification_id)
        
        return jsonify({
            'success': True,
            'message': 'Notification marked as read'
        }), 200
        
    except Exception as e:
        print(f"❌ Error marking notification as read: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/get_user_alerts/<user_id>', methods=['GET', 'OPTIONS'])
def get_user_alerts(user_id):
    """Get all alerts for a specific user with their current status"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        # 🔥 FIXED: Filter alerts by user_id
        alerts = Alert.query.filter_by(user_id=user_id).order_by(Alert.timestamp.desc()).all()
        
        if not alerts:
            return jsonify({
                'success': True,
                'alerts': [],
                'message': 'No alerts found for this user'
            }), 200
        
        alert_list = [
            {
                'id': alert.id,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'description': alert.description,
                'reporter_name': alert.reporter_name,
                'barangay': alert.barangay,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'photo_url': alert.photo_filename,
                'video_url': alert.video_filename,
                'admin_response': alert.admin_response,
                'responded_at': alert.responded_at.isoformat() if alert.responded_at else None,
                'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
                'resolve_time': alert.resolve_time,
                'status': alert.status or 'pending'
            }
            for alert in alerts
        ]
        
        print(f"✅ Retrieved {len(alert_list)} alerts for user {user_id}")
        
        return jsonify({
            'success': True,
            'alerts': alert_list
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting user alerts: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ========================================
# EXISTING ENDPOINTS
# ========================================

@app.route('/resolve_alert/<int:alert_id>', methods=['POST', 'OPTIONS'])
def resolve_alert(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'message': 'Alert not found'}), 404
        
        alert.resolved = True
        alert.resolved_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"✅ Alert {alert_id} marked as resolved")
        return jsonify({
            'message': 'Alert marked as resolved',
            'alert_id': alert_id
        }), 200
        
    except Exception as e:
        print("❌ Error resolving alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500


@app.route('/unresolve_alert/<int:alert_id>', methods=['POST', 'OPTIONS'])
def unresolve_alert(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'message': 'Alert not found'}), 404
        
        alert.resolved = False
        alert.resolved_at = None
        
        db.session.commit()
        
        print(f"✅ Alert {alert_id} marked as unresolved")
        return jsonify({
            'message': 'Alert marked as unresolved',
            'alert_id': alert_id
        }), 200
        
    except Exception as e:
        print("❌ Error unresolving alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        print(f"Error serving file {filename}:", e)
        return jsonify({'message': 'File not found'}), 404


@app.route('/alertResolve')
def admin_resolve():
    return render_template('alertResolve.html')


@app.route("/health")
def health():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        print("DB ERROR:", e)
        db_status = "disconnected"

    cloudinary_status = "configured" if os.getenv('CLOUDINARY_CLOUD_NAME') else "not configured"

    return jsonify({
        "status": "healthy",
        "database": db_status,
        "cloudinary": cloudinary_status,
        "cors": "enabled",
        "sse": "enabled"
    })


@app.route('/admin/debug-alerts')
def debug_alerts():
    """Debug what's in the database"""
    try:
        all_alerts = Alert.query.order_by(Alert.timestamp.desc()).limit(5).all()
        
        result = []
        for alert in all_alerts:
            result.append({
                'id': alert.id,
                'timestamp': str(alert.timestamp),
                'photo_filename': alert.photo_filename,
                'is_cloudinary': 'cloudinary.com' in (alert.photo_filename or ''),
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'resolved': alert.resolved
            })
        
        return jsonify({
            'total_alerts': Alert.query.count(),
            'recent_5': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# POST - Admin creates notification
@app.route('/api/admin/notifications', methods=['POST'])
def create_notification():
    data = request.json
    user_id = data.get('user_id')
    message = data.get('message')
    type = data.get('type', 'info')
    
    # Create notification in database
    notification = Notification(
        user_id=user_id,
        message=message,
        type=type,
        is_read=False
    )
    db.session.add(notification)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'notification': notification.to_dict()
    }), 201

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


# PATCH - Mark notification as read
@app.route('/api/notifications/<int:notification_id>/read', methods=['PATCH'])
def mark_as_read(notification_id):
    notification = Notification.query.get(notification_id)
    if notification:
        notification.is_read = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Notification not found'}), 404

# DELETE - Delete notification
@app.route('/api/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    notification = Notification.query.get(notification_id)
    if notification:
        db.session.delete(notification)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Notification not found'}), 404


# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'Internal server error'}), 500

    
# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'Internal server error'}), 500

# Add to app.py
@app.route('/keep-alive')
def keep_alive():
    return jsonify({
        "status": "awake", 
        "timestamp": get_philippine_time_iso()  # ✅ FIXED
    })
# Create Tables
with app.app_context():
    db.create_all()
    print("✅ Database tables created/verified")

# Run App
if __name__ == '__main__':
    print("🚀 Starting Flask app...")
    print(f"📍 Running on http://localhost:5000")
    app.run(port=5000, debug=True)