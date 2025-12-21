from flask import request, Blueprint, send_file
from database import db
from model.alert_model import Alert
import os

alert_bp = Blueprint('alert', __name__)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BACKEND_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --------------------------
# SEND ALERT
# --------------------------
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

    if photo:
        photo_filename = photo.filename
        photo.save(os.path.join(UPLOAD_FOLDER, photo_filename))
    if video:
        video_filename = video.filename
        video.save(os.path.join(UPLOAD_FOLDER, video_filename))

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
