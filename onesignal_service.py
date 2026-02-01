# onesignal_service.py
# Place this file in your project root (same folder as app.py)
# This is a standalone helper — app.py just imports and calls it

import requests
import os
from dotenv import load_dotenv

load_dotenv()

ONESIGNAL_APP_ID = os.getenv('ONESIGNAL_APP_ID')           # ← Add to your .env
ONESIGNAL_API_KEY = os.getenv('ONESIGNAL_REST_API_KEY')    # ← Add to your .env

ONESIGNAL_API_URL = 'https://onesignal.com/api/v1/notifications'


def send_push_notification(user_id, title, message, data=None):
    """
    Send a push notification to a specific user via OneSignal.

    Args:
        user_id (str): Your app's user ID (matches the externalUserId set on frontend)
        title (str): Notification title
        message (str): Notification body/message
        data (dict, optional): Extra key-value data to pass to the app when tapped
    
    Returns:
        dict: { 'success': bool, 'response': ... }
    """

    if not ONESIGNAL_APP_ID or not ONESIGNAL_API_KEY:
        print("⚠️ OneSignal: APP_ID or API_KEY not configured in .env")
        return {'success': False, 'error': 'OneSignal not configured'}

    headers = {
        'Authorization': f'Basic {ONESIGNAL_API_KEY}',
        'Content-Type': 'application/json'
    }

    payload = {
        'app_id': ONESIGNAL_APP_ID,
        'include_external_user_ids': [str(user_id)],  # targets your user by externalUserId
        'headings': {'en': title},
        'contents': {'en': message},
    }

    # Attach extra data if provided (available in the app when user taps the notification)
    if data:
        payload['data'] = data

    try:
        response = requests.post(ONESIGNAL_API_URL, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            result = response.json()
            print(f"✅ OneSignal push sent to user {user_id} | Recipients: {result.get('recipients', 0)}")
            return {'success': True, 'response': result}
        else:
            print(f"❌ OneSignal error {response.status_code}: {response.text}")
            return {'success': False, 'error': response.text}

    except requests.exceptions.Timeout:
        print("❌ OneSignal: Request timed out")
        return {'success': False, 'error': 'Request timed out'}
    except Exception as e:
        print(f"❌ OneSignal error: {e}")
        return {'success': False, 'error': str(e)}