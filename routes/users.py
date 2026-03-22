from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection
from utils import token_required

users_bp = Blueprint('users', __name__, url_prefix='/api/users')

@users_bp.route('/me', methods=['GET'])
@token_required
def get_profile():
    return jsonify({
        'id': g.user['id'],
        'fullname': g.user['fullname'],
        'email': g.user['email'],
        'role': g.user['role']
    }), 200

@users_bp.route('/me', methods=['PATCH'])
@token_required
def update_profile():
    data = request.get_json()
    fullname = data.get('fullname')
    phone = data.get('phone', '')
    birthdate = data.get('birthdate', '')

    if not fullname:
        return jsonify({'message': 'Eksik veri'}), 400

    conn = get_db_connection()
    conn.execute('UPDATE users SET fullname = ?, phone = ?, birthdate = ? WHERE id = ?', 
                 (fullname, phone, birthdate, g.user['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Profil güncellendi'}), 200

@users_bp.route('/change-password', methods=['POST'])
@token_required
def change_password():
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({'message': 'Eksik veri'}), 400

    if len(new_password) < 6:
        return jsonify({'message': 'Şifre en az 6 karakter olmalıdır'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT password FROM users WHERE id = ?', (g.user['id'],)).fetchone()

    if not user or not check_password_hash(user['password'], current_password):
        conn.close()
        return jsonify({'message': 'Mevcut şifre hatalı'}), 401

    hashed_pw = generate_password_hash(new_password)
    conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_pw, g.user['id']))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Şifre başarıyla güncellendi'}), 200
