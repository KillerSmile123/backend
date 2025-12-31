from flask import Blueprint, request, jsonify
from model.admin_model import Admin
from database import db

login_bp = Blueprint('login_bp', __name__)

@login_bp.route('/login', methods=['POST'])
def login():
    print("=" * 50)
    print("🔍 LOGIN ROUTE HIT!")
    print("Content-Type:", request.content_type)
    print("Raw Data:", request.data)
    print("Form Data:", request.form)
    print("=" * 50)
    
    data = request.get_json(silent=True)
    print("Parsed JSON:", data)

    if not data:
        print("❌ No JSON data received!")
        return jsonify({'message': 'Invalid JSON'}), 400

    email = data.get('email')
    password = data.get('password')
    
    print(f"Email: {email}")
    print(f"Password: {'***' if password else None}")

    if not email or not password:
        print("❌ Missing email or password!")
        return jsonify({'message': 'Email and password are required'}), 400

    admin = Admin.query.filter_by(email=email).first()
    print(f"Admin found: {admin is not None}")

    if admin and admin.check_password(password):
        print("✅ Login successful!")
        return jsonify({
            'message': 'Login successful',
            'admin': admin.to_dict(),
            'token': 'dummy-token'
        }), 200

    print("❌ Invalid credentials!")
    return jsonify({'message': 'Invalid credentials'}), 401