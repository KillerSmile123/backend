from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import os
import traceback

# Import your database setup
from database import init_db, db
from route.register_route import register_bp
from route.alert_route import alert_bp
from route.adminauth_route import login_bp
from model.user import User

app = Flask(
    __name__,
    template_folder='sunog_User/templates',
    static_folder='sunog_User/static'
)

# CORS config
CORS(app, supports_credentials=True)

# Secret key
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Uploads
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ===== Init DB with Railway MySQL =====
init_db(app)

# Register Blueprints
app.register_blueprint(register_bp)
app.register_blueprint(alert_bp)
app.register_blueprint(login_bp)

# ===== 🚨 Fire Alert Endpoint =====
@app.route('/send_alert', methods=['POST'])
def send_alert():
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

        photo_filename = os.path.join(app.config['UPLOAD_FOLDER'], photo.filename) if photo else None
        video_filename = os.path.join(app.config['UPLOAD_FOLDER'], video.filename) if video else None

        if photo: photo.save(photo_filename)
        if video: video.save(video_filename)

        # Log alert (or save to DB if needed)
        print("🔥 Fire Alert Received!")
        print("Description:", description)
        print("Location:", latitude, longitude)
        print("Photo:", photo.filename if photo else 'None')
        print("Video:", video.filename if video else 'None')

        return jsonify({'message': 'Fire alert received successfully'}), 200

    except Exception as e:
        print("❌ Error:", str(e))
        traceback.print_exc()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

# ===== ✅ Admin Resolved Alerts Page =====
@app.route('/alertResolve')
def admin_resolve():
    return render_template('alertResolve.html')

# ===== Health Check =====
@app.route('/health')
def health_check():
    try:
        db.session.execute('SELECT 1')
        db_status = 'connected'
    except:
        db_status = 'disconnected'

    return jsonify({
        'status': 'healthy',
        'database': db_status,
        'cors': 'enabled'
    })

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
    app.run(host='127.0.0.1', port=8000, debug=True)
