# userauth_route.py
import random
import requests
import time
import uuid
import os
from flask import Blueprint, request, jsonify, send_file
from dotenv import load_dotenv
from database import db
from model.user import User

load_dotenv()

BREVO_EMAIL = os.getenv("BREVO_EMAIL")
BREVO_SMTP_KEY = os.getenv("BREVO_SMTP_KEY")

auth_bp = Blueprint('auth_bp', __name__)

# Store OTPs temporarily in memory (use Redis in production)
login_otp_store = {}
OTP_EXPIRY_SECONDS = 600  # 10 minutes
MAX_OTP_ATTEMPTS = 5

# --------------------------
# HELPER FUNCTIONS
# --------------------------
def clean_expired_login_otps():
    """Remove expired OTPs from memory"""
    current_time = time.time()
    expired = [
        email for email, data in login_otp_store.items()
        if current_time - data["timestamp"] > OTP_EXPIRY_SECONDS
    ]
    for email in expired:
        del login_otp_store[email]

def send_login_otp_email(receiver_email, otp):
    """Send OTP via Brevo API"""
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
        "subject": "S.U.N.O.G - Your Login OTP Code",
        "htmlContent": f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; border: 3px solid #800000;">
                <h2 style="color: #800000; text-align: center;">S.U.N.O.G Login Verification</h2>
                <p>Hello,</p>
                <p>Your One-Time Password (OTP) for login is:</p>
                <div style="background-color: #f8f8f8; padding: 20px; text-align: center; font-size: 32px; font-weight: bold; color: #800000; letter-spacing: 5px; border-radius: 8px; margin: 20px 0;">
                    {otp}
                </div>
                <p><strong>This OTP will expire in 10 minutes.</strong></p>
                <p>If you didn't request this OTP, please ignore this email.</p>
                <hr style="border: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #666; text-align: center;">
                    This is an automated email. Please do not reply.
                </p>
            </div>
        </div>
        """
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

        print(f"✅ Login OTP sent to {receiver_email}")
        return True

    except Exception as e:
        print("❌ Brevo API Exception:", e)
        return False

# --------------------------
# SEND LOGIN OTP ROUTE
# --------------------------
@auth_bp.route('/send-otp', methods=['POST'])
def send_login_otp():
    """Send OTP to user's email for login"""
    try:
        clean_expired_login_otps()

        data = request.get_json()
        gmail = data.get("gmail")

        if not gmail:
            return jsonify({"success": False, "message": "Gmail is required"}), 400

        # Check if user exists
        user = User.query.filter_by(gmail=gmail).first()
        if not user:
            return jsonify({
                "success": False,
                "message": "User not found. Please register first."
            }), 404

        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # Store OTP with timestamp and attempts counter
        login_otp_store[gmail] = {
            "otp": otp,
            "timestamp": time.time(),
            "attempts": 0
        }

        # Send OTP via Brevo
        if not send_login_otp_email(gmail, otp):
            return jsonify({
                "success": False,
                "message": "Failed to send OTP email"
            }), 500

        # Log OTP for development (REMOVE IN PRODUCTION)
        print(f"🔐 Login OTP for {gmail}: {otp}")

        return jsonify({
            "success": True,
            "message": "OTP sent successfully to your email",
            "expires_in": OTP_EXPIRY_SECONDS
        }), 200

    except Exception as e:
        print(f"❌ /send-otp ERROR: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500

# --------------------------
# VERIFY OTP & LOGIN ROUTE
# --------------------------
@auth_bp.route('/verify-otp', methods=['POST'])
def verify_login_otp():
    """Verify OTP and log user in"""
    try:
        clean_expired_login_otps()

        data = request.get_json()
        gmail = data.get("gmail")
        otp = data.get("otp")

        if not gmail or not otp:
            return jsonify({
                "success": False,
                "message": "Gmail and OTP are required"
            }), 400

        # Check if OTP exists in store
        stored_data = login_otp_store.get(gmail)
        if not stored_data:
            return jsonify({
                "success": False,
                "message": "OTP not found or expired. Please request a new one."
            }), 400

        # Check if OTP is expired
        if time.time() - stored_data["timestamp"] > OTP_EXPIRY_SECONDS:
            del login_otp_store[gmail]
            return jsonify({
                "success": False,
                "message": "OTP has expired. Please request a new one."
            }), 400

        # Check attempts (prevent brute force)
        if stored_data["attempts"] >= MAX_OTP_ATTEMPTS:
            del login_otp_store[gmail]
            return jsonify({
                "success": False,
                "message": "Too many failed attempts. Please request a new OTP."
            }), 429

        # Verify OTP
        if stored_data["otp"] != otp:
            login_otp_store[gmail]["attempts"] += 1
            remaining = MAX_OTP_ATTEMPTS - login_otp_store[gmail]["attempts"]
            return jsonify({
                "success": False,
                "message": f"Invalid OTP. {remaining} attempts remaining."
            }), 400

        # OTP is valid - remove it from store
        del login_otp_store[gmail]

        # Get user from database
        user = User.query.filter_by(gmail=gmail).first()
        if not user:
            return jsonify({
                "success": False,
                "message": "User not found"
            }), 404

        # Generate token (you can use JWT if needed)
        token = str(uuid.uuid4())

        print(f"✅ User {user.fullname} logged in successfully")

        return jsonify({
            "success": True,
            "message": "Login successful",
            "token": token,
            "user": {
                "id": user.id,
                "fullname": user.fullname,
                "address": user.address,
                "gmail": user.gmail,
                "mobile": user.mobile
            }
        }), 200

    except Exception as e:
        print(f"❌ /verify-otp ERROR: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500

# --------------------------
# OLD LOGIN ROUTE (KEEP FOR BACKWARD COMPATIBILITY - OPTIONAL)
# --------------------------
@auth_bp.route('/login-old', methods=['POST'])
def login_old():
    """Old login with mobile number (deprecated - use OTP login)"""
    try:
        data = request.json
        gmail = data.get("gmail")
        mobile = data.get("mobile")

        if not gmail or not mobile:
            return jsonify({"success": False, "message": "Missing credentials"}), 400

        user = User.query.filter_by(gmail=gmail, mobile=mobile).first()

        if not user:
            return jsonify({
                "success": False,
                "message": "Invalid Gmail or Mobile Number"
            }), 401

        token = str(uuid.uuid4())

        return jsonify({
            "success": True,
            "message": "Login successful",
            "token": token,
            "user": {
                "id": user.id,
                "fullname": user.fullname,
                "address": user.address,
                "gmail": user.gmail,
                "mobile": user.mobile
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --------------------------
# GET USER INFO BY EMAIL
# --------------------------
@auth_bp.route('/user/<gmail>', methods=['GET'])
def get_user_info(gmail):
    try:
        user = User.query.filter_by(gmail=gmail).first()
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        return jsonify({
            "success": True,
            "user": {
                "id": user.id,
                "fullname": user.fullname,
                "address": user.address,
                "gmail": user.gmail,
                "mobile": user.mobile
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --------------------------
# PROFILE GET / UPDATE
# --------------------------
@auth_bp.route('/api/user/profile/<int:user_id>', methods=['GET'])
def get_user_profile(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "fullname": user.fullname,
        "address": user.address,
        "mobile": user.mobile,
        "gmail": user.gmail,
        "home_address": getattr(user, "home_address", ""),
        "default_map_location": getattr(user, "default_map_location", ""),
        "gps_enabled": getattr(user, "gps_enabled", False),
        "latitude": getattr(user, "latitude", 0.0),
        "longitude": getattr(user, "longitude", 0.0)
    })


@auth_bp.route('/api/user/profile/<int:user_id>', methods=['PUT'])
def update_user_profile(user_id):
    data = request.json
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.fullname = data.get("fullname", user.fullname)
    user.gmail = data.get("gmail", user.gmail)
    user.mobile = data.get("mobile", user.mobile)
    user.home_address = data.get("home_address", getattr(user, "home_address", ""))
    user.default_map_location = data.get("default_map_location", getattr(user, "default_map_location", ""))
    user.gps_enabled = data.get("gps_enabled", getattr(user, "gps_enabled", False))
    if "coords" in data:
        user.latitude = data["coords"]["lat"]
        user.longitude = data["coords"]["lng"]

    db.session.commit()
    return jsonify({"message": "Profile updated successfully"})


# --------------------------
# CHANGE PASSWORD
# --------------------------
@auth_bp.route('/api/user/change-password/<int:user_id>', methods=['PUT'])
def change_password(user_id):
    data = request.json
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.password != data.get("old_password"):
        return jsonify({"error": "Old password incorrect"}), 400

    user.password = data.get("new_password")
    db.session.commit()
    return jsonify({"message": "Password changed successfully"})


# --------------------------
# CHANGE PROFILE PICTURE
# --------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BACKEND_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@auth_bp.route('/api/user/profile-picture/<int:user_id>', methods=['POST'])
def change_profile_picture(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    file = request.files.get("profile_picture")
    if file:
        filename = f"profile_{user_id}.png"
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        user.profile_picture = filename
        db.session.commit()
        return jsonify({"message": "Profile picture updated"})
    return jsonify({"error": "No file uploaded"}), 400


# --------------------------
# NOTIFICATIONS SETTINGS
# --------------------------
@auth_bp.route('/api/user/notifications/<int:user_id>', methods=['PUT'])
def update_notifications(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.json
    user.notifications = data  # You can store as JSON in DB
    db.session.commit()
    return jsonify({"message": "Notification settings updated"})


# --------------------------
# DELETE ACCOUNT
# --------------------------
@auth_bp.route('/api/user/<int:user_id>', methods=['DELETE'])
def delete_account(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account deleted successfully"})