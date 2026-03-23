from flask import Blueprint, request, jsonify, g, Response
from database import get_db_connection
from utils import role_required, event_to_dict, COMMISSION_RATE

organizer_bp = Blueprint('organizer', __name__, url_prefix='/api/organizer')

@organizer_bp.route('/events', methods=['GET'])
@role_required('organizer', 'admin')
def organizer_events():
    conn = get_db_connection()
    if g.user['role'] == 'admin':
        events = conn.execute('SELECT * FROM events ORDER BY date ASC').fetchall()
    else:
        events = conn.execute(
            'SELECT * FROM events WHERE organizer_id = ? ORDER BY date ASC',
            (g.user['id'],)
        ).fetchall()
    conn.close()
    
    # Debug log for you to see in terminal
    print(f"--- LOG: Organizator {g.user['id']} icin {len(events)} etkinlik/seans donduruldu. ---")
    
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
        WHERE t.status IN ('valid', 'used') {event_filter}
    ''', params).fetchall()

    total_revenue = sum(t['total_price'] for t in tickets)
    total_tickets = sum(t['quantity'] for t in tickets)
    commission = round(total_revenue * COMMISSION_RATE)
    net_revenue = total_revenue - commission

    # Etkinlik bazlı döküm
    events_stats = conn.execute(f'''
        SELECT 
            e.id, 
            e.title, 
            e.date,
            e.capacity, 
            e.price, 
            e.status,
            u.fullname as organizer_name,
            COALESCE(SUM(CASE WHEN t.status IN ('valid', 'used') THEN t.quantity ELSE 0 END), 0) as real_sold_count,
            COALESCE(SUM(CASE WHEN t.status IN ('valid', 'used') THEN t.total_price ELSE 0 END), 0) as real_gross
        FROM events e
        LEFT JOIN users u ON e.organizer_id = u.id
        LEFT JOIN tickets t ON e.id = t.event_id
        WHERE e.status = 'active' {event_filter}
        GROUP BY e.id
        ORDER BY e.date ASC
    ''', params).fetchall()

    breakdown = []
    for ev in events_stats:
        gross = ev['real_gross']
        # Format date and truncate long titles even more for the chart
        try:
            from datetime import datetime
            dt_obj = datetime.fromisoformat(ev['date'].replace('T', ' '))
            day_str = dt_obj.strftime('%d %b')
            
            # Shorter truncation for chart readability: 15 chars
            raw_title = ev['title']
            if len(raw_title) > 15:
                short_title = raw_title[:12] + "..."
            else:
                short_title = raw_title
            
            display_title = f"{short_title} ({day_str})"
        except:
            display_title = ev['title']

        breakdown.append({
            'event_id': ev['id'],
            'title': display_title,
            'organizer_name': ev['organizer_name'],
            'sold_count': ev['real_sold_count'],
            'capacity': ev['capacity'],
            'gross_revenue': gross,
            'commission': round(gross * COMMISSION_RATE),
            'net_revenue': round(gross * (1 - COMMISSION_RATE)),
            'status': ev['status']
        })

    organizer_breakdown = []
    if g.user['role'] == 'admin':
        orgs_stats = conn.execute('''
            SELECT 
                u.id as organizer_id,
                u.fullname as organizer_name,
                u.email as organizer_email,
                COALESCE(SUM(t.quantity), 0) as total_tickets,
                COALESCE(SUM(t.total_price), 0) as total_gross
            FROM users u
            JOIN events e ON u.id = e.organizer_id
            LEFT JOIN tickets t ON e.id = t.event_id AND t.status IN ('valid', 'used')
            WHERE u.role = 'organizer'
            GROUP BY u.id
            HAVING total_tickets > 0
            ORDER BY total_gross DESC
        ''').fetchall()
        
        for org in orgs_stats:
            gross = org['total_gross']
            organizer_breakdown.append({
                'organizer_id': org['organizer_id'],
                'name': org['organizer_name'],
                'email': org['organizer_email'],
                'total_tickets': org['total_tickets'],
                'gross_revenue': gross,
                'commission': round(gross * COMMISSION_RATE),
                'net_revenue': round(gross * (1 - COMMISSION_RATE))
            })

    conn.close()
    return jsonify({
        'total_revenue': total_revenue,
        'total_tickets': total_tickets,
        'commission': commission,
        'net_revenue': net_revenue,
        'commission_rate': COMMISSION_RATE,
        'breakdown': breakdown,
        'organizer_breakdown': organizer_breakdown
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
        return jsonify({'message': 'Missing data: event_id, code, discount_type, and discount_value are required.'}), 400

    if discount_type not in ('percentage', 'fixed'):
        return jsonify({'message': 'Invalid discount type.'}), 400

    conn = get_db_connection()
    
    # Check if event belongs to organizer
    if g.user['role'] != 'admin':
        event = conn.execute('SELECT organizer_id FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event or event['organizer_id'] != g.user['id']:
            conn.close()
            return jsonify({'message': 'You do not have permission to add a promotion to this event.'}), 403

    try:
        conn.execute('''
            INSERT INTO promotions (event_id, code, discount_type, discount_value, usage_limit)
            VALUES (?, ?, ?, ?, ?)
        ''', (event_id, code, discount_type, int(discount_value), usage_limit if usage_limit else None))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': 'This code might already exist for this event.'}), 400

    conn.close()
    return jsonify({'message': 'Promotion created successfully.'}), 201

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
        return jsonify({'message': 'Promotion not found.'}), 404

    if g.user['role'] != 'admin' and promo['organizer_id'] != g.user['id']:
        conn.close()
        return jsonify({'message': 'You do not have permission to delete this promotion.'}), 403

    conn.execute('DELETE FROM promotions WHERE id = ?', (promo_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Promotion deleted successfully.'}), 200


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDEE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _query_attendees(event_id):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT
            t.ticket_key, t.owner_name, t.owner_surname,
            u.email, u.fullname,
            t.status, t.total_price, t.quantity, t.purchase_date,
            s.zone, s.row_label, s.col_label
        FROM tickets t
        JOIN events  e ON t.event_id = e.id
        JOIN users   u ON t.user_id  = u.id
        LEFT JOIN seats s ON t.seat_id = s.id
        WHERE t.event_id = ?
        ORDER BY t.purchase_date
    ''', (event_id,)).fetchall()
    conn.close()
    return rows


def _check_event_access(event_id):
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    conn.close()
    if not event:
        return None, 'not_found'
    if g.user['role'] != 'admin' and event['organizer_id'] != g.user['id']:
        return None, 'forbidden'
    return event, None


# ── GET /api/organizer/events/<event_id>/attendees  (JSON) ────────────────────
@organizer_bp.route('/events/<event_id>/attendees', methods=['GET'])
@role_required('organizer', 'admin')
def event_attendees(event_id):
    event, err = _check_event_access(event_id)
    if not event:
        return jsonify({'message': 'Event not found or unauthorized.'}), (404 if err == 'not_found' else 403)

    rows = _query_attendees(event_id)
    attendees = []
    for r in rows:
        seat  = f"{r['zone']} {r['row_label']}-{r['col_label']}" if r['zone'] else 'General Admission'
        name  = r['owner_name']   or (r['fullname'] or '').split()[0] or '-'
        surna = r['owner_surname'] or ' '.join((r['fullname'] or '').split()[1:]) or ''
        attendees.append({
            'ticket_key':   r['ticket_key'],
            'name':         name,
            'surname':      surna,
            'full_name':    f"{name} {surna}".strip(),
            'email':        r['email'],
            'seat':         seat,
            'status':       r['status'],
            'price':        r['total_price'],
            'quantity':     r['quantity'],
            'purchased_at': (r['purchase_date'] or '')[:16],
        })
    return jsonify({
        'event_title': event['title'],
        'event_date':  event['date'],
        'total':       len(attendees),
        'attendees':   attendees
    }), 200


# ── GET /api/organizer/events/<event_id>/attendees/export  (CSV) ──────────────
@organizer_bp.route('/events/<event_id>/attendees/export', methods=['GET'])
@role_required('organizer', 'admin')
def export_attendees(event_id):
    import io, csv

    event, err = _check_event_access(event_id)
    if not event:
        return jsonify({'message': 'Event not found or unauthorized.'}), (404 if err == 'not_found' else 403)

    rows = _query_attendees(event_id)
    buf  = io.StringIO()
    w    = csv.writer(buf)
    w.writerow(['Ticket Code', 'First Name', 'Last Name', 'Email',
                'Seat / Type', 'Status', 'Price (TL)', 'Quantity', 'Purchase Date'])

    status_map = {'valid': 'Valid', 'used': 'Used',
                  'refund_pending': 'Refund Pending', 'cancelled': 'Cancelled'}

    for r in rows:
        seat = f"{r['zone']} {r['row_label']}-{r['col_label']}" if r['zone'] else 'General Admission'
        w.writerow([
            r['ticket_key'],
            r['owner_name']    or (r['fullname'] or '-').split()[0],
            r['owner_surname'] or ' '.join((r['fullname'] or '').split()[1:]) or '-',
            r['email'],
            seat,
            status_map.get(r['status'], r['status']),
            r['total_price'],
            r['quantity'],
            (r['created_at'] or r['purchase_date'] or '')[:16],
        ])

    # UTF-8 BOM — Excel opens without encoding prompt
    csv_bytes = b'\xef\xbb\xbf' + buf.getvalue().encode('utf-8')
    safe  = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in (event['title'] or 'Event'))
    fname = f"Attendees_{safe}.csv"

    return Response(
        csv_bytes,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{fname}"',
            'Content-Type': 'text/csv; charset=utf-8',
        }
    )
