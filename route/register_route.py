import random
import smtplib
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

register_bp = Blueprint('register', __name__)

# Store OTPs temporarily in memory with timestamps
otp_store = {}

OTP_EXPIRY_SECONDS = 300  # 5 minutes

# -------------------------------
# Helper: Clean expired OTPs
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
# Helper: Send OTP via Brevo
# -------------------------------
def send_otp_email(receiver_email, otp):
    msg = MIMEMultipart()
    msg["From"] = "markgodwill15@gmail.com"  # This is the sender displayed to recipients
    msg["To"] = receiver_email
    msg["Subject"] = "Your Registration OTP Code"

    msg.attach(MIMEText(
        f"""
        Your OTP code is: {otp}

        This code will expire in 5 minutes.

        If you did not request this, please ignore this email.
                """,
                "plain"
    ))

    try:
        server = smtplib.SMTP("smtp-relay.brevo.com", 587)
        server.starttls()
        server.login(BREVO_EMAIL, BREVO_SMTP_KEY)
        server.send_message(msg)
        server.quit()
        print(f"✅ OTP sent successfully to {receiver_email}")
        return True
    except Exception as e:
        print("❌ Brevo email error:", e)
        import traceback
        traceback.print_exc()
        return False

# Rest of your code stays the same...
# (send_otp and register routes)

# -------------------------------
# Send OTP Route
# -------------------------------
@register_bp.route("/send_otp", methods=["POST"])
def send_otp():
    clean_expired_otps()

    data = request.get_json()
    gmail = data.get("gmail") if data else None

    if not gmail:
        return jsonify({"message": "Gmail is required"}), 400

    # Check existing user
    if User.query.filter_by(gmail=gmail).first():
        return jsonify({"message": "Gmail already registered"}), 409

    # Generate OTP
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

# -------------------------------
# Register User Route
# -------------------------------
@register_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()

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

    try:
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
        return jsonify({
            "message": "Registration failed",
            "error": str(e)
        }), 500