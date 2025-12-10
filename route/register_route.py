import random
import smtplib
import time
from email.mime.text import MIMEText
from flask import Blueprint, request, jsonify, make_response

from database import db
from model.user import User

register_bp = Blueprint('register_bp', __name__)

# Store OTPs temporarily in memory with timestamps
otp_store = {}

# Email configuration
SENDER_EMAIL = "sunogfire15@gmail.com"
SENDER_PASSWORD = "dsvm nsqm nkgt prdp"

def clean_expired_otps():
    """Clean up expired OTPs (older than 5 minutes)"""
    current_time = time.time()
    expired_emails = []
    
    for email, data in otp_store.items():
        if current_time - data['timestamp'] > 300:  # 5 minutes
            expired_emails.append(email)
    
    for email in expired_emails:
        del otp_store[email]

@register_bp.route('/send_gmail_otp', methods=['POST', 'OPTIONS'])
def send_gmail_otp():
    """Send OTP to Gmail with proper CORS handling"""
    
    # Handle preflight OPTIONS request - Flask-CORS handles this automatically
    if request.method == 'OPTIONS':
        return '', 200

    # Clean expired OTPs
    clean_expired_otps()

    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided'}), 400
            
        gmail = data.get('gmail')
        if not gmail:
            return jsonify({'message': 'Gmail is required'}), 400

        # Check if user already exists
        existing_user = User.query.filter_by(gmail=gmail).first()
        if existing_user:
            return jsonify({'message': 'Gmail already registered'}), 409

        # Generate OTP
        otp = str(random.randint(100000, 999999))
        
        # Store OTP with timestamp
        otp_store[gmail] = {
            'otp': otp,
            'timestamp': time.time()
        }

        # Send email
        try:
            msg = MIMEText(f"""
            Your OTP code is: {otp}
            
            This code will expire in 5 minutes.
            
            If you didn't request this, please ignore this email.
            """)
            msg["Subject"] = "Your Registration OTP Code"
            msg["From"] = SENDER_EMAIL
            msg["To"] = gmail

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)

            return jsonify({
                'message': 'OTP sent successfully',
                'otp': otp,  # For demo purposes only - remove in production
                'expires_in': 300  # 5 minutes
            }), 200

        except smtplib.SMTPAuthenticationError:
            return jsonify({'message': 'Email authentication failed'}), 500
        except smtplib.SMTPException as e:
            return jsonify({'message': 'Failed to send email', 'error': str(e)}), 500

    except Exception as e:
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

@register_bp.route('/register', methods=['POST', 'OPTIONS'])
def register():
    """Register user after OTP verification"""
    
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['fullname', 'address', 'mobile', 'gmail']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'message': f'{field} is required'}), 400

        fullname = data.get('fullname')
        address = data.get('address')
        mobile = data.get('mobile')
        gmail = data.get('gmail')

        # Check if user already exists
        if User.query.filter_by(gmail=gmail).first():
            return jsonify({'message': 'Gmail already exists'}), 409

        # Create new user
        new_user = User(
            fullname=fullname,
            address=address,
            mobile=mobile,
            gmail=gmail
        )
        
        db.session.add(new_user)
        db.session.commit()

        # Clean up OTP after successful registration
        if gmail in otp_store:
            del otp_store[gmail]

        return jsonify({
            'message': 'User registered successfully',
            'user_id': new_user.id
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Registration failed', 'error': str(e)}), 500