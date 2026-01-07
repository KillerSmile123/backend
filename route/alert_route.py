# alert_route.py
from flask import request, Blueprint, send_file, jsonify
from database import db
from model.alert_model import Alert
import os
import traceback

# ✅ Import Cloudinary functions
from cloudinary_config import upload_to_cloudinary, delete_from_cloudinary

alert_bp = Blueprint('alert', __name__)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BACKEND_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --------------------------
# SEND ALERT (WITH CLOUDINARY)
# --------------------------
@alert_bp.route('/send_alert', methods=['POST', 'OPTIONS'])
def send_alert():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        description = request.form.get('description')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        
        # Get barangay and reporter name
        barangay = request.form.get('barangay')
        reporter_name = request.form.get('reporter_name')
        
        # ✅ NEW: Get user_id from form
        user_id = request.form.get('user_id')
        
        photo = request.files.get('photo')
        video = request.files.get('video')

        print(f"📥 Received alert submission:")
        print(f"  User ID: {user_id}")  # ✅ NEW
        print(f"  Description: {description}")
        print(f"  Barangay: {barangay}")
        print(f"  Reporter: {reporter_name}")
        print(f"  Latitude: {latitude}, Longitude: {longitude}")

        if not latitude or not longitude:
            return jsonify({'message': 'Location is required'}), 400
        if not photo and not video:
            return jsonify({'message': 'At least a photo or a video is required'}), 400

        # ✅ Upload to Cloudinary
        photo_url = None
        video_url = None
        
        if photo:
            print(f"📤 Uploading photo to Cloudinary: {photo.filename}")
            photo_result = upload_to_cloudinary(photo, folder="fire_alerts/photos", resource_type="image")
            if photo_result['success']:
                photo_url = photo_result['url']
                print(f"✅ Photo uploaded successfully!")
                print(f"   URL: {photo_url}")
            else:
                print(f"❌ Photo upload failed: {photo_result['error']}")
                return jsonify({'message': 'Photo upload failed', 'error': photo_result['error']}), 500
            
        if video:
            print(f"📤 Uploading video to Cloudinary: {video.filename}")
            video_result = upload_to_cloudinary(video, folder="fire_alerts/videos", resource_type="video")
            if video_result['success']:
                video_url = video_result['url']
                print(f"✅ Video uploaded successfully!")
                print(f"   URL: {video_url}")
            else:
                print(f"❌ Video upload failed: {video_result['error']}")
                return jsonify({'message': 'Video upload failed', 'error': video_result['error']}), 500

        # ✅ Save to database with Cloudinary URLs AND user_id
        new_alert = Alert(
            user_id=int(user_id) if user_id else None,  # ✅ NEW: Save user_id
            description=description,
            latitude=float(latitude),
            longitude=float(longitude),
            photo_filename=photo_url,  # Full Cloudinary URL
            video_filename=video_url,  # Full Cloudinary URL
            barangay=barangay,
            reporter_name=reporter_name
        )
        
        db.session.add(new_alert)
        db.session.commit()

        print("✅ Fire Alert Saved to Database!")
        print(f"   Alert ID: {new_alert.id}")
        print(f"   User ID: {new_alert.user_id}")  # ✅ NEW

        return jsonify({
            'message': 'Fire alert received successfully',
            'alert_id': new_alert.id,
            'user_id': new_alert.user_id,  # ✅ NEW
            'photo_url': photo_url,
            'video_url': video_url,
            'timestamp': new_alert.timestamp.isoformat() if new_alert.timestamp else None
        }), 200

    except Exception as e:
        print("❌ Error in send_alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500


# --------------------------
# CLEAR ALERT HISTORY
# --------------------------
@alert_bp.route('/api/alerts/user/<int:user_id>', methods=['DELETE'])
def clear_alerts(user_id):
    alerts = Alert.query.filter_by(user_id=user_id).all()
    for alert in alerts:
        db.session.delete(alert)
    db.session.commit()
    return {"message": "Alert history cleared"}


# --------------------------
# DOWNLOAD FIRE CONTACTS PDF
# --------------------------
@alert_bp.route('/api/fire/contacts/pdf', methods=['GET'])
def download_contacts_pdf():
    path = os.path.join(BACKEND_DIR, "docs/contacts.pdf")
    if not os.path.exists(path):
        return {"error": "PDF not found"}, 404
    return send_file(path, as_attachment=True)