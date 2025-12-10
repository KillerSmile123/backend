from flask import request, Blueprint
from database import db
from model.alert_model import Alert
import os

alert_bp = Blueprint('alert', __name__)

# Get the absolute path to the backend directory
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BACKEND_DIR, 'uploads')

# Ensure uploads folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@alert_bp.route('/send_alert', methods=['POST'])
def send_alert():
    description = request.form.get('description')

    try:
        latitude = float(request.form.get('latitude') or 0.0)
        longitude = float(request.form.get('longitude') or 0.0)
    except ValueError:
        return {"error": "Invalid or missing location coordinates."}, 400

    photo = request.files.get('photo')
    video = request.files.get('video')

    photo_filename = None
    video_filename = None

    # Save uploaded files if any
    if photo:
        photo_filename = photo.filename
        photo_path = os.path.join(UPLOAD_FOLDER, photo_filename)
        try:
            photo.save(photo_path)
        except Exception as e:
            return {"error": f"Failed to save photo: {str(e)}"}, 500

    if video:
        video_filename = video.filename
        video_path = os.path.join(UPLOAD_FOLDER, video_filename)
        try:
            video.save(video_path)
        except Exception as e:
            return {"error": f"Failed to save video: {str(e)}"}, 500

    # Save to DB
    try:
        alert = Alert(
            description=description,
            latitude=latitude,
            longitude=longitude,
            photo_filename=photo_filename,
            video_filename=video_filename
        )

        db.session.add(alert)
        db.session.commit()
        
        return {"message": "Alert sent successfully!"}, 200
        
    except Exception as e:
        db.session.rollback()
        return {"error": f"Database error: {str(e)}"}, 500