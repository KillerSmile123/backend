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

# ✅ Initialize Cloudinary
init_cloudinary()

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
        photo = request.files.get('photo')
        video = request.files.get('video')

        if not latitude or not longitude:
            return jsonify({'message': 'Location is required'}), 400
        if not photo and not video:
            return jsonify({'message': 'At least a photo or a video is required'}), 400

        # ✅ Upload to Cloudinary instead of local storage
        photo_url = None
        photo_public_id = None
        video_url = None
        video_public_id = None
        
        if photo:
            photo_result = upload_to_cloudinary(photo, folder="fire_alerts/photos", resource_type="image")
            if photo_result['success']:
                photo_url = photo_result['url']
                photo_public_id = photo_result['public_id']
            else:
                return jsonify({'message': 'Photo upload failed', 'error': photo_result['error']}), 500
            
        if video:
            video_result = upload_to_cloudinary(video, folder="fire_alerts/videos", resource_type="video")
            if video_result['success']:
                video_url = video_result['url']
                video_public_id = video_result['public_id']
            else:
                return jsonify({'message': 'Video upload failed', 'error': video_result['error']}), 500

        # ✅ Save to database with Cloudinary URLs
        new_alert = Alert(
            description=description,
            latitude=float(latitude),
            longitude=float(longitude),
            photo_filename=photo_url,  # Store Cloudinary URL instead of filename
            video_filename=video_url   # Store Cloudinary URL instead of filename
        )
        
        db.session.add(new_alert)
        db.session.commit()

        print("🔥 Fire Alert Saved to Database with Cloudinary!")
        print(f"Alert ID: {new_alert.id}")
        print("Description:", description)
        print("Location:", latitude, longitude)
        print("Photo URL:", photo_url if photo_url else 'None')
        print("Video URL:", video_url if video_url else 'None')

        return jsonify({
            'message': 'Fire alert received successfully',
            'alert_id': new_alert.id,
            'photo_url': photo_url,
            'video_url': video_url
        }), 200

    except Exception as e:
        print("❌ Error:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

# ✅ Get all alerts (already returns URLs from database)
@app.route('/get_alerts', methods=['GET', 'OPTIONS'])
def get_alerts():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alerts = Alert.query.order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in alerts:
            alerts_list.append({
                'id': alert.id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'photo_url': alert.photo_filename,  # Now contains Cloudinary URL
                'video_url': alert.video_filename,  # Now contains Cloudinary URL
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None
            })
        
        return jsonify({
            'alerts': alerts_list,
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print("❌ Error fetching alerts:", str(e))
        traceback.print_exc()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

# ✅ OPTIONAL: Delete alert endpoint (also deletes from Cloudinary)
@app.route('/delete_alert/<int:alert_id>', methods=['DELETE', 'OPTIONS'])
def delete_alert(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'message': 'Alert not found'}), 404
        
        # Delete from Cloudinary if URLs exist
        if alert.photo_filename and 'cloudinary.com' in alert.photo_filename:
            # Extract public_id from URL
            # URL format: https://res.cloudinary.com/cloud_name/image/upload/v123456/fire_alerts/photos/abc123.jpg
            parts = alert.photo_filename.split('/')
            if 'fire_alerts' in parts:
                idx = parts.index('fire_alerts')
                public_id = '/'.join(parts[idx:]).split('.')[0]
                delete_from_cloudinary(public_id, resource_type="image")
        
        if alert.video_filename and 'cloudinary.com' in alert.video_filename:
            parts = alert.video_filename.split('/')
            if 'fire_alerts' in parts:
                idx = parts.index('fire_alerts')
                public_id = '/'.join(parts[idx:]).split('.')[0]
                delete_from_cloudinary(public_id, resource_type="video")
        
        # Delete from database
        db.session.delete(alert)
        db.session.commit()
        
        return jsonify({'message': 'Alert deleted successfully'}), 200
        
    except Exception as e:
        print("❌ Error deleting alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

# Serve uploaded files (keep for backward compatibility with old data)
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

    return jsonify({
        "status": "healthy",
        "database": db_status,
        "cors": "enabled"
    })

@app.route("/api/login", methods=["POST"])
def login():
    ...

@app.route("/api/register", methods=["POST"])
def register():
    ...

@app.route("/api/alert", methods=["POST"])
def create_alert():
    ...

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

# Run App
if __name__ == '__main__':
    app.run(port=5000, debug=True)