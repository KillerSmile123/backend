import cloudinary
import cloudinary.uploader
import os
import io
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()

def init_cloudinary():
    """Initialize Cloudinary configuration"""
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
    
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
    import base64

    try:
        print(f"🔄 Starting Cloudinary upload...")
        print(f"  Folder: {folder}")
        print(f"  Resource Type: {resource_type}")
        print(f"  File: {file.filename if hasattr(file, 'filename') else 'Unknown'}")
        print(f"  Content-Type: {file.content_type if hasattr(file, 'content_type') else 'Unknown'}")

        # Read raw bytes from stream
        file.stream.seek(0)
        file_bytes = file.stream.read()

        print(f"  File size: {len(file_bytes)} bytes")
        print(f"  First 16 bytes (hex): {file_bytes[:16].hex()}")

        if len(file_bytes) == 0:
            return {'success': False, 'error': 'File is empty (0 bytes)'}

        # Detect content type from file header (magic bytes)
        content_type = file.content_type or 'application/octet-stream'
        if file_bytes[:3] == b'\xff\xd8\xff':
            content_type = 'image/jpeg'
        elif file_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            content_type = 'image/png'
        elif file_bytes[:4] == b'RIFF' and file_bytes[8:12] == b'WEBP':
            content_type = 'image/webp'
        elif file_bytes[:4] in (b'\x00\x00\x00\x1c', b'\x00\x00\x00\x18', b'\x00\x00\x00 '):
            content_type = 'video/mp4'

        print(f"  Detected content type: {content_type}")

        # ✅ Upload via base64 data URI — most reliable across all environments
        b64_data = base64.b64encode(file_bytes).decode('utf-8')
        data_uri = f"data:{content_type};base64,{b64_data}"

        upload_options = {
            'folder': folder,
            'resource_type': resource_type,
        }

        result = cloudinary.uploader.upload(data_uri, **upload_options)

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