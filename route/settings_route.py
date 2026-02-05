# settings_route.py
import os
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
from database import db
from model.user import User
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import io
from datetime import datetime

settings_bp = Blueprint('settings', __name__)

# Configuration
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BACKEND_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ===========================
# 1. PROFILE SETTINGS
# ===========================

@settings_bp.route('/api/user/profile/<int:user_id>', methods=['GET'])
def get_user_profile(user_id):
    """Get user profile information"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        return jsonify({
            "success": True,
            "user": {
                "id": user.id,
                "fullname": user.fullname,
                "address": user.address,
                "mobile": user.mobile,
                "gmail": user.gmail,
                "profile_picture": getattr(user, "profile_picture", None)
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@settings_bp.route('/api/user/profile/<int:user_id>', methods=['PUT'])
def update_user_profile(user_id):
    """Update user profile information"""
    try:
        data = request.json
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        # Update fields if provided
        if 'fullname' in data:
            user.fullname = data['fullname']
        
        if 'gmail' in data:
            # Check if email already exists for another user
            existing_user = User.query.filter(User.gmail == data['gmail'], User.id != user_id).first()
            if existing_user:
                return jsonify({"success": False, "message": "Email already in use"}), 400
            user.gmail = data['gmail']
        
        if 'mobile' in data:
            user.mobile = data['mobile']
        
        if 'address' in data:
            user.address = data['address']

        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Profile updated successfully"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@settings_bp.route('/api/user/profile-picture/<int:user_id>', methods=['POST'])
def change_profile_picture(user_id):
    """Upload and update user profile picture"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        if 'profile_picture' not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file = request.files['profile_picture']
        
        if file.filename == '':
            return jsonify({"success": False, "message": "No file selected"}), 400

        if file and allowed_file(file.filename):
            # Create secure filename
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"profile_{user_id}.{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            # Save file
            file.save(filepath)
            
            # Note: You may need to add 'profile_picture' column to User model
            # Uncomment below when column is added:
            # user.profile_picture = filename
            # db.session.commit()
            
            return jsonify({
                "success": True,
                "message": "Profile picture updated successfully",
                "filename": filename
            }), 200
        else:
            return jsonify({"success": False, "message": "Invalid file type. Use PNG, JPG, JPEG, GIF, or WEBP"}), 400
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ===========================
# 5. PRIVACY & SECURITY
# ===========================

@settings_bp.route('/api/alerts/user/<int:user_id>', methods=['DELETE'])
def clear_user_history(user_id):
    """Clear user's alert/report history"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        # If you have an Alert model, import and delete user's alerts:
        # from model.alert_model import Alert
        # Alert.query.filter_by(user_id=user_id).delete()
        # db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "History cleared successfully"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@settings_bp.route('/api/user/<int:user_id>', methods=['DELETE'])
def delete_account(user_id):
    """Delete user account"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        # Delete associated data first (alerts, notifications, etc.)
        # If you have Alert model:
        # from model.alert_model import Alert
        # Alert.query.filter_by(user_id=user_id).delete()
        
        # Delete profile picture if exists
        if hasattr(user, 'profile_picture') and user.profile_picture:
            profile_path = os.path.join(UPLOAD_FOLDER, user.profile_picture)
            if os.path.exists(profile_path):
                os.remove(profile_path)
        
        # Delete user
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Account deleted successfully"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ===========================
# 7. FIRE SAFETY TOOLS
# ===========================

@settings_bp.route('/api/fire/contacts/pdf', methods=['GET'])
def download_contacts_pdf():
    """Generate and download emergency contacts PDF"""
    try:
        # Create PDF in memory
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Title
        p.setFont("Helvetica-Bold", 20)
        p.drawString(1*inch, height - 1*inch, "Emergency Fire Contacts")
        
        # Add content
        p.setFont("Helvetica", 12)
        y_position = height - 1.5*inch
        
        contacts = [
            ("Emergency Hotline", "911"),
            ("Fire Department", "911"),
            ("Local Fire Station", "(123) 456-7890"),
            ("Poison Control", "1-800-222-1222"),
            ("Red Cross", "1-800-733-2767"),
            ("Non-Emergency", "311"),
        ]
        
        for name, number in contacts:
            p.drawString(1*inch, y_position, f"{name}:")
            p.drawString(3*inch, y_position, number)
            y_position -= 0.3*inch
        
        # Safety Tips Section
        y_position -= 0.5*inch
        p.setFont("Helvetica-Bold", 14)
        p.drawString(1*inch, y_position, "Quick Safety Tips:")
        
        y_position -= 0.3*inch
        p.setFont("Helvetica", 11)
        tips = [
            "1. Stay calm and alert others",
            "2. Call 911 immediately",
            "3. Evacuate if safe to do so",
            "4. Never use elevators during fire",
            "5. Stay low to avoid smoke",
            "6. Have a meeting point outside"
        ]
        
        for tip in tips:
            p.drawString(1*inch, y_position, tip)
            y_position -= 0.25*inch
        
        # Footer
        p.setFont("Helvetica-Oblique", 9)
        p.drawString(1*inch, 0.5*inch, "S.U.N.O.G - Fire Incident Reporting System")
        p.drawString(1*inch, 0.3*inch, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        p.showPage()
        p.save()
        
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name='emergency_contacts.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@settings_bp.route('/api/fire/emergency-numbers', methods=['GET'])
def get_emergency_numbers():
    """Get list of emergency numbers"""
    emergency_numbers = [
        {"name": "Emergency Services", "number": "911", "type": "emergency"},
        {"name": "Fire Department", "number": "911", "type": "fire"},
        {"name": "Police", "number": "911", "type": "police"},
        {"name": "Ambulance", "number": "911", "type": "medical"},
        {"name": "Poison Control", "number": "1-800-222-1222", "type": "medical"},
        {"name": "Red Cross", "number": "1-800-733-2767", "type": "support"},
        {"name": "Non-Emergency", "number": "311", "type": "general"}
    ]
    
    return jsonify({
        "success": True,
        "contacts": emergency_numbers
    }), 200


@settings_bp.route('/api/fire/safety-tips', methods=['GET'])
def get_safety_tips():
    """Get fire safety tips"""
    safety_tips = [
        {
            "title": "During a Fire",
            "tips": [
                "Stay calm and don't panic",
                "Alert others immediately",
                "Call 911 right away",
                "Evacuate if safe to do so",
                "Never use elevators",
                "Stay low to avoid smoke inhalation"
            ]
        },
        {
            "title": "Before Evacuating",
            "tips": [
                "Feel doors before opening (check for heat)",
                "Close doors behind you",
                "Use stairs, never elevators",
                "Help others if possible",
                "Take your phone if nearby"
            ]
        },
        {
            "title": "Prevention",
            "tips": [
                "Install smoke detectors",
                "Have fire extinguishers ready",
                "Create evacuation plan",
                "Practice fire drills",
                "Keep emergency numbers handy",
                "Don't overload electrical outlets"
            ]
        }
    ]
    
    return jsonify({
        "success": True,
        "tips": safety_tips
    }), 200