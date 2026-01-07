#register_route.py

import random
import requests
import time
from email.mime.text import MIMEText
from flask import Blueprint, request, jsonify
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

from database import db
from model.user import User


load_dotenv()

BREVO_EMAIL = os.getenv("BREVO_EMAIL")
BREVO_SMTP_KEY = os.getenv("BREVO_SMTP_KEY")

register_bp = Blueprint("register", __name__)

# Store OTPs temporarily in memory
otp_store = {}

OTP_EXPIRY_SECONDS = 300  # 5 minutes

# -------------------------------
# Clean expired OTPs
# -------------------------------
def clean_expired_otps():
    current_time = time.time()
    expired = [
        email for email, data in otp_store.items()
        if current_time - data["timestamp"] > OTP_EXPIRY_SECONDS
    ]
    for email in expired:
        del otp_store[email]

# -------------------------------
# Send OTP via Brevo
# -------------------------------
def send_otp_email(receiver_email, otp):
    if not BREVO_SMTP_KEY:
        print("❌ BREVO API KEY NOT SET")
        return False

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": BREVO_SMTP_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": "SUNOG Alert System",
            "email": BREVO_EMAIL
        },
        "to": [
            {"email": receiver_email}
        ],
        "subject": "Your Registration OTP Code",
        "textContent": f"Your OTP code is {otp}. It expires in 5 minutes."
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code not in [200, 201, 202]:
            print("❌ Brevo API Error:", response.text)
            return False

        print(f"✅ OTP sent to {receiver_email}")
        return True

    except Exception as e:
        print("❌ Brevo API Exception:", e)
        return False

# -------------------------------
# Send OTP Route
# -------------------------------
@register_bp.route("/send_otp", methods=["POST"])
def send_otp():
    try:
        clean_expired_otps()

        data = request.get_json(silent=True)
        gmail = data.get("gmail") if data else None

        if not gmail:
            return jsonify({"message": "Gmail is required"}), 400

        if User.query.filter_by(gmail=gmail).first():
            return jsonify({"message": "Gmail already registered"}), 409

        otp = str(random.randint(100000, 999999))

        otp_store[gmail] = {
            "otp": otp,
            "timestamp": time.time()
        }

        if not send_otp_email(gmail, otp):
            return jsonify({"message": "Failed to send OTP"}), 500

        return jsonify({
            "message": "OTP sent successfully",
            "expires_in": OTP_EXPIRY_SECONDS
        }), 200

    except Exception as e:
        print("❌ /send_otp ERROR:", e)
        return jsonify({"message": "Server error"}), 500

# -------------------------------
# Register User Route
# -------------------------------
@register_bp.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"message": "Invalid request"}), 400

        required_fields = ["fullname", "address", "mobile", "gmail", "otp"]
        for field in required_fields:
            if not data.get(field):
                return jsonify({"message": f"{field} is required"}), 400

        gmail = data["gmail"]
        otp = data["otp"]

        stored = otp_store.get(gmail)
        if not stored:
            return jsonify({"message": "OTP not found or expired"}), 400

        if time.time() - stored["timestamp"] > OTP_EXPIRY_SECONDS:
            del otp_store[gmail]
            return jsonify({"message": "OTP expired"}), 400

        if stored["otp"] != otp:
            return jsonify({"message": "Invalid OTP"}), 400

        if User.query.filter_by(gmail=gmail).first():
            return jsonify({"message": "Gmail already exists"}), 409

        new_user = User(
            fullname=data["fullname"],
            address=data["address"],
            mobile=data["mobile"],
            gmail=gmail
        )

        db.session.add(new_user)
        db.session.commit()
        del otp_store[gmail]

        return jsonify({
            "message": "User registered successfully",
            "user_id": new_user.id
        }), 201

    except Exception as e:
        db.session.rollback()
        print("❌ /register ERROR:", e)
        return jsonify({"message": "Registration failed"}), 500
