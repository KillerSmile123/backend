from app import app, db
from model.alert_model import Alert

with app.app_context():
    # Fix alert #152
    alert152 = Alert.query.get(152)
    if alert152:
        alert152.status = 'spam'
        print(f"✅ Fixed alert #152")
    else:
        print(f"⚠️  Alert #152 not found")
    
    # Fix alert #154
    alert154 = Alert.query.get(154)
    if alert154:
        alert154.status = 'spam'
        print(f"✅ Fixed alert #154")
    else:
        print(f"⚠️  Alert #154 not found")
    
    # Commit changes
    db.session.commit()
    print("🎉 Changes saved to Railway database!")