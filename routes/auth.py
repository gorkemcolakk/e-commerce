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
        return jsonify({'message': 'Missing data'}), 400

    if len(data['password']) < 6:
        return jsonify({'message': 'Password must be at least 6 characters'}), 400

    role = data.get('role', 'customer')
    if role not in ('customer', 'organizer'):
        role = 'customer'
        
    phone = data.get('phone', '')
    birthdate = data.get('birthdate', '')

    conn = get_db_connection()
    c = conn.cursor()
    existing = c.execute('SELECT id FROM users WHERE email = ?', (data['email'],)).fetchone()
    if existing:
        conn.close()
        return jsonify({'message': 'This email is already registered'}), 409

    hashed_pw = generate_password_hash(data['password'])
    c.execute(
        'INSERT INTO users (fullname, email, password, role, phone, birthdate) VALUES (?, ?, ?, ?, ?, ?)',
        (data['fullname'], data['email'], hashed_pw, role, phone, birthdate)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Registration successful'}), 201

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Missing data'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (data['email'],)).fetchone()
    conn.close()

    if not user or not check_password_hash(user['password'], data['password']):
        return jsonify({'message': 'Invalid email or password'}), 401

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
            'role': user['role'],
            'phone': user['phone'] if 'phone' in user.keys() else '',
            'birthdate': user['birthdate'] if 'birthdate' in user.keys() else ''
        }
    }), 200

from utils import send_email

@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")
def forgot_password():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'message': 'Email is required'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()

    if not user:
        # Prevent user enumeration, just return success
        return jsonify({'message': 'Password reset link sent to your email (if registered).'}), 200
    
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
        <h2 style="color:#a78bfa;margin-top:0;">🔐 Password Reset</h2>
        <p>Hello <strong>{user['fullname']}</strong>,</p>
        <p>Click the button below to reset your password. The link is valid for <strong>15 minutes</strong>.</p>
        <a href="{reset_link}" style="display:inline-block;margin:16px 0;padding:12px 24px;background:linear-gradient(135deg,#7c3aed,#db2777);color:#fff;text-decoration:none;border-radius:8px;font-weight:bold;">Reset My Password</a>
        <p style="font-size:12px;color:#94a3b8;">If you cannot click the button, copy this link to your browser:<br>
          <a href="{reset_link}" style="color:#a78bfa;word-break:break-all;">{reset_link}</a>
        </p>
        <hr style="border:none;border-top:1px solid #2d2d4e;margin:24px 0;">
        <p style="font-size:12px;color:#64748b;">If you did not make this request, please ignore this email.</p>
      </div>
    </body></html>
    """
    plain_text = f"Visit this link to reset your password (valid for 15 min):\n{reset_link}"
    send_email(email, "Password Reset Request", plain_text, html_message=email_body)

    return jsonify({'message': 'Password reset link sent to your email.'}), 200

@auth_bp.route('/reset-password', methods=['POST'])
@limiter.limit("5 per hour")
def reset_password():
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        return jsonify({'message': 'Missing data'}), 400

    if len(new_password) < 6:
        return jsonify({'message': 'Password must be at least 6 characters'}), 400

    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if decoded.get('purpose') != 'password_reset':
            return jsonify({'message': 'Invalid token purpose'}), 400
    except Exception:
        return jsonify({'message': 'Invalid or expired token'}), 400
    
    hashed_pw = generate_password_hash(new_password)
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_pw, decoded['id']))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Password reset successfully. You can now login.'}), 200
