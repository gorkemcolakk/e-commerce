from flask import Blueprint, jsonify, g
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
