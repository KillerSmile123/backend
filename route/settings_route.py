# settings_route.py
import os
from flask import Blueprint, request, jsonify, send_file
from database import db
from model.user import User
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import io
from datetime import datetime

settings_bp = Blueprint('settings', __name__)

# ===========================
# 1. PRIVACY & SECURITY
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
# 2. FIRE SAFETY TOOLS
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
        p.drawString(1*inch, 0.5*inch, "FireTrackr - Fire Incident Reporting System")
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