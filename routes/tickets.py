import uuid
from flask import Blueprint, request, jsonify, g
from database import get_db_connection
from datetime import datetime
from utils import token_required, make_qr_base64, make_qr_bytes, create_notification, sign_ticket_data, verify_ticket_signature, send_email, send_ticket_confirmation_email, limiter

tickets_bp = Blueprint('tickets', __name__, url_prefix='/api/tickets')

# ─────────────────────────────────────────────────────────────────────────────
# GUEST TICKET PURCHASE
# ─────────────────────────────────────────────────────────────────────────────
@tickets_bp.route('/guest-buy', methods=['POST'])
@limiter.limit("5 per minute")
def guest_buy_ticket():
    data = request.get_json()
    event_id     = data.get('event_id')
    guest_email  = (data.get('guest_email') or '').strip().lower()
    guest_name   = (data.get('guest_name')  or '').strip()
    guest_surname= (data.get('guest_surname') or '').strip()
    promo_code   = data.get('promo_code', '').strip().upper()
    tickets_info = data.get('tickets_info', [])
    quantity     = len(tickets_info)

    if not event_id:
        return jsonify({'message': 'event_id is required'}), 400
    if not guest_email or '@' not in guest_email:
        return jsonify({'message': 'Please enter a valid email address'}), 400
    if quantity < 1:
        return jsonify({'message': 'Quantity must be at least 1'}), 400

    card_name   = data.get('card_name', '').strip()
    card_number = data.get('card_number', '').replace(' ', '')
    card_exp    = data.get('card_exp', '').strip()
    cvc         = data.get('cvc', '').strip()
    if not card_name or not card_number or not cvc or not card_exp:
        return jsonify({'message': 'Payment information missing!'}), 400

    conn = get_db_connection()
    c = conn.cursor()

    # User management
    existing = c.execute("SELECT * FROM users WHERE email = ? AND role = 'guest'", (guest_email,)).fetchone()
    if existing:
        guest_user_id = existing['id']
        guest_fullname = existing['fullname']
    else:
        real_user = c.execute("SELECT id FROM users WHERE email = ? AND role != 'guest'", (guest_email,)).fetchone()
        if real_user:
            conn.close()
            return jsonify({'message': 'Account exists for this email. Please log in.'}), 409
        import secrets
        from werkzeug.security import generate_password_hash
        random_pw = generate_password_hash(secrets.token_hex(32))
        guest_fullname = f"{guest_name} {guest_surname}"
        c.execute("INSERT INTO users (fullname, email, password, role) VALUES (?, ?, ?, 'guest')", (guest_fullname, guest_email, random_pw))
        guest_user_id = c.lastrowid

    # Event Check
    event = c.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Event not found'}), 404
    if event['status'] != 'active':
        conn.close()
        return jsonify({'message': 'Event is not active'}), 400

    total_price = 0
    seat_labels_str = "Standard"
    seats_dict = {}

    if event['has_seating']:
        seat_ids = [t.get('seat_id') for t in tickets_info if t.get('seat_id')]
        if len(seat_ids) != quantity:
            conn.close()
            return jsonify({'message': 'Seat selection required.'}), 400
        placeholders = ','.join(['?'] * len(seat_ids))
        seats = c.execute(f"SELECT * FROM seats WHERE id IN ({placeholders}) AND event_id = ? AND status = 'available'", seat_ids + [event_id]).fetchall()
        if len(seats) != quantity:
            conn.close()
            return jsonify({'message': 'Some seats are already sold.'}), 400
        for s in seats:
            total_price += s['price']
            seats_dict[str(s['id'])] = s
        seat_labels_str = ", ".join(f"{s['zone']} {s['row_label']}-{s['col_label']}" for s in seats)
    else:
        total_price = event['price'] * quantity

    # Promo Code
    promo_record = None
    if promo_code:
        promo_record = c.execute('SELECT * FROM promotions WHERE event_id = ? AND code = ?', (event_id, promo_code)).fetchone()
        if not promo_record:
            conn.close()
            return jsonify({'message': 'Invalid promo code.'}), 400
        if promo_record['usage_limit'] and promo_record['used_count'] >= promo_record['usage_limit']:
            conn.close()
            return jsonify({'message': 'Promo limit reached.'}), 400
        if promo_record['discount_type'] == 'percentage':
            total_price -= (total_price * promo_record['discount_value']) // 100
        else:
            total_price -= promo_record['discount_value']
        total_price = max(0, total_price)

    # PAYMENT
    from payment import PaymentGateway
    pay_res = PaymentGateway.process_payment(total_price, card_name, card_number, card_exp, cvc)
    if not pay_res['success']:
        conn.close()
        return jsonify({'message': pay_res['message']}), 400

    # UPDATE COUNTS AFTER SUCCESSFUL PAYMENT
    if event['has_seating']:
        c.execute(f"UPDATE seats SET status = 'sold' WHERE id IN ({placeholders})", seat_ids)
        c.execute("UPDATE events SET sold_count = sold_count + ? WHERE id = ?", (quantity, event_id))
    else:
        c.execute("UPDATE events SET sold_count = sold_count + ? WHERE id = ? AND capacity - sold_count >= ? AND status = 'active'", (quantity, event_id, quantity))
        if c.rowcount == 0:
            conn.close()
            return jsonify({'message': 'Capacity filled or event inactive.'}), 400

    if promo_record:
        c.execute('UPDATE promotions SET used_count = used_count + 1 WHERE id = ?', (promo_record['id'],))

    # GENERATE TICKETS
    gen_tix = []
    for t_info in tickets_info:
        key = uuid.uuid4().hex.upper()[:12]
        q_data = sign_ticket_data(f"EVENTIX-{key}-{event_id}")
        t_p = event['price'] if not event['has_seating'] else seats_dict[str(t_info['seat_id'])]['price']
        sid = t_info.get('seat_id') if event['has_seating'] else None
        
        c.execute("INSERT INTO tickets (user_id, event_id, ticket_key, qr_code, quantity, total_price, status, owner_name, owner_surname, seat_id) VALUES (?, ?, ?, ?, ?, ?, 'valid', ?, ?, ?)",
                  (guest_user_id, event_id, key, q_data, 1, t_p, t_info.get('name'), t_info.get('surname'), sid))
        
        gen_tix.append({'ticket_key': key, 'qr_code': make_qr_base64(q_data), 'name': t_info.get('name'), 'surname': t_info.get('surname'), 'price': t_p})

    conn.commit()
    conn.close()
    
    try:
        send_ticket_confirmation_email(guest_email, guest_fullname, event, gen_tix, total_price, seat_labels_str)
    except: pass

    return jsonify({'message': 'Success!', 'tickets': gen_tix, 'total_price': total_price}), 201

# ─────────────────────────────────────────────────────────────────────────────
# LOGGED-IN TICKET PURCHASE
# ─────────────────────────────────────────────────────────────────────────────
@tickets_bp.route('/buy', methods=['POST'])
@token_required
@limiter.limit("5 per minute")
def buy_ticket():
    data = request.get_json()
    event_id = data.get('event_id')
    promo_code = data.get('promo_code', '').strip().upper()
    tickets_info = data.get('tickets_info', [])
    quantity = len(tickets_info)

    if not event_id or quantity < 1:
        return jsonify({'message': 'Invalid request.'}), 400

    card_name, card_number = data.get('card_name'), data.get('card_number', '').replace(' ', '')
    card_exp, cvc = data.get('card_exp'), data.get('cvc')
    if not all([card_name, card_number, card_exp, cvc]):
        return jsonify({'message': 'Payment info missing.'}), 400

    conn = get_db_connection()
    c = conn.cursor()
    event = c.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event or event['status'] != 'active':
        conn.close()
        return jsonify({'message': 'Event not found or inactive.'}), 404

    total_price = 0
    seats_dict = {}
    seat_labels_str = "Standard"

    if event['has_seating']:
        seat_ids = [t.get('seat_id') for t in tickets_info if t.get('seat_id')]
        placeholders = ','.join(['?'] * len(seat_ids))
        seats = c.execute(f"SELECT * FROM seats WHERE id IN ({placeholders}) AND event_id = ? AND status = 'available'", seat_ids + [event_id]).fetchall()
        if len(seats) != quantity:
            conn.close()
            return jsonify({'message': 'Some seats are unavailable.'}), 400
        for s in seats:
            total_price += s['price']
            seats_dict[str(s['id'])] = s
        seat_labels_str = ", ".join(f"{s['zone']} {s['row_label']}-{s['col_label']}" for s in seats)
    else:
        total_price = event['price'] * quantity

    # PROMO
    promo_record = None
    if promo_code:
        if promo_code == 'BDAY26':
            u = c.execute('SELECT birthdate, bday_promo_used_year FROM users WHERE id = ?', (g.user['id'],)).fetchone()
            now = datetime.now()
            if not u or not u['birthdate'] or u['birthdate'][5:10] != now.strftime('%m-%d'):
                conn.close()
                return jsonify({'message': 'Only valid on your birthday.'}), 400
            if u['bday_promo_used_year'] == now.year:
                conn.close()
                return jsonify({'message': 'Already used this year.'}), 400
            promo_record = {'id': 0, 'is_bday': True, 'discount_type': 'percentage', 'discount_value': 15}
        else:
            promo_record = c.execute('SELECT * FROM promotions WHERE event_id = ? AND code = ?', (event_id, promo_code)).fetchone()
        
        if not promo_record:
            conn.close()
            return jsonify({'message': 'Invalid promo code.'}), 400
        
        if promo_record.get('discount_type') == 'percentage':
            total_price -= (total_price * promo_record['discount_value']) // 100
        else:
            total_price -= promo_record.get('discount_value', 0)
        total_price = max(0, total_price)

    # PAYMENT
    from payment import PaymentGateway
    pay_res = PaymentGateway.process_payment(total_price, card_name, card_number, card_exp, cvc)
    if not pay_res['success']:
        conn.close()
        return jsonify({'message': pay_res['message']}), 400

    # UPDATE COUNTS
    if event['has_seating']:
        c.execute(f"UPDATE seats SET status = 'sold' WHERE id IN ({placeholders})", seat_ids)
        c.execute("UPDATE events SET sold_count = sold_count + ? WHERE id = ?", (quantity, event_id))
    else:
        c.execute("UPDATE events SET sold_count = sold_count + ? WHERE id = ? AND capacity - sold_count >= ? AND status = 'active'", (quantity, event_id, quantity))

    if promo_record:
        if promo_record.get('is_bday'):
            c.execute('UPDATE users SET bday_promo_used_year = ? WHERE id = ?', (datetime.now().year, g.user['id']))
        elif promo_record.get('id', 0) != 0:
            c.execute('UPDATE promotions SET used_count = used_count + 1 WHERE id = ?', (promo_record['id'],))

    gen_tix = []
    for t_info in tickets_info:
        key = uuid.uuid4().hex.upper()[:12]
        q_data = sign_ticket_data(f"EVENTIX-{key}-{event_id}")
        t_p = event['price'] if not event['has_seating'] else seats_dict[str(t_info['seat_id'])]['price']
        sid = t_info.get('seat_id') if event['has_seating'] else None
        c.execute("INSERT INTO tickets (user_id, event_id, ticket_key, qr_code, quantity, total_price, status, owner_name, owner_surname, seat_id) VALUES (?, ?, ?, ?, ?, ?, 'valid', ?, ?, ?)",
                  (g.user['id'], event_id, key, q_data, 1, t_p, t_info.get('name'), t_info.get('surname'), sid))
        gen_tix.append({'ticket_key': key, 'qr_code': make_qr_base64(q_data), 'name': t_info.get('name'), 'surname': t_info.get('surname'), 'price': t_p})

    create_notification(conn, g.user['id'], f"Successfully purchased {quantity} tickets.")
    conn.commit()
    conn.close()
    
    try:
        send_ticket_confirmation_email(g.user['email'], g.user['fullname'], event, gen_tix, total_price, seat_labels_str)
    except: pass
    return jsonify({'message': 'Success!', 'tickets': gen_tix}), 201

# --- MY TICKETS ---
@tickets_bp.route('/my-tickets', methods=['GET'])
@token_required
def my_tickets():
    conn = get_db_connection()
    tickets = conn.execute('''
        SELECT t.id, t.ticket_key, t.qr_code, t.quantity, t.total_price,
               t.status, t.purchase_date, t.owner_name, t.owner_surname,
               e.title, e.date, e.location, e.image, e.id as event_id,
               s.zone, s.row_label, s.col_label
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        LEFT JOIN seats s ON t.seat_id = s.id
        WHERE t.user_id = ?
        ORDER BY t.id DESC
    ''', (g.user['id'],)).fetchall()
    conn.close()
    return jsonify([dict(t) for t in tickets]), 200

# --- VALIDATE ---
@tickets_bp.route('/validate_by_qr', methods=['POST'])
@token_required
def validate_by_qr():
    data = request.get_json() or {}
    qr_code = data.get('qr_code', '').strip()
    action  = data.get('action', 'check') 
    if not qr_code or not verify_ticket_signature(qr_code):
        return jsonify({'valid': False, 'message': 'Invalid signature.'}), 400
    conn = get_db_connection()
    t = conn.execute('SELECT t.*, e.organizer_id FROM tickets t JOIN events e ON t.event_id = e.id WHERE t.qr_code = ?', (qr_code,)).fetchone()
    if not t:
        conn.close()
        return jsonify({'valid': False, 'message': 'Not found.'}), 404
    if g.user['role'] == 'organizer' and t['organizer_id'] != g.user['id']:
        conn.close()
        return jsonify({'valid': False, 'message': 'No permission.'}), 403
    if action == 'use' and t['status'] == 'valid':
        conn.execute("UPDATE tickets SET status = 'used' WHERE qr_code = ?", (qr_code,))
        conn.commit()
    conn.close()
    return jsonify({'valid': True, 'ticket': dict(t)}), 200

# --- PROMO VALIDATE ---
@tickets_bp.route('/validate_promo', methods=['POST'])
@token_required
def validate_promo():
    data = request.get_json()
    eid, code = data.get('event_id'), data.get('code', '').strip().upper()
    if code == 'BDAY26':
        conn = get_db_connection()
        u = conn.execute('SELECT birthdate FROM users WHERE id = ?', (g.user['id'],)).fetchone()
        conn.close()
        if not u or u['birthdate'][5:10] != datetime.now().strftime('%m-%d'):
            return jsonify({'valid': False, 'message': 'Only on birthday.'}), 400
        return jsonify({'valid': True, 'discount_type': 'percentage', 'discount_value': 15}), 200
    conn = get_db_connection()
    p = conn.execute('SELECT * FROM promotions WHERE event_id = ? AND code = ?', (eid, code)).fetchone()
    conn.close()
    if not p: return jsonify({'valid': False}), 404
    return jsonify({'valid': True, 'discount_type': p['discount_type'], 'discount_value': p['discount_value']}), 200
