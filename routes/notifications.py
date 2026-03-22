from flask import Blueprint, jsonify, g
from database import get_db_connection
from utils import token_required

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')

@notifications_bp.route('', methods=['GET'])
@token_required
def get_notifications():
    conn = get_db_connection()
    notifications = conn.execute(
        'SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 20',
        (g.user['id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(n) for n in notifications]), 200

@notifications_bp.route('/<int:notif_id>/read', methods=['PATCH'])
@token_required
def mark_notification_read(notif_id):
    conn = get_db_connection()
    conn.execute(
        'UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
        (notif_id, g.user['id'])
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Notification marked as read'}), 200

@notifications_bp.route('/read-all', methods=['PATCH'])
@token_required
def mark_all_notifications_read():
    conn = get_db_connection()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (g.user['id'],))
    conn.commit()
    conn.close()
    return jsonify({'message': 'All notifications marked as read'}), 200
