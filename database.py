#databsase.py

from flask_sqlalchemy import SQLAlchemy
from flask import Flask

db = SQLAlchemy()

def init_db(app: Flask):
    # Railway MySQL credentials
    user = "root"
    password = "EkWtqIHFUsYPygWVBVisnJMoBLmLSnlc"
    host = "mainline.proxy.rlwy.net"
    port = "11651"
    name = "railway"

    # SQLAlchemy connection string
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Optional: test connection
    try:
        with app.app_context():
            db.engine.connect()
            print("Connected to Railway MySQL successfully!")
    except Exception as e:
        print("Database connection error:", e)
