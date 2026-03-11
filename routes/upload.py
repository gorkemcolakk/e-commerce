import os
import time
import uuid
from flask import Blueprint, request, jsonify
from utils import role_required

upload_bp = Blueprint('upload', __name__, url_prefix='/api/upload')
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def simulate_s3_upload(file_obj, filename):
    """
    Mock func to simulate uploading a file to Amazon S3 or similar cloud storage.
    """
    print(f"\n[CLOUDSYNC] 🚀 Initiating secure upload to S3 Bucket (eventix-assets)...")
    print(f"[CLOUDSYNC] 📁 File: {filename}")
    
    # Simulate network latency/upload time
    time.sleep(1.5)
    
    # Actually save locally so the app still works
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file_obj.save(os.path.join(UPLOAD_FOLDER, filename))
    
    print(f"[CLOUDSYNC] ✅ Upload complete! Object stored successfully.\n")
    return f"/uploads/{filename}"

@upload_bp.route('', methods=['POST'])
@role_required('organizer', 'admin')
def upload_file():
    if 'file' not in request.files:
        return jsonify({'message': 'Dosya bulunamadı'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'Seçili dosya yok'}), 400
        
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        
        # simulated S3 upload
        file_url = simulate_s3_upload(file, filename)
        
        return jsonify({'url': file_url, 'message': 'Dosya buluta başarıyla yüklendi (Simüle edildi)'}), 201
    else:
        return jsonify({'message': 'Geçersiz dosya uzantısı (Desteklenenler: png, jpg, jpeg, gif, mp4, webm)'}), 400
