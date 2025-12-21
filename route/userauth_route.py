from flask import Blueprint, request, jsonify, send_file
from database import db
from model.user import User
import uuid
import os

auth_bp = Blueprint('auth_bp', __name__)

# --------------------------
# LOGIN ROUTE
# --------------------------
@auth_bp.route('/login', methods=['POST'])
def login():
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
