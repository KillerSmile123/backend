import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv
import sys

load_dotenv()

def init_cloudinary():
    """Initialize Cloudinary configuration"""
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
    
    # Debug logging
    print(f"🔍 Cloudinary Config Check:")
    print(f"  Cloud Name: {'✅ Set' if cloud_name else '❌ Missing'}")
    print(f"  API Key: {'✅ Set' if api_key else '❌ Missing'}")
    print(f"  API Secret: {'✅ Set' if api_secret else '❌ Missing'}")
    
    if not all([cloud_name, api_key, api_secret]):
        print("❌ Missing Cloudinary credentials!")
        sys.exit(1)
    
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )

def upload_to_cloudinary(file, folder="fire_alerts", resource_type="auto"):
    """
    Upload a file to Cloudinary
    
    Args:
        file: File object from request.files
        folder: Cloudinary folder name
        resource_type: 'image', 'video', or 'auto'
    
    Returns:
        dict: Upload result with secure_url and public_id
    """
    try:
        print(f"🔄 Starting Cloudinary upload...")
        print(f"  Folder: {folder}")
        print(f"  Resource Type: {resource_type}")
        print(f"  File: {file.filename if hasattr(file, 'filename') else 'Unknown'}")
        
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type=resource_type,
            transformation=[
                {'quality': 'auto'},
                {'fetch_format': 'auto'}
            ]
        )
        
        print(f"✅ Upload successful!")
        print(f"  URL: {result['secure_url']}")
        print(f"  Public ID: {result['public_id']}")
        
        return {
            'success': True,
            'url': result['secure_url'],
            'public_id': result['public_id']
        }
    except Exception as e:
        print(f"❌ Cloudinary upload error: {str(e)}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }

def delete_from_cloudinary(public_id, resource_type="image"):
    """
    Delete a file from Cloudinary
    
    Args:
        public_id: The Cloudinary public_id
        resource_type: 'image' or 'video'
    
    Returns:
        dict: Result of deletion
    """
    try:
        print(f"🗑️ Deleting from Cloudinary: {public_id}")
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        print(f"  Result: {result}")
        return {
            'success': result['result'] == 'ok',
            'result': result
        }
    except Exception as e:
        print(f"❌ Cloudinary deletion error: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }