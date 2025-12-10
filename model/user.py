# backend/model/user.py

from database import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100))
    address = db.Column(db.String(255))
    mobile = db.Column(db.String(15))
    gmail = db.Column(db.String(100), unique=True)


    def __repr__(self):
        return f'<User {self.email}>'
