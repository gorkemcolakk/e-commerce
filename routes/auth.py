from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from database import get_db_connection
from utils import SECRET_KEY, limiter
import os

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per hour")
def register():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password') or not data.get('fullname'):
        return jsonify({'message': 'Eksik veri'}), 400

    role = data.get('role', 'customer')
    if role not in ('customer', 'organizer'):
        role = 'customer'

    conn = get_db_connection()
    c = conn.cursor()
    existing = c.execute('SELECT id FROM users WHERE email = ?', (data['email'],)).fetchone()
    if existing:
        conn.close()
        return jsonify({'message': 'Bu e-posta zaten kayıtlı'}), 409

    hashed_pw = generate_password_hash(data['password'])
    c.execute(
        'INSERT INTO users (fullname, email, password, role) VALUES (?, ?, ?, ?)',
        (data['fullname'], data['email'], hashed_pw, role)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Kayıt başarılı'}), 201

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Eksik veri'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (data['email'],)).fetchone()
    conn.close()

    if not user or not check_password_hash(user['password'], data['password']):
        return jsonify({'message': 'Hatalı e-posta veya şifre'}), 401

    token = jwt.encode({
        'id': user['id'],
        'email': user['email'],
        'fullname': user['fullname'],
        'role': user['role'],
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
    }, SECRET_KEY, algorithm="HS256")

    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'fullname': user['fullname'],
            'role': user['role']
        }
    }), 200

from utils import send_email

@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")
def forgot_password():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'message': 'E-posta gerekli'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()

    if not user:
        # Prevent user enumeration, just return success
        return jsonify({'message': 'Şifre sıfırlama linki e-postanıza gönderildi (varsa).'}), 200
    
    reset_token = jwt.encode({
        'id': user['id'],
        'purpose': 'password_reset',
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    }, SECRET_KEY, algorithm="HS256")

    # Host'u isteğin geldiği yerden al; yoksa .env'deki FRONTEND_URL'i kullan
    base_url = os.environ.get('FRONTEND_URL', '').rstrip('/')
    if not base_url:
        host = request.host  # örn: localhost:5000 veya 192.168.x.x:5000
        base_url = f"http://{host}"

    reset_link = f"{base_url}/login.html?reset_token={reset_token}"
    email_body = f"""
    <html><body style="font-family:Arial,sans-serif;background:#0f0f1a;color:#e2e8f0;padding:32px;">
      <div style="max-width:480px;margin:0 auto;background:#1a1a2e;border-radius:12px;padding:32px;border:1px solid #2d2d4e;">
        <h2 style="color:#a78bfa;margin-top:0;">🔐 Şifre Sıfırlama</h2>
        <p>Merhaba <strong>{user['fullname']}</strong>,</p>
        <p>Şifrenizi sıfırlamak için aşağıdaki butona tıklayın. Link <strong>15 dakika</strong> geçerlidir.</p>
        <a href="{reset_link}" style="display:inline-block;margin:16px 0;padding:12px 24px;background:linear-gradient(135deg,#7c3aed,#db2777);color:#fff;text-decoration:none;border-radius:8px;font-weight:bold;">Şifremi Sıfırla</a>
        <p style="font-size:12px;color:#94a3b8;">Butona tıklayamıyorsanız bu linki tarayıcınıza kopyalayın:<br>
          <a href="{reset_link}" style="color:#a78bfa;word-break:break-all;">{reset_link}</a>
        </p>
        <hr style="border:none;border-top:1px solid #2d2d4e;margin:24px 0;">
        <p style="font-size:12px;color:#64748b;">Bu isteği siz yapmadıysanız bu e-postayı görmezden gelin.</p>
      </div>
    </body></html>
    """
    plain_text = f"Şifrenizi sıfırlamak için bu linke gidin (15 dk geçerlidir):\n{reset_link}"
    send_email(email, "Şifre Sıfırlama Talebi", plain_text, html_message=email_body)

    return jsonify({'message': 'Şifre sıfırlama linki e-postanıza gönderildi.'}), 200

@auth_bp.route('/reset-password', methods=['POST'])
@limiter.limit("5 per hour")
def reset_password():
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        return jsonify({'message': 'Eksik veri'}), 400

    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if decoded.get('purpose') != 'password_reset':
            return jsonify({'message': 'Geçersiz token amacı'}), 400
    except Exception:
        return jsonify({'message': 'Geçersiz veya süresi dolmuş token'}), 400
    
    hashed_pw = generate_password_hash(new_password)
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_pw, decoded['id']))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Şifreniz başarıyla sıfırlandı. Giriş yapabilirsiniz.'}), 200
