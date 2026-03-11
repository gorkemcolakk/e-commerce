from flask import Blueprint, request, jsonify, g
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
    if not fullname:
        return jsonify({'message': 'Eksik veri'}), 400

    conn = get_db_connection()
    conn.execute('UPDATE users SET fullname = ? WHERE id = ?', (fullname, g.user['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Profil güncellendi'}), 200
