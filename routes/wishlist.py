from flask import Blueprint, jsonify, g
from database import get_db_connection
from utils import token_required, event_to_dict

wishlist_bp = Blueprint('wishlist', __name__, url_prefix='/api/wishlist')

@wishlist_bp.route('', methods=['GET'])
@token_required
def get_wishlist():
    conn = get_db_connection()
    items = conn.execute('''
        SELECT e.id, e.title, e.category, e.date, e.location, e.price, e.image,
               e.featured, e.capacity, e.sold_count, e.status, e.description, e.lineup_json
        FROM wishlist w
        JOIN events e ON w.event_id = e.id
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
    ''', (g.user['id'],)).fetchall()
    conn.close()
    return jsonify([event_to_dict(e) for e in items]), 200

@wishlist_bp.route('/<event_id>', methods=['POST'])
@token_required
def add_to_wishlist(event_id):
    conn = get_db_connection()
    event = conn.execute('SELECT id FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404
    try:
        conn.execute(
            'INSERT INTO wishlist (user_id, event_id) VALUES (?, ?)',
            (g.user['id'], event_id)
        )
        conn.commit()
        conn.close()
        return jsonify({'message': 'Favorilere eklendi'}), 201
    except Exception:
        conn.close()
        return jsonify({'message': 'Zaten favorilerde'}), 409

@wishlist_bp.route('/<event_id>', methods=['DELETE'])
@token_required
def remove_from_wishlist(event_id):
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM wishlist WHERE user_id = ? AND event_id = ?',
        (g.user['id'], event_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Favorilerden çıkarıldı'}), 200
