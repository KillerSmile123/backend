from flask import Blueprint, request, jsonify
from backend.model.admin_model import Admin
from backend.database import db

login_bp = Blueprint('login_bp', __name__)

@login_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'message': 'Email and password are required'}), 400

    admin = Admin.query.filter_by(email=email).first()

    if admin and admin.check_password(password):
        return jsonify({
            'message': 'Login successful',
            'admin': admin.to_dict(),
            'token': 'dummy-token'  # Replace with real JWT if needed
        }), 200
    else:
        return jsonify({'message': 'Invalid credentials'}), 401
