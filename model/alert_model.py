from database import db
from datetime import datetime

class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    
    # ✅ ADD THIS LINE - Link alert to user
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    description = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    photo_filename = db.Column(db.String(500), nullable=True)
    video_filename = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # ✅ Reporter information fields
    barangay = db.Column(db.String(255), nullable=True)
    reporter_name = db.Column(db.String(255), nullable=True)
    
    # ✅ Status and resolution fields
    resolved = db.Column(db.Boolean, default=False, nullable=False)
    admin_response = db.Column(db.Text, nullable=True)
    responded_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolve_time = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=True)
    
    # ✅ ADD THIS - Relationship to User
    user = db.relationship('User', backref='alerts', lazy=True)