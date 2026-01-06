from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
import os
import traceback

from sqlalchemy import text

from dijkstra import dijkstra
from graph_data import road_graph

# Import your database setup
from database import init_db, db
from route.register_route import register_bp
from route.alert_route import alert_bp
from route.adminauth_route import login_bp
from route.userauth_route import auth_bp
from model.user import User
from model.alert_model import Alert

from node_coordinates import node_coords

from dotenv import load_dotenv

# ✅ Import Cloudinary functions
from cloudinary_config import init_cloudinary, upload_to_cloudinary, delete_from_cloudinary

load_dotenv()

app = Flask(__name__)

# CORS config
CORS(app, supports_credentials=True,
     resources={r"/*": {
         "origins": [
             "https://sunog-user.onrender.com", 
             "https://sunog-admin.onrender.com",
             "http://localhost:3000",
             "http://localhost:5000"
         ],
         "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         "allow_headers": ["Content-Type", "Authorization"]
     }})

# Secret key
app.config['SECRET_KEY'] = '88e8c79a3e05967c39b69b6d9ae86f04d418a4f59fa84c4eadf6506e56f34672'

# ✅ Initialize Cloudinary and verify configuration
try:
    init_cloudinary()
    print("✅ Cloudinary initialized successfully!")
    print(f"Cloud Name: {os.getenv('CLOUDINARY_CLOUD_NAME')}")
except Exception as e:
    print(f"❌ Cloudinary initialization failed: {e}")
    print("Please check your .env file has:")
    print("  CLOUDINARY_CLOUD_NAME=your_cloud_name")
    print("  CLOUDINARY_API_KEY=your_api_key")
    print("  CLOUDINARY_API_SECRET=your_api_secret")

# Uploads folder (keep for backward compatibility if needed)
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Init DB with Railway MySQL
init_db(app)

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/user')
app.register_blueprint(login_bp)
app.register_blueprint(register_bp)
app.register_blueprint(alert_bp)

# Dijkstra route
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

# ✅ UPDATED Fire Alert Endpoint with Cloudinary
@app.route('/send_alert', methods=['POST', 'OPTIONS'])
def send_alert():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        description = request.form.get('description')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        
        # ✅ Get new fields (barangay and reporter name)
        barangay = request.form.get('barangay')
        reporter_name = request.form.get('reporter_name')
        
        photo = request.files.get('photo')
        video = request.files.get('video')

        app.logger.info(f"📥 Received alert submission:")
        app.logger.info(f"  Description: {description}")
        app.logger.info(f"  Barangay: {barangay}")
        app.logger.info(f"  Reporter: {reporter_name}")
        app.logger.info(f"  Latitude: {latitude}, Longitude: {longitude}")

        if not latitude or not longitude:
            return jsonify({'message': 'Location is required'}), 400
        if not photo and not video:
            return jsonify({'message': 'At least a photo or a video is required'}), 400

        # ✅ Upload to Cloudinary
        photo_url = None
        video_url = None
        
        if photo:
            app.logger.info(f"📤 Uploading photo to Cloudinary: {photo.filename}")
            photo_result = upload_to_cloudinary(photo, folder="fire_alerts/photos", resource_type="image")
            if photo_result['success']:
                photo_url = photo_result['url']
                app.logger.info(f"✅ Photo uploaded successfully!")
            else:
                return jsonify({'message': 'Photo upload failed', 'error': photo_result['error']}), 500
            
        if video:
            app.logger.info(f"📤 Uploading video to Cloudinary: {video.filename}")
            video_result = upload_to_cloudinary(video, folder="fire_alerts/videos", resource_type="video")
            if video_result['success']:
                video_url = video_result['url']
                app.logger.info(f"✅ Video uploaded successfully!")
            else:
                return jsonify({'message': 'Video upload failed', 'error': video_result['error']}), 500

        # ✅ Save to database with new fields
        new_alert = Alert(
            description=description,
            latitude=float(latitude),
            longitude=float(longitude),
            photo_filename=photo_url,
            video_filename=video_url,
            barangay=barangay,  # ✅ New field
            reporter_name=reporter_name  # ✅ New field
        )
        
        db.session.add(new_alert)
        db.session.commit()

        app.logger.info("✅ Fire Alert Saved to Database!")

        return jsonify({
            'message': 'Fire alert received successfully',
            'alert_id': new_alert.id,
            'photo_url': photo_url,
            'video_url': video_url,
            'timestamp': new_alert.timestamp.isoformat() if new_alert.timestamp else None
        }), 200

    except Exception as e:
        print("❌ Error in send_alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

# ✅ Get all alerts
# ========================================
# REPLACE your existing /get_alerts endpoint with this:
# ========================================

@app.route('/get_alerts', methods=['GET', 'OPTIONS'])
def get_alerts():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        # ✅ Only get unresolved alerts (active alerts)
        alerts = Alert.query.filter_by(resolved=False).order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in alerts:
            alerts_list.append({
                'id': alert.id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'location': alert.barangay,  # Frontend expects 'location'
                'photo_filename': alert.photo_filename,
                'video_filename': alert.video_filename,
                'photo_url': alert.photo_filename,
                'video_url': alert.video_filename,
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'status': 'Pending'
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


# ========================================
# ADD these NEW endpoints after /get_alerts:
# ========================================

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


@app.route('/resolve_alert/<int:alert_id>', methods=['POST', 'OPTIONS'])
def resolve_alert(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'message': 'Alert not found'}), 404
        
        from datetime import datetime
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
    
# ✅ Delete alert endpoint (also deletes from Cloudinary)
@app.route('/delete_alert/<int:alert_id>', methods=['DELETE', 'OPTIONS'])
def delete_alert(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'message': 'Alert not found'}), 404
        
        print(f"🗑️ Deleting alert {alert_id}")
        
        # Delete photo from Cloudinary
        if alert.photo_filename and 'cloudinary.com' in alert.photo_filename:
            try:
                # Extract public_id from URL
                parts = alert.photo_filename.split('/')
                if 'fire_alerts' in parts:
                    idx = parts.index('fire_alerts')
                    public_id = '/'.join(parts[idx:]).split('.')[0]
                    result = delete_from_cloudinary(public_id, resource_type="image")
                    print(f"  Photo deletion: {result}")
            except Exception as e:
                print(f"  ⚠️ Photo deletion failed: {e}")
        
        # Delete video from Cloudinary
        if alert.video_filename and 'cloudinary.com' in alert.video_filename:
            try:
                parts = alert.video_filename.split('/')
                if 'fire_alerts' in parts:
                    idx = parts.index('fire_alerts')
                    public_id = '/'.join(parts[idx:]).split('.')[0]
                    result = delete_from_cloudinary(public_id, resource_type="video")
                    print(f"  Video deletion: {result}")
            except Exception as e:
                print(f"  ⚠️ Video deletion failed: {e}")
        
        # Delete from database
        db.session.delete(alert)
        db.session.commit()
        
        print(f"✅ Alert {alert_id} deleted successfully")
        return jsonify({'message': 'Alert deleted successfully'}), 200
        
    except Exception as e:
        print("❌ Error deleting alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

# Serve uploaded files (backward compatibility)
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
        "cors": "enabled"
    })

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'Internal server error'}), 500

# Create Tables
with app.app_context():
    db.create_all()
    print("✅ Database tables created/verified")

# Run App
if __name__ == '__main__':
    print("🚀 Starting Flask app...")
    print(f"📍 Running on http://localhost:5000")
    app.run(port=5000, debug=True)