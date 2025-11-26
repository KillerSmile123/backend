# backend/model/admin_model.py

from backend.database import db  # ✅ Import db FIRST
from werkzeug.security import generate_password_hash, check_password_hash

class Admin(db.Model):
    __tablename__ = 'admins'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # If not using hash, keep it simple
    name = db.Column(db.String(100), nullable=True)

    def __init__(self, email, password, name=None):
        self.email = email
        self.password = password  # ← no hashing if you disabled it
        self.name = name

    def check_password(self, password):
        return self.password == password  # ← simple check, no hash used

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name
        }
