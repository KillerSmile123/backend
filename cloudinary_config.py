import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

def init_cloudinary():
    """Initialize Cloudinary configuration"""
    cloudinary.config(
        cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
        api_key=os.getenv('CLOUDINARY_API_KEY'),
        api_secret=os.getenv('CLOUDINARY_API_SECRET'),
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
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type=resource_type,
            transformation=[
                {'quality': 'auto'},
                {'fetch_format': 'auto'}
            ]
        )
        return {
            'success': True,
            'url': result['secure_url'],
            'public_id': result['public_id']
        }
    except Exception as e:
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
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        return {
            'success': result['result'] == 'ok',
            'result': result
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }