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



def upload_to_cloudinary(file_or_bytes, folder="fire_alerts", resource_type="auto", filename=None, content_type=None):
    import base64
    try:
        if isinstance(file_or_bytes, bytes):
            file_bytes = file_or_bytes
            content_type = content_type or 'application/octet-stream'
        else:
            file_or_bytes.stream.seek(0)
            file_bytes = file_or_bytes.stream.read()
            content_type = file_or_bytes.content_type or 'application/octet-stream'

        print(f"  File size: {len(file_bytes)} bytes")
        print(f"  First 16 bytes: {file_bytes[:16].hex()}")

        if len(file_bytes) == 0:
            return {'success': False, 'error': 'File is empty (0 bytes)'}

        # ✅ Detect type from magic bytes
        if file_bytes[:3] == b'\xff\xd8\xff':
            content_type = 'image/jpeg'
            resource_type = 'image'
        elif file_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            content_type = 'image/png'
            resource_type = 'image'
        elif file_bytes[:4] == b'RIFF' and file_bytes[8:12] == b'WEBP':
            content_type = 'image/webp'
            resource_type = 'image'
        elif b'ftyp' in file_bytes[:12]:
            # ✅ HEIC/HEIF/MP4 container — Android phones often send these as "jpg"
            # Check if it's heic/heif or mp4
            ftyp_brand = file_bytes[8:12]
            if ftyp_brand in (b'heic', b'heix', b'mif1', b'msf1'):
                content_type = 'image/heic'
                resource_type = 'image'
            else:
                content_type = 'video/mp4'
                resource_type = 'video'
        else:
            # ✅ Fallback: let Cloudinary auto-detect
            resource_type = 'auto'

        print(f"  Detected content type: {content_type}")
        print(f"  Using resource_type: {resource_type}")

        b64_data = base64.b64encode(file_bytes).decode('utf-8')
        data_uri = f"data:{content_type};base64,{b64_data}"

        result = cloudinary.uploader.upload(data_uri, folder=folder, resource_type=resource_type)

        return {
            'success': True,
            'url': result['secure_url'],
            'public_id': result['public_id']
        }

    except Exception as e:
        print(f"❌ Cloudinary upload error: {str(e)}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

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