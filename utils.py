import qrcode
import io
import base64
import json
import jwt
import hmac
import hashlib
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from flask import request, jsonify, g
from functools import wraps
from database import get_db_connection
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

SECRET_KEY = 'eventix-super-secret-key-2026'
COMMISSION_RATE = 0.10

limiter = Limiter(key_func=get_remote_address)

def sign_ticket_data(data: str) -> str:
    """Creates an HMAC-SHA256 signature for the ticket data."""
    signature = hmac.new(SECRET_KEY.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{data}-{signature[:16]}"

def verify_ticket_signature(signed_data: str) -> bool:
    """Verifies the HMAC signature of the ticket data."""
    parts = signed_data.rsplit('-', 1)
    if len(parts) != 2:
        return False
    data, signature = parts
    expected_signature = hmac.new(SECRET_KEY.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()[:16]
    return hmac.compare_digest(signature, expected_signature)

def make_qr_base64(data: str) -> str:
    """Generate a QR code image and return it as a base64 PNG data URL."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{b64}"

def make_qr_bytes(data: str) -> bytes:
    """Generate a QR code image and return raw PNG bytes (for email CID embedding)."""
    qr = qrcode.QRCode(version=1, box_size=8, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()

def event_to_dict(e):
    evt = dict(e)
    evt['featured'] = bool(evt['featured'])
    evt['lineup'] = json.loads(evt['lineup_json']) if evt.get('lineup_json') else []
    evt.pop('lineup_json', None)
    return evt

def create_notification(conn, user_id: int, message: str):
    conn.execute(
        'INSERT INTO notifications (user_id, message) VALUES (?, ?)',
        (user_id, message)
    )

def send_email(to_email: str, subject: str, message: str, html_message: str = None, images: list = None):
    """
    Gerçek SMTP kullanarak e-posta gönderir.
    images: [{'cid': 'unique_id', 'data': bytes_of_png}, ...] — CID ile gömülü resimler.
    Çevresel değişkenlerde SMTP ayarları yoksa mock (simülasyon) email atar.
    """
    smtp_server = os.environ.get('SMTP_SERVER')
    smtp_port = os.environ.get('SMTP_PORT', 587)
    smtp_username = os.environ.get('SMTP_USERNAME')
    smtp_password = os.environ.get('SMTP_PASSWORD')

    if smtp_server and smtp_username and smtp_password:
        try:
            # Eğer resim varsa related/mixed yapısı kur, yoksa alternative yeterli
            if images:
                outer = MIMEMultipart('mixed')
                outer['Subject'] = subject
                outer['From'] = f"Eventix <{smtp_username}>"
                outer['To'] = to_email

                alt = MIMEMultipart('alternative')
                alt.attach(MIMEText(message, 'plain'))
                if html_message:
                    related = MIMEMultipart('related')
                    related.attach(MIMEText(html_message, 'html'))
                    for img in images:
                        mime_img = MIMEImage(img['data'], _subtype='png')
                        mime_img.add_header('Content-ID', f"<{img['cid']}>")  
                        mime_img.add_header('Content-Disposition', 'inline', filename=f"{img['cid']}.png")
                        related.attach(mime_img)
                    alt.attach(related)
                outer.attach(alt)
            else:
                outer = MIMEMultipart('alternative')
                outer['Subject'] = subject
                outer['From'] = f"Eventix <{smtp_username}>"
                outer['To'] = to_email
                outer.attach(MIMEText(message, 'plain'))
                if html_message:
                    outer.attach(MIMEText(html_message, 'html'))

            server = smtplib.SMTP(smtp_server, int(smtp_port))
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(outer)
            server.quit()
            print(f"📧 [REAL] EMAIL SENT TO: {to_email}")
            return
        except Exception as e:
            print(f"🚨 SMTP E-Posta Gönderme Hatası: {e}")
            print("Uyarı: Simülasyon (Mock) e-posta üzerinden devam ediliyor...")

    # Fallback to mock
    send_mock_email(to_email, subject, message)

def send_mock_email(to_email: str, subject: str, message: str):
    """
    Simulates sending an email by printing formatted output to the console.
    """
    print(f"\n{'='*50}")
    print(f"📧 [MOCK] EMAIL SENT TO: {to_email}")
    print(f"📝 SUBJECT: {subject}")
    print(f"--------------------------------------------------")
    print(f"{message}")
    print(f"{'='*50}\n")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        if not token:
            return jsonify({'message': 'Token eksik!'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE id = ?', (data['id'],)).fetchone()
            conn.close()
            if not user:
                return jsonify({'message': 'Geçersiz token!'}), 401
            g.user = dict(user)
        except Exception:
            return jsonify({'message': 'Token geçersiz veya süresi dolmuş!'}), 401
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            if g.user.get('role') not in roles:
                return jsonify({'message': 'Yetersiz yetki!'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
