from flask import Flask, jsonify, request, render_template
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
from model.alert_model import Alert  # ✅ Add this import

from node_coordinates import node_coords

from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)

# CORS config - MUST come before registering blueprints
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

# Uploads
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ===== Init DB with Railway MySQL =====
init_db(app)

# Register Blueprints with URL prefixes to avoid conflicts
app.register_blueprint(auth_bp, url_prefix='/user')        # User routes
app.register_blueprint(login_bp)      # Admin routes
app.register_blueprint(register_bp)
app.register_blueprint(alert_bp)

#Dijkstra
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

# ===== 🚨 Fire Alert Endpoint (UPDATED to save to database) =====
@app.route('/send_alert', methods=['POST', 'OPTIONS'])
def send_alert():
    # Handle preflight OPTIONS request
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

        # Save files
        photo_filename = None
        video_filename = None
        
        if photo:
            photo_filename = photo.filename
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
            
        if video:
            video_filename = video.filename
            video.save(os.path.join(app.config['UPLOAD_FOLDER'], video_filename))

        # ✅ Save to database
        new_alert = Alert(
            description=description,
            latitude=float(latitude),
            longitude=float(longitude),
            photo_filename=photo_filename,
            video_filename=video_filename
        )
        
        db.session.add(new_alert)
        db.session.commit()

        print("🔥 Fire Alert Saved to Database!")
        print(f"Alert ID: {new_alert.id}")
        print("Description:", description)
        print("Location:", latitude, longitude)
        print("Photo:", photo_filename if photo_filename else 'None')
        print("Video:", video_filename if video_filename else 'None')

        return jsonify({
            'message': 'Fire alert received successfully',
            'alert_id': new_alert.id
        }), 200

    except Exception as e:
        print("❌ Error:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

# ✅ NEW: Get all alerts for admin dashboard
@app.route('/get_alerts', methods=['GET', 'OPTIONS'])
def get_alerts():
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        # Fetch alerts from database (most recent first)
        alerts = Alert.query.order_by(Alert.timestamp.desc()).all()
        
        # Convert to JSON format
        alerts_list = []
        for alert in alerts:
            alerts_list.append({
                'id': alert.id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'photo_filename': alert.photo_filename,
                'video_filename': alert.video_filename,
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

# ===== ✅ Admin Resolved Alerts Page =====
@app.route('/alertResolve')
def admin_resolve():
    return render_template('alertResolve.html')

# ===== Health Check =====
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


# ===== Error Handlers =====
@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'Internal server error'}), 500

# ===== Create Tables =====
with app.app_context():
    db.create_all()

# ===== Run App =====
if __name__ == '__main__':
    app.run(port=5000, debug=True)