from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
import os
import traceback

from sqlalchemy import text

from dijkstra import dijkstra
from graph_data import road_graph

# Import your database setup
from database import init_db, db
from route.register_route import register_bp
from route.alert_route import alert_bp
from route.adminauth_route import login_bp
from route.userauth_route import auth_bp
from model.user import User
from model.alert_model import Alert

from node_coordinates import node_coords

from dotenv import load_dotenv

# ✅ Import Cloudinary functions
from cloudinary_config import init_cloudinary, upload_to_cloudinary, delete_from_cloudinary

load_dotenv()

app = Flask(__name__)

# CORS config
CORS(app, supports_credentials=True,
     resources={r"/*": {
         "origins": [
             "https://sunog-user.onrender.com", 
             "https://sunog-admin.onrender.com",
             "http://localhost:3000",
             "http://localhost:5000"
         ],
         "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         "allow_headers": ["Content-Type", "Authorization"]
     }})

# Secret key
app.config['SECRET_KEY'] = '88e8c79a3e05967c39b69b6d9ae86f04d418a4f59fa84c4eadf6506e56f34672'

# ✅ Initialize Cloudinary and verify configuration
try:
    init_cloudinary()
    print("✅ Cloudinary initialized successfully!")
    print(f"Cloud Name: {os.getenv('CLOUDINARY_CLOUD_NAME')}")
except Exception as e:
    print(f"❌ Cloudinary initialization failed: {e}")
    print("Please check your .env file has:")
    print("  CLOUDINARY_CLOUD_NAME=your_cloud_name")
    print("  CLOUDINARY_API_KEY=your_api_key")
    print("  CLOUDINARY_API_SECRET=your_api_secret")

# Uploads folder (keep for backward compatibility if needed)
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Init DB with Railway MySQL
init_db(app)

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/user')
app.register_blueprint(login_bp)
app.register_blueprint(register_bp)
app.register_blueprint(alert_bp)

# Dijkstra route
@app.route('/get-shortest-route')
def get_shortest_route():
    start = request.args.get('start')
    end = request.args.get('end')

    path = dijkstra(road_graph, start, end)

    if not path:
        return jsonify({"error": "No path found"}), 404

    try:
        coords = [node_coords[node] for node in path]
    except KeyError as e:
        return jsonify({"error": f"Missing node coordinate: {e}"}), 500

    return jsonify(coords)

# ✅ UPDATED Fire Alert Endpoint with Cloudinary

# ✅ Get all alerts
# ========================================
# REPLACE your existing /get_alerts endpoint with this:
# ========================================

# ========================================
# REPLACE your existing /get_alerts endpoint with this:
# ========================================

@app.route('/get_alerts', methods=['GET', 'OPTIONS'])
def get_alerts():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        # ✅ Only get unresolved alerts (active alerts)
        alerts = Alert.query.filter_by(resolved=False).order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in alerts:
            # ✅ photo_filename and video_filename already contain full Cloudinary URLs
            alerts_list.append({
                'id': alert.id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'location': alert.barangay,  # Frontend expects 'location'
                'photo_filename': alert.photo_filename,  # Full Cloudinary URL
                'video_filename': alert.video_filename,  # Full Cloudinary URL
                'photo_url': alert.photo_filename,  # Full Cloudinary URL
                'video_url': alert.video_filename,  # Full Cloudinary URL
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'status': 'Pending'
            })
        
        print(f"📋 Retrieved {len(alerts_list)} active alerts")
        print(f"📸 Sample photo URL: {alerts_list[0]['photo_url'] if alerts_list and alerts_list[0]['photo_url'] else 'No photos'}")
        
        return jsonify({
            'alerts': alerts_list,
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print("❌ Error fetching alerts:", str(e))
        traceback.print_exc()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500


# ========================================
# ADD these NEW endpoints after /get_alerts:
# ========================================

@app.route('/get_resolved_alerts', methods=['GET', 'OPTIONS'])
def get_resolved_alerts():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        resolved_alerts = Alert.query.filter_by(resolved=True).order_by(Alert.timestamp.desc()).all()
        
        alerts_list = []
        for alert in resolved_alerts:
            alerts_list.append({
                'id': alert.id,
                'description': alert.description,
                'latitude': alert.latitude,
                'longitude': alert.longitude,
                'location': alert.barangay,
                'photo_url': alert.photo_filename,
                'video_url': alert.video_filename,
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None,
                'resolvedAt': alert.resolved_at.isoformat() if alert.resolved_at else None,
                'status': 'Resolved'
            })
        
        print(f"📋 Retrieved {len(alerts_list)} resolved alerts")
        
        return jsonify({
            'resolved': alerts_list,
            'count': len(alerts_list)
        }), 200
        
    except Exception as e:
        print("❌ Error fetching resolved alerts:", str(e))
        traceback.print_exc()
        return jsonify({
            'resolved': [],
            'count': 0
        }), 200


@app.route('/resolve_alert/<int:alert_id>', methods=['POST', 'OPTIONS'])
def resolve_alert(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'message': 'Alert not found'}), 404
        
        from datetime import datetime
        alert.resolved = True
        alert.resolved_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"✅ Alert {alert_id} marked as resolved")
        return jsonify({
            'message': 'Alert marked as resolved',
            'alert_id': alert_id
        }), 200
        
    except Exception as e:
        print("❌ Error resolving alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500


@app.route('/unresolve_alert/<int:alert_id>', methods=['POST', 'OPTIONS'])
def unresolve_alert(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'message': 'Alert not found'}), 404
        
        alert.resolved = False
        alert.resolved_at = None
        
        db.session.commit()
        
        print(f"✅ Alert {alert_id} marked as unresolved")
        return jsonify({
            'message': 'Alert marked as unresolved',
            'alert_id': alert_id
        }), 200
        
    except Exception as e:
        print("❌ Error unresolving alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500
    
# ✅ Delete alert endpoint (also deletes from Cloudinary)
@app.route('/delete_alert/<int:alert_id>', methods=['DELETE', 'OPTIONS'])
def delete_alert(alert_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({'message': 'Alert not found'}), 404
        
        print(f"🗑️ Deleting alert {alert_id}")
        
        # Delete photo from Cloudinary
        if alert.photo_filename and 'cloudinary.com' in alert.photo_filename:
            try:
                # Extract public_id from URL
                parts = alert.photo_filename.split('/')
                if 'fire_alerts' in parts:
                    idx = parts.index('fire_alerts')
                    public_id = '/'.join(parts[idx:]).split('.')[0]
                    result = delete_from_cloudinary(public_id, resource_type="image")
                    print(f"  Photo deletion: {result}")
            except Exception as e:
                print(f"  ⚠️ Photo deletion failed: {e}")
        
        # Delete video from Cloudinary
        if alert.video_filename and 'cloudinary.com' in alert.video_filename:
            try:
                parts = alert.video_filename.split('/')
                if 'fire_alerts' in parts:
                    idx = parts.index('fire_alerts')
                    public_id = '/'.join(parts[idx:]).split('.')[0]
                    result = delete_from_cloudinary(public_id, resource_type="video")
                    print(f"  Video deletion: {result}")
            except Exception as e:
                print(f"  ⚠️ Video deletion failed: {e}")
        
        # Delete from database
        db.session.delete(alert)
        db.session.commit()
        
        print(f"✅ Alert {alert_id} deleted successfully")
        return jsonify({'message': 'Alert deleted successfully'}), 200
        
    except Exception as e:
        print("❌ Error deleting alert:", str(e))
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'message': 'Server error', 'error': str(e)}), 500

# Serve uploaded files (backward compatibility)
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        print(f"Error serving file {filename}:", e)
        return jsonify({'message': 'File not found'}), 404

@app.route('/alertResolve')
def admin_resolve():
    return render_template('alertResolve.html')

@app.route("/health")
def health():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        print("DB ERROR:", e)
        db_status = "disconnected"

    cloudinary_status = "configured" if os.getenv('CLOUDINARY_CLOUD_NAME') else "not configured"

    return jsonify({
        "status": "healthy",
        "database": db_status,
        "cloudinary": cloudinary_status,
        "cors": "enabled"
    })


# ========================================
# DATABASE MIGRATION ENDPOINTS
# ========================================

@app.route('/admin/safe-migrate', methods=['POST', 'OPTIONS'])
def safe_migrate():
    """
    Safe migration to increase photo/video column sizes
    This is NON-DESTRUCTIVE and won't delete any data
    """
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        from sqlalchemy import inspect
        
        print("🔍 Checking current database schema...")
        
        inspector = inspect(db.engine)
        columns = inspector.get_columns('alerts')
        
        photo_col = next((c for c in columns if c['name'] == 'photo_filename'), None)
        video_col = next((c for c in columns if c['name'] == 'video_filename'), None)
        
        if not photo_col or not video_col:
            return jsonify({
                'success': False,
                'error': 'Columns not found in database'
            }), 400
        
        current_photo_size = getattr(photo_col.get('type'), 'length', 255)
        current_video_size = getattr(video_col.get('type'), 'length', 255)
        
        print(f"📊 Current sizes - Photo: {current_photo_size}, Video: {current_video_size}")
        
        # Check if already migrated
        if current_photo_size >= 500 and current_video_size >= 500:
            return jsonify({
                'success': True,
                'message': '✅ Columns already migrated!',
                'photo_size': current_photo_size,
                'video_size': current_video_size,
                'already_done': True
            }), 200
        
        # Perform migration
        print("🔄 Starting migration...")
        
        with db.engine.connect() as conn:
            db_type = db.engine.dialect.name
            print(f"💾 Database type: {db_type}")
            
            if db_type == 'mysql':
                print("  Executing MySQL ALTER commands...")
                conn.execute(text("ALTER TABLE alerts MODIFY COLUMN photo_filename VARCHAR(500)"))
                conn.execute(text("ALTER TABLE alerts MODIFY COLUMN video_filename VARCHAR(500)"))
                conn.commit()
            elif db_type == 'postgresql':
                print("  Executing PostgreSQL ALTER commands...")
                conn.execute(text("ALTER TABLE alerts ALTER COLUMN photo_filename TYPE VARCHAR(500)"))
                conn.execute(text("ALTER TABLE alerts ALTER COLUMN video_filename TYPE VARCHAR(500)"))
                conn.commit()
            else:
                return jsonify({
                    'success': False,
                    'error': f'Unsupported database type: {db_type}'
                }), 400
        
        print("✅ Migration completed successfully!")
        
        return jsonify({
            'success': True,
            'message': '✅ Migration completed successfully!',
            'old_photo_size': current_photo_size,
            'old_video_size': current_video_size,
            'new_photo_size': 500,
            'new_video_size': 500,
            'database_type': db_type
        }), 200
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


    @app.route('/admin/migration-tool')
    def migration_tool():
        """Simple UI to run the migration"""
        return '''<!DOCTYPE html>
    <html><head><title>FireTrackr - Database Migration</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
    .container{background:white;padding:40px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3);max-width:600px;width:100%}
    h1{color:#333;margin-bottom:10px;font-size:28px}
    .subtitle{color:#666;margin-bottom:30px;font-size:16px}
    .info{background:#f0f7ff;border-left:4px solid #2196F3;padding:15px;margin-bottom:20px;border-radius:5px}
    .success{background:#d4edda;border-left:4px solid #28a745;padding:15px;margin-bottom:20px;border-radius:5px;display:none}
    .error{background:#f8d7da;border-left:4px solid #dc3545;padding:15px;margin-bottom:20px;border-radius:5px;display:none}
    button{width:100%;padding:15px;font-size:18px;font-weight:600;background:#4CAF50;color:white;border:none;border-radius:10px;cursor:pointer;transition:all 0.3s}
    button:hover:not(:disabled){background:#45a049;transform:translateY(-2px);box-shadow:0 5px 15px rgba(76,175,80,0.3)}
    button:disabled{background:#ccc;cursor:not-allowed}
    .details{margin-top:10px;font-family:monospace;font-size:13px;background:#f5f5f5;padding:10px;border-radius:5px}
    </style></head><body>
    <div class="container">
    <h1>🔧 Database Migration Tool</h1>
    <p class="subtitle">FireTrackr Capstone Project</p>
    <div class="info"><strong>📋 What this does:</strong><br>
    Increases photo_filename and video_filename columns from 255 to 500 characters for Cloudinary URLs.</div>
    <div class="success" id="success"></div>
    <div class="error" id="error"></div>
    <button id="btn" onclick="run()">🚀 Run Migration</button>
    </div>
    <script>
    async function run(){
    const btn=document.getElementById('btn');
    const success=document.getElementById('success');
    const error=document.getElementById('error');
    success.style.display='none';
    error.style.display='none';
    btn.disabled=true;
    btn.textContent='⏳ Running...';
    try{
    const r=await fetch('/admin/safe-migrate',{method:'POST'});
    const d=await r.json();
    if(d.success){
    success.style.display='block';
    if(d.already_done){
    success.innerHTML='<strong>✅ Already Migrated!</strong><br>Columns are already 500 characters.<div class="details">Photo: '+d.photo_size+' chars<br>Video: '+d.video_size+' chars</div>';
    btn.textContent='✅ Already Done';
    }else{
    success.innerHTML='<strong>✅ Success!</strong><br>'+d.message+'<div class="details">Database: '+d.database_type+'<br>Old: '+d.old_photo_size+' → New: 500</div>';
    btn.textContent='✅ Complete';
    }
    }else{throw new Error(d.error)}
    }catch(e){
    error.style.display='block';
    error.innerHTML='<strong>❌ Failed</strong><br>'+e.message;
    btn.textContent='❌ Try Again';
    btn.disabled=false;
    }
    }
    </script></body></html>'''

    @app.route('/admin/debug-alerts')
    def debug_alerts():
        """Debug what's in the database"""
    try:
        all_alerts = Alert.query.order_by(Alert.timestamp.desc()).limit(5).all()
        
        result = []
        for alert in all_alerts:
            result.append({
                'id': alert.id,
                'timestamp': str(alert.timestamp),
                'photo_filename': alert.photo_filename,
                'is_cloudinary': 'cloudinary.com' in (alert.photo_filename or ''),
                'barangay': alert.barangay,
                'reporter_name': alert.reporter_name,
                'resolved': alert.resolved
            })
        
        return jsonify({
            'total_alerts': Alert.query.count(),
            'recent_5': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'Internal server error'}), 500

    
# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'Internal server error'}), 500

# Create Tables
with app.app_context():
    db.create_all()
    print("✅ Database tables created/verified")

# Run App
if __name__ == '__main__':
    print("🚀 Starting Flask app...")
    print(f"📍 Running on http://localhost:5000")
    app.run(port=5000, debug=True)