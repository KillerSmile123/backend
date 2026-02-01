#app.py

from flask import Flask, jsonify, request, render_template, send_from_directory, Response, stream_with_context
from flask_cors import CORS
import os
import requests 
import traceback
from datetime import datetime, timedelta, timezone
import json
import time
import math
from queue import Queue
from threading import Lock
from onesignal_service import send_push_notification

from sqlalchemy import text

# Import your database setup
from model.user import User
from model.admin_model import Admin
from model.alert_model import Alert
from model.notification_model import Notification  
from database import init_db, db
from route.register_route import register_bp
from route.alert_route import alert_bp
from route.adminauth_route import login_bp
from route.userauth_route import auth_bp
from route.notification_route import notification_bp



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
            "origins": "*",  # ✅ Allow ALL origins
            "allow_headers": ["*"],  # ✅ Allow all headers
            "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "expose_headers": ["Content-Type", "Authorization"],
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
app.register_blueprint(notification_bp)


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




# ========================================
# DIJKSTRA ROUTE
# ========================================

@app.route('/get_alert_route', methods=['GET', 'OPTIONS'])
def get_alert_route():
    """Calculate shortest route using OpenRouteService API (OpenStreetMap data)"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        alert_lat = float(request.args.get('lat'))
        alert_lng = float(request.args.get('lng'))
        
        print(f"🚒 Calculating route to: {alert_lat}, {alert_lng}")
        
        # Fire station coordinates
        fire_station_coords = [8.476723719070502, 123.7970718508905]
        
        # Get API key from environment
        api_key = os.getenv('OPENROUTE_API_KEY')
        
        if not api_key:
            print("⚠️ OPENROUTE_API_KEY not set in environment")
            return jsonify({
                'success': False,
                'error': 'OpenRouteService API key not configured. Please add OPENROUTE_API_KEY to your .env file'
            }), 500
        
        # OpenRouteService API endpoint for GeoJSON response
        url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
        
        headers = {
            'Authorization': api_key,
            'Content-Type': 'application/json'
        }
        
        # Coordinates must be in [longitude, latitude] format for ORS
        body = {
            "coordinates": [
                [fire_station_coords[1], fire_station_coords[0]],  # Fire station [lng, lat]
                [alert_lng, alert_lat]  # Alert location [lng, lat]
            ],
            "instructions": False,
            "elevation": False
        }
        
        print(f"📡 Sending request to OpenRouteService...")
        
        # Make API request with timeout
        response = requests.post(url, json=body, headers=headers, timeout=10)
        
        if response.status_code != 200:
            error_data = response.json() if response.content else {}
            print(f"❌ ORS API error {response.status_code}: {error_data}")
            
            if response.status_code == 401:
                error_msg = 'Invalid API key. Please check your OPENROUTE_API_KEY'
            elif response.status_code == 403:
                error_msg = 'API key quota exceeded or forbidden'
            elif response.status_code == 404:
                error_msg = 'No route found between these locations'
            else:
                error_msg = f'Routing service error: {response.status_code}'
            
            return jsonify({
                'success': False,
                'error': error_msg
            }), response.status_code
        
        data = response.json()
        
        # GeoJSON response has features array
        if 'features' not in data or len(data['features']) == 0:
            print(f"❌ No routes found in response")
            return jsonify({
                'success': False,
                'error': 'No route found between these locations'
            }), 404
        
        # Extract route information from GeoJSON
        feature = data['features'][0]
        route_geometry = feature['geometry']['coordinates']
        route_properties = feature['properties']
        route_summary = route_properties.get('summary', {})
        
        # Get distance and duration
        distance_km = route_summary.get('distance', 0) / 1000  # Convert meters to km
        duration_seconds = route_summary.get('duration', 0)
        duration_minutes = duration_seconds / 60
        
        # Convert route coordinates to our format
        route_coords = []
        
        # Add fire station as first point
        route_coords.append({
            'lat': fire_station_coords[0],
            'lng': fire_station_coords[1],
            'label': 'Fire Station',
            'isStart': True
        })
        
        # Add all route points (convert from [lng, lat] to {lat, lng})
        for i, coord in enumerate(route_geometry):
            route_coords.append({
                'lat': coord[1],
                'lng': coord[0],
                'isJunction': i % 5 == 0  # Mark every 5th point as junction for visualization
            })
        
        # Add alert location as last point
        route_coords.append({
            'lat': alert_lat,
            'lng': alert_lng,
            'label': 'Fire Incident',
            'isEnd': True
        })
        
        print(f"✅ Route calculated successfully:")
        print(f"   Distance: {distance_km:.2f} km")
        print(f"   Duration: {duration_minutes:.1f} minutes")
        print(f"   Route points: {len(route_coords)}")
        
        return jsonify({
            'success': True,
            'route': route_coords,
            'total_distance': round(distance_km, 2),
            'estimated_duration': round(duration_minutes, 1),
            'duration_seconds': round(duration_seconds),
            'source': 'OpenRouteService',
            'map_data': 'OpenStreetMap'
        }), 200
        
    except requests.exceptions.Timeout:
        print("❌ Request timeout")
        return jsonify({
            'success': False,
            'error': 'Routing service request timed out. Please try again.'
        }), 504
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return jsonify({
            'success': False,
            'error': 'Could not connect to routing service. Please check your internet connection.'
        }), 503
        
    except ValueError as e:
        print(f"❌ Invalid coordinates: {e}")
        return jsonify({
            'success': False,
            'error': 'Invalid coordinates provided'
        }), 400
    
    except KeyError as e:
        print(f"❌ Missing key in response: {e}")
        return jsonify({
            'success': False,
            'error': f'Invalid response structure: missing {str(e)}'
        }), 500
        
    except Exception as e:
        print(f"❌ Unexpected error calculating route: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


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

        send_push_notification(
            user_id=alert.user_id,
            title='🚒 Fire Station Response',
            message=message,
            data={'alert_id': str(alert_id), 'type': 'response'}
        )
        
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

        send_push_notification(
            user_id=alert.user_id if alert.user_id else None,
            title='✅ Fire Alert Resolved',
            message=f'Fire at {alert.barangay or "your location"} has been extinguished at {resolve_time}.',
            data={'alert_id': str(alert_id), 'type': 'resolved'}
        )
        
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

        send_push_notification(
            user_id=user_id,
            title='🗑️ Alert Removed',
            message=f'Your fire alert at {location} has been removed from the system.',
            data={'alert_id': str(alert_id), 'type': 'deleted'}
        )
        
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


@app.route('/mark_spam/<alert_id>', methods=['POST', 'OPTIONS'])
def mark_spam(alert_id):
    """Mark an alert as spam and move it to spam section"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        user_id = str(alert.user_id) if alert.user_id else 'unknown'
        location = alert.barangay or f"{alert.latitude}, {alert.longitude}"
        
        # Update alert status to spam
        alert.status = 'spam'
        alert.resolved = True  # Mark as resolved to remove from active alerts
        alert.resolved_at = get_philippine_time()
        
        db.session.commit()
        
        # Create notification to inform user
        notification_data = {
            'id': f'notif_{alert_id}_{get_philippine_timestamp()}',
            'user_id': user_id,
            'type': 'spam',
            'title': '⚠️ Alert Marked as Spam',
            'message': f'Your fire alert at {location} has been marked as spam and removed from active alerts.',
            'alert_id': str(alert_id),
            'alert_location': location,
            'timestamp': get_philippine_time_iso(),
            'read': False,
            'resolve_time': None
        }
        
        save_notification(notification_data)

        send_push_notification(
            user_id=user_id,
            title='⚠️ Alert Marked as Spam',
            message=f'Your fire alert at {location} has been marked as spam.',
            data={'alert_id': str(alert_id), 'type': 'spam'}
        )
        
        print(f"✅ Alert {alert_id} marked as spam - real-time notification sent")
        
        return jsonify({
            'success': True,
            'message': 'Alert marked as spam and user notified!'
        }), 200
        
    except Exception as e:
        print(f"❌ Error marking alert as spam: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/get_spam_alerts', methods=['GET', 'OPTIONS'])
def get_spam_alerts():
    """Get all alerts marked as spam"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        spam_alerts = Alert.query.filter_by(status='spam').order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in spam_alerts:
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
                'markedSpamAt': alert.resolved_at.isoformat() if alert.resolved_at else None,
                'status': 'Spam'
            })
        
        print(f"📋 Retrieved {len(alerts_list)} spam alerts")
        
        return jsonify({
            'spam': alerts_list,
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print("❌ Error fetching spam alerts:", str(e))
        traceback.print_exc()
        return jsonify({
            'spam': [],
            'count': 0
        }), 200


@app.route('/restore_spam_alert/<alert_id>', methods=['POST', 'OPTIONS'])
def restore_spam_alert(alert_id):
    """Restore an alert from spam back to active alerts"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        user_id = str(alert.user_id) if alert.user_id else 'unknown'
        location = alert.barangay or f"{alert.latitude}, {alert.longitude}"
        
        # Restore alert to pending status
        alert.status = 'pending'
        alert.resolved = False
        alert.resolved_at = None
        
        db.session.commit()
        
        # Create notification to inform user
        notification_data = {
            'id': f'notif_{alert_id}_{get_philippine_timestamp()}',
            'user_id': user_id,
            'type': 'restored',
            'title': '✅ Alert Restored',
            'message': f'Your fire alert at {location} has been restored and is now active again.',
            'alert_id': str(alert_id),
            'alert_location': location,
            'timestamp': get_philippine_time_iso(),
            'read': False,
            'resolve_time': None
        }
        
        save_notification(notification_data)
        
        print(f"✅ Alert {alert_id} restored from spam - real-time notification sent")
        
        return jsonify({
            'success': True,
            'message': 'Alert restored and user notified!'
        }), 200
        
    except Exception as e:
        print(f"❌ Error restoring alert from spam: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/delete_spam_alert/<alert_id>', methods=['DELETE', 'OPTIONS'])
def delete_spam_alert(alert_id):
    """Permanently delete a spam alert"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
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
        
        print(f"✅ Spam alert {alert_id} permanently deleted")
        
        return jsonify({
            'success': True,
            'message': 'Spam alert permanently deleted!'
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting spam alert: {e}")
        traceback.print_exc()
        db.session.rollback()
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



# Get admin profile
@app.route('/admin/profile/<int:admin_id>', methods=['GET'])
def get_admin_profile(admin_id):
    admin = Admin.query.get(admin_id)
    if not admin:
        return jsonify({'message': 'Admin not found'}), 404
    
    return jsonify(admin.to_dict()), 200

# Update admin profile
@app.route('/admin/profile/<int:admin_id>', methods=['PUT'])
def update_admin_profile(admin_id):
    data = request.get_json()
    admin = Admin.query.get(admin_id)
    
    if not admin:
        return jsonify({'message': 'Admin not found'}), 404
    
    admin.fullname = data.get('fullname', admin.fullname)
    admin.email = data.get('email', admin.email)
    admin.contact = data.get('contact', admin.contact)
    
    db.session.commit()
    
    return jsonify({
        'message': 'Profile updated successfully',
        'admin': admin.to_dict()
    }), 200

# Upload profile picture
@app.route('/admin/upload_picture', methods=['POST'])
def upload_picture():
    if 'profile_picture' not in request.files:
        return jsonify({'message': 'No file uploaded'}), 400
    
    file = request.files['profile_picture']
    admin_id = request.form.get('admin_id')
    
    admin = Admin.query.get(admin_id)
    if not admin:
        return jsonify({'message': 'Admin not found'}), 404
    
    # Create uploads folder if doesn't exist
    import os
    upload_folder = 'static/uploads'
    os.makedirs(upload_folder, exist_ok=True)
    
    # Save file
    filename = f"admin_{admin_id}_{file.filename}"
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)
    
    # Update database
    admin.profile_picture = f'/static/uploads/{filename}'
    db.session.commit()
    
    return jsonify({
        'message': 'Picture uploaded successfully',
        'profile_picture': admin.profile_picture
    }), 200

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