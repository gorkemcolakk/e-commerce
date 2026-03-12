from flask import Blueprint, request, jsonify, g
from database import get_db_connection
from utils import role_required, event_to_dict, COMMISSION_RATE

organizer_bp = Blueprint('organizer', __name__, url_prefix='/api/organizer')

@organizer_bp.route('/events', methods=['GET'])
@role_required('organizer', 'admin')
def organizer_events():
    conn = get_db_connection()
    if g.user['role'] == 'admin':
        events = conn.execute('SELECT * FROM events ORDER BY id').fetchall()
    else:
        events = conn.execute(
            'SELECT * FROM events WHERE organizer_id = ? ORDER BY id',
            (g.user['id'],)
        ).fetchall()
    conn.close()
    return jsonify([event_to_dict(e) for e in events]), 200

@organizer_bp.route('/revenue', methods=['GET'])
@role_required('organizer', 'admin')
def organizer_revenue():
    conn = get_db_connection()
    if g.user['role'] == 'admin':
        event_filter = ""
        params = []
    else:
        event_filter = "AND e.organizer_id = ?"
        params = [g.user['id']]

    tickets = conn.execute(f'''
        SELECT t.total_price, t.quantity, t.status, e.title
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        WHERE t.status = 'valid' {event_filter}
    ''', params).fetchall()

    total_revenue = sum(t['total_price'] for t in tickets)
    total_tickets = sum(t['quantity'] for t in tickets)
    commission = round(total_revenue * COMMISSION_RATE)
    net_revenue = total_revenue - commission

    events = conn.execute(f'''
        SELECT e.id, e.title, e.sold_count, e.capacity, e.price, e.status
        FROM events e
        WHERE 1=1 {event_filter.replace('e.organizer_id', 'organizer_id')}
        ORDER BY e.id
    ''', params).fetchall()

    breakdown = []
    for ev in events:
        gross = ev['sold_count'] * ev['price']
        breakdown.append({
            'event_id': ev['id'],
            'title': ev['title'],
            'sold_count': ev['sold_count'],
            'capacity': ev['capacity'],
            'gross_revenue': gross,
            'commission': round(gross * COMMISSION_RATE),
            'net_revenue': round(gross * (1 - COMMISSION_RATE)),
            'status': ev['status']
        })

    conn.close()
    return jsonify({
        'total_revenue': total_revenue,
        'total_tickets': total_tickets,
        'commission': commission,
        'net_revenue': net_revenue,
        'commission_rate': COMMISSION_RATE,
        'breakdown': breakdown
    }), 200

@organizer_bp.route('/promotions', methods=['GET'])
@role_required('organizer', 'admin')
def get_promotions():
    conn = get_db_connection()
    if g.user['role'] == 'admin':
        promotions = conn.execute('''
            SELECT p.*, e.title as event_title 
            FROM promotions p 
            JOIN events e ON p.event_id = e.id 
            ORDER BY p.id DESC
        ''').fetchall()
    else:
        promotions = conn.execute('''
            SELECT p.*, e.title as event_title 
            FROM promotions p 
            JOIN events e ON p.event_id = e.id 
            WHERE e.organizer_id = ? 
            ORDER BY p.id DESC
        ''', (g.user['id'],)).fetchall()
    conn.close()
    return jsonify([dict(p) for p in promotions]), 200

@organizer_bp.route('/promotions', methods=['POST'])
@role_required('organizer', 'admin')
def create_promotion():
    data = request.get_json()
    event_id = data.get('event_id')
    code = data.get('code', '').strip().upper()
    discount_type = data.get('discount_type')
    discount_value = data.get('discount_value')
    usage_limit = data.get('usage_limit')

    if not event_id or not code or not discount_type or not discount_value:
        return jsonify({'message': 'Eksik bilgi: event_id, code, discount_type ve discount_value zorunludur.'}), 400

    if discount_type not in ('percentage', 'fixed'):
        return jsonify({'message': 'Geçersiz indirim türü.'}), 400

    conn = get_db_connection()
    
    # Check if event belongs to organizer
    if g.user['role'] != 'admin':
        event = conn.execute('SELECT organizer_id FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event or event['organizer_id'] != g.user['id']:
            conn.close()
            return jsonify({'message': 'Bu etkinliğe promosyon ekleme yetkiniz yok.'}), 403

    try:
        conn.execute('''
            INSERT INTO promotions (event_id, code, discount_type, discount_value, usage_limit)
            VALUES (?, ?, ?, ?, ?)
        ''', (event_id, code, discount_type, int(discount_value), usage_limit if usage_limit else None))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': 'Bu kod zaten bu etkinlik için mevcut olabilir.'}), 400

    conn.close()
    return jsonify({'message': 'Promosyon başarıyla oluşturuldu.'}), 201

@organizer_bp.route('/promotions/<int:promo_id>', methods=['DELETE'])
@role_required('organizer', 'admin')
def delete_promotion(promo_id):
    conn = get_db_connection()
    promo = conn.execute('''
        SELECT p.id, e.organizer_id 
        FROM promotions p 
        JOIN events e ON p.event_id = e.id 
        WHERE p.id = ?
    ''', (promo_id,)).fetchone()

    if not promo:
        conn.close()
        return jsonify({'message': 'Promosyon bulunamadı.'}), 404

    if g.user['role'] != 'admin' and promo['organizer_id'] != g.user['id']:
        conn.close()
        return jsonify({'message': 'Bu promosyonu silme yetkiniz yok.'}), 403

    conn.execute('DELETE FROM promotions WHERE id = ?', (promo_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Promosyon başarıyla silindi.'}), 200
