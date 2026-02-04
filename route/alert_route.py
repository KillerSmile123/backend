# alert_route.py - COMPLETE VERSION WITH SPAM HANDLING FIX
from flask import request, Blueprint, send_file, jsonify
from database import db
from model.alert_model import Alert
import os
import traceback
import json
from datetime import datetime

from cloudinary_config import upload_to_cloudinary, delete_from_cloudinary

alert_bp = Blueprint('alert', __name__)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BACKEND_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --------------------------
# SEND ALERT (UNIFIED MEDIA)
# --------------------------
@alert_bp.route('/send_alert', methods=['POST', 'OPTIONS'])
def send_alert():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        description = request.form.get('description')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        barangay = request.form.get('barangay')
        reporter_name = request.form.get('reporter_name')
        user_id = request.form.get('user_id')
        
        photos = request.files.getlist('photos')
        videos = request.files.getlist('videos')

        print(f"📥 Received alert submission:")
        print(f"  User ID: {user_id}")
        print(f"  Description: {description}")
        print(f"  Barangay: {barangay}")
        print(f"  Reporter: {reporter_name}")
        print(f"  Latitude: {latitude}, Longitude: {longitude}")
        print(f"  Photos received: {len(photos)}")
        print(f"  Videos received: {len(videos)}")

        if not latitude or not longitude:
            return jsonify({'message': 'Location is required'}), 400
        if not photos and not videos:
            return jsonify({'message': 'At least one photo or video is required'}), 400
        if not user_id:
            print("⚠️ Warning: No user_id provided!")

        photo_urls = []
        for i, photo in enumerate(photos):
            if photo and photo.filename:
                try:
                    print(f"📤 Uploading photo {i+1}/{len(photos)}: {photo.filename}")
                    photo_result = upload_to_cloudinary(
                        photo, 
                        folder="fire_alerts/photos", 
                        resource_type="image"
                    )
                    
                    if photo_result['success']:
                        photo_url = photo_result['url']
                        photo_urls.append(photo_url)
                        print(f"✅ Photo {i+1} uploaded: {photo_url}")
                    else:
                        print(f"❌ Photo {i+1} upload failed: {photo_result['error']}")
                        
                except Exception as e:
                    print(f"❌ Error uploading photo {i+1}: {e}")
                    traceback.print_exc()
        
        video_urls = []
        for i, video in enumerate(videos):
            if video and video.filename:
                try:
                    print(f"📤 Uploading video {i+1}/{len(videos)}: {video.filename}")
                    video_result = upload_to_cloudinary(
                        video, 
                        folder="fire_alerts/videos", 
                        resource_type="video"
                    )
                    
                    if video_result['success']:
                        video_url = video_result['url']
                        video_urls.append(video_url)
                        print(f"✅ Video {i+1} uploaded: {video_url}")
                    else:
                        print(f"❌ Video {i+1} upload failed: {video_result['error']}")
                        
                except Exception as e:
                    print(f"❌ Error uploading video {i+1}: {e}")
                    traceback.print_exc()

        if not photo_urls and not video_urls:
            return jsonify({
                'message': 'Failed to upload media files',
                'error': 'All uploads failed'
            }), 500

        photo_urls_json = json.dumps(photo_urls) if photo_urls else None
        video_urls_json = json.dumps(video_urls) if video_urls else None
        
        print(f"💾 Saving to database:")
        print(f"  Photo URLs: {photo_urls_json}")
        print(f"  Video URLs: {video_urls_json}")

        new_alert = Alert(
            user_id=int(user_id) if user_id else None,
            description=description,
            latitude=float(latitude),
            longitude=float(longitude),
            photo_filename=photo_urls_json,
            video_filename=video_urls_json,
            barangay=barangay,
            reporter_name=reporter_name,
            timestamp=datetime.utcnow(),
            status='pending',
            resolved=False
        )
        
        db.session.add(new_alert)
        db.session.commit()

        print("✅ Fire Alert Saved to Database!")
        print(f"   Alert ID: {new_alert.id}")
        print(f"   User ID: {new_alert.user_id}")
        print(f"   Photos: {len(photo_urls)}, Videos: {len(video_urls)}")

        return jsonify({
            'success': True,
            'message': 'Fire alert received successfully',
            'alert_id': new_alert.id,
            'user_id': new_alert.user_id,
            'photo_urls': photo_urls,
            'photo_count': len(photo_urls),
            'video_urls': video_urls,
            'video_count': len(video_urls),
            'timestamp': new_alert.timestamp.isoformat()
        }), 200

    except Exception as e:
        print("❌ Error in send_alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Server error',
            'error': str(e)
        }), 500


# --------------------------
# GET ALERTS (ACTIVE ONLY - NOT SPAM, NOT RESOLVED)
# --------------------------
@alert_bp.route('/get_alerts', methods=['GET'])
def get_alerts():
    """Return all active alerts (not resolved, not spam)"""
    try:
        # ✅ FIX: Only get alerts that are NOT resolved OR not spam
        alerts = Alert.query.filter_by(resolved=False).order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in alerts:
            photo_urls = []
            if alert.photo_filename:
                try:
                    photo_urls = json.loads(alert.photo_filename)
                    if not isinstance(photo_urls, list):
                        photo_urls = [alert.photo_filename]
                except (json.JSONDecodeError, TypeError):
                    photo_urls = [alert.photo_filename]
            
            video_urls = []
            if alert.video_filename:
                try:
                    video_urls = json.loads(alert.video_filename)
                    if not isinstance(video_urls, list):
                        video_urls = [alert.video_filename]
                except (json.JSONDecodeError, TypeError):
                    video_urls = [alert.video_filename]
            
            alerts_list.append({
                'id': alert.id,
                'user_id': alert.user_id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'photo_urls': photo_urls,
                'video_urls': video_urls,
                'photo_url': photo_urls[0] if photo_urls else None,
                'video_url': video_urls[0] if video_urls else None,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'status': alert.status or 'pending',
                'resolved': alert.resolved,
                'admin_response': alert.admin_response,
                'responded_at': alert.responded_at.isoformat() if alert.responded_at else None
            })
        
        print(f"📋 Retrieved {len(alerts_list)} active alerts")
        return jsonify({
            'success': True,
            'alerts': alerts_list,
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching alerts: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# --------------------------
# MARK ALERT AS SPAM ✅ NEW ROUTE
# --------------------------
@alert_bp.route('/mark_spam/<alert_id>', methods=['POST'])
def mark_spam(alert_id):
    """Mark an alert as spam"""
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        # ✅ FIX: Set status to 'spam' (NOT 'resolved')
        alert.status = 'spam'
        alert.resolved = True  # Move it out of active alerts
        alert.resolved_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"✅ Alert {alert_id} marked as SPAM (status: {alert.status})")
        return jsonify({
            'success': True,
            'message': 'Alert marked as spam successfully',
            'alert_id': alert_id,
            'status': 'spam'
        }), 200
        
    except Exception as e:
        print(f"❌ Error marking alert as spam: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# --------------------------
# GET SPAM ALERTS ✅ NEW ROUTE
# --------------------------
@alert_bp.route('/get_spam_alerts', methods=['GET'])
def get_spam_alerts():
    """Get all alerts marked as spam"""
    try:
        # ✅ Filter by status='spam'
        spam_alerts = Alert.query.filter_by(status='spam').order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in spam_alerts:
            photo_urls = []
            if alert.photo_filename:
                try:
                    photo_urls = json.loads(alert.photo_filename)
                    if not isinstance(photo_urls, list):
                        photo_urls = [alert.photo_filename]
                except (json.JSONDecodeError, TypeError):
                    photo_urls = [alert.photo_filename]
            
            video_urls = []
            if alert.video_filename:
                try:
                    video_urls = json.loads(alert.video_filename)
                    if not isinstance(video_urls, list):
                        video_urls = [alert.video_filename]
                except (json.JSONDecodeError, TypeError):
                    video_urls = [alert.video_filename]
            
            alerts_list.append({
                'id': alert.id,
                'user_id': alert.user_id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'photo_urls': photo_urls,
                'video_urls': video_urls,
                'photo_url': photo_urls[0] if photo_urls else None,
                'video_url': video_urls[0] if video_urls else None,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'status': 'spam',
                'resolved': True,
                'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None
            })
        
        print(f"📋 Retrieved {len(alerts_list)} spam alerts")
        return jsonify({
            'success': True,
            'alerts': alerts_list,
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching spam alerts: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# --------------------------
# MARK ALERT AS RESOLVED
# --------------------------
@alert_bp.route('/resolve_alert/<int:alert_id>', methods=['POST'])
def resolve_alert(alert_id):
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404

        alert.status = 'resolved'
        alert.resolved = True
        alert.resolved_at = datetime.utcnow()

        db.session.commit()

        print(f"✅ Alert {alert_id} marked RESOLVED")

        return jsonify({
            'success': True,
            'message': 'Alert resolved successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        print("❌ Resolve error:", e)
        return jsonify({'error': str(e)}), 500


# --------------------------
# GET RESOLVED ALERTS (NOT SPAM) ✅ FIXED
# --------------------------
@alert_bp.route('/get_resolved_alerts', methods=['GET'])
def get_resolved_alerts():
    """Get all resolved alerts (excluding spam and pending)"""
    try:
        # ✅ FIXED: Only get alerts with status='resolved' 
        # This ensures we exclude both spam (status='spam') and pending (status='pending')
        resolved_alerts = Alert.query.filter(
            Alert.status == 'resolved'
        ).order_by(Alert.resolved_at.desc()).all()
        
        alerts_list = []
        for alert in resolved_alerts:
            photo_urls = []
            if alert.photo_filename:
                try:
                    photo_urls = json.loads(alert.photo_filename)
                    if not isinstance(photo_urls, list):
                        photo_urls = [alert.photo_filename]
                except (json.JSONDecodeError, TypeError):
                    photo_urls = [alert.photo_filename]
            
            video_urls = []
            if alert.video_filename:
                try:
                    video_urls = json.loads(alert.video_filename)
                    if not isinstance(video_urls, list):
                        video_urls = [alert.video_filename]
                except (json.JSONDecodeError, TypeError):
                    video_urls = [alert.video_filename]
            
            alerts_list.append({
                'id': alert.id,
                'user_id': alert.user_id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'photo_urls': photo_urls,
                'video_urls': video_urls,
                'photo_url': photo_urls[0] if photo_urls else None,
                'video_url': video_urls[0] if video_urls else None,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'status': 'resolved',
                'resolved': True,
                'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
                'resolve_time': alert.resolve_time,
                'admin_response': alert.admin_response
            })
        
        print(f"📋 Retrieved {len(alerts_list)} resolved alerts (excluding spam and pending)")
        return jsonify({
            'success': True,
            'resolved': alerts_list,  # ✅ Changed from 'alerts' to 'resolved' to match your JS
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching resolved alerts: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# --------------------------
# GET USER'S ALERTS
# --------------------------
@alert_bp.route('/get_user_alerts/<user_id>', methods=['GET'])
def get_user_alerts(user_id):
    """Get all alerts for a specific user"""
    try:
        alerts = Alert.query.filter_by(user_id=user_id).order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in alerts:
            photo_urls = []
            if alert.photo_filename:
                try:
                    photo_urls = json.loads(alert.photo_filename)
                    if not isinstance(photo_urls, list):
                        photo_urls = [alert.photo_filename]
                except (json.JSONDecodeError, TypeError):
                    photo_urls = [alert.photo_filename]
            
            video_urls = []
            if alert.video_filename:
                try:
                    video_urls = json.loads(alert.video_filename)
                    if not isinstance(video_urls, list):
                        video_urls = [alert.video_filename]
                except (json.JSONDecodeError, TypeError):
                    video_urls = [alert.video_filename]
            
            alerts_list.append({
                'id': alert.id,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'description': alert.description,
                'reporter_name': alert.reporter_name,
                'barangay': alert.barangay,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'photo_urls': photo_urls,
                'video_urls': video_urls,
                'photo_url': photo_urls[0] if photo_urls else None,
                'video_url': video_urls[0] if video_urls else None,
                'admin_response': alert.admin_response,
                'responded_at': alert.responded_at.isoformat() if alert.responded_at else None,
                'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
                'resolve_time': alert.resolve_time,
                'status': alert.status or 'pending',
                'resolved': alert.resolved
            })
        
        print(f"✅ Retrieved {len(alerts_list)} alerts for user {user_id}")
        return jsonify({
            'success': True,
            'alerts': alerts_list
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting user alerts: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# --------------------------
# DELETE ALERT WITH CLOUDINARY CLEANUP
# --------------------------
@alert_bp.route('/delete_alert/<alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    """Delete alert and its media from Cloudinary"""
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        if alert.photo_filename:
            try:
                photo_urls = json.loads(alert.photo_filename)
                if isinstance(photo_urls, list):
                    for photo_url in photo_urls:
                        if 'cloudinary.com' in photo_url:
                            parts = photo_url.split('/')
                            if 'fire_alerts' in parts:
                                idx = parts.index('fire_alerts')
                                public_id = '/'.join(parts[idx:]).split('.')[0]
                                delete_from_cloudinary(public_id, resource_type="image")
                                print(f"🗑️ Deleted photo: {public_id}")
            except:
                pass
        
        if alert.video_filename:
            try:
                video_urls = json.loads(alert.video_filename)
                if isinstance(video_urls, list):
                    for video_url in video_urls:
                        if 'cloudinary.com' in video_url:
                            parts = video_url.split('/')
                            if 'fire_alerts' in parts:
                                idx = parts.index('fire_alerts')
                                public_id = '/'.join(parts[idx:]).split('.')[0]
                                delete_from_cloudinary(public_id, resource_type="video")
                                print(f"🗑️ Deleted video: {public_id}")
            except:
                pass
        
        db.session.delete(alert)
        db.session.commit()
        
        print(f"✅ Alert {alert_id} deleted")
        return jsonify({
            'success': True,
            'message': 'Alert deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting alert: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# --------------------------
# CLEAR USER ALERTS
# --------------------------
@alert_bp.route('/api/alerts/user/<int:user_id>', methods=['DELETE'])
def clear_alerts(user_id):
    """Delete all alerts for a user"""
    try:
        alerts = Alert.query.filter_by(user_id=user_id).all()
        
        for alert in alerts:
            if alert.photo_filename:
                try:
                    photo_urls = json.loads(alert.photo_filename)
                    if isinstance(photo_urls, list):
                        for photo_url in photo_urls:
                            if 'cloudinary.com' in photo_url:
                                parts = photo_url.split('/')
                                if 'fire_alerts' in parts:
                                    idx = parts.index('fire_alerts')
                                    public_id = '/'.join(parts[idx:]).split('.')[0]
                                    delete_from_cloudinary(public_id, resource_type="image")
            except:
                pass
            
            if alert.video_filename:
                try:
                    video_urls = json.loads(alert.video_filename)
                    if isinstance(video_urls, list):
                        for video_url in video_urls:
                            if 'cloudinary.com' in video_url:
                                parts = video_url.split('/')
                                if 'fire_alerts' in parts:
                                    idx = parts.index('fire_alerts')
                                    public_id = '/'.join(parts[idx:]).split('.')[0]
                                    delete_from_cloudinary(public_id, resource_type="video")
            except:
                pass
            
            db.session.delete(alert)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Deleted {len(alerts)} alerts',
            'count': len(alerts)
        }), 200
        
    except Exception as e:
        print(f"❌ Error clearing alerts: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# --------------------------
# DOWNLOAD FIRE CONTACTS PDF
# --------------------------
@alert_bp.route('/api/fire/contacts/pdf', methods=['GET'])
def download_contacts_pdf():
    path = os.path.join(BACKEND_DIR, "docs/contacts.pdf")
    if not os.path.exists(path):
        return {"error": "PDF not found"}, 404
    return send_file(path, as_attachment=True)