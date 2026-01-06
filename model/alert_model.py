from database import db
from datetime import datetime

class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    photo_filename = db.Column(db.String(500), nullable=True)
    video_filename = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    barangay = db.Column(db.String(100), nullable=True)
    reporter_name = db.Column(db.String(100), nullable=True)
    
    resolved = db.Column(db.Boolean, default=False, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    # ✅ ADD THESE FIELDS:
    status = db.Column(db.String(50), default='pending', nullable=True)
    admin_response = db.Column(db.Text, nullable=True)
    responded_at = db.Column(db.DateTime, nullable=True)
    resolve_time = db.Column(db.String(50), nullable=True)
    resolved_by = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.String(100), nullable=True)