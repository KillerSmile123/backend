from database import db
from datetime import datetime

class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.String(100), primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'response', 'resolved', 'deleted'
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    alert_id = db.Column(db.String(100), nullable=True)
    alert_location = db.Column(db.String(200), nullable=True)
    resolve_time = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)