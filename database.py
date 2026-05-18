# database.py
import os
from flask_sqlalchemy import SQLAlchemy
from flask import Flask

db = SQLAlchemy()

def init_db(app: Flask):
    user = os.environ.get('DB_USER', 'root')
    password = os.environ.get('DB_PASSWORD', 'JMrwDaBfVhJpWyIPsvEFraVrhmoEgkld')
    host = os.environ.get('DB_HOST', 'tramway.proxy.rlwy.net')
    port = os.environ.get('DB_PORT', '58046')
    name = os.environ.get('DB_NAME', 'railway')

    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"
        f"?charset=utf8mb4"
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