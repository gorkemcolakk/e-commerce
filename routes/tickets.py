import uuid
from flask import Blueprint, request, jsonify, g
from database import get_db_connection
from utils import token_required, make_qr_base64, make_qr_bytes, create_notification, sign_ticket_data, verify_ticket_signature, send_email, send_ticket_confirmation_email, limiter

tickets_bp = Blueprint('tickets', __name__, url_prefix='/api/tickets')


# ─────────────────────────────────────────────────────────────────────────────
# GUEST TICKET PURCHASE — No JWT required
# ─────────────────────────────────────────────────────────────────────────────
@tickets_bp.route('/guest-buy', methods=['POST'])
@limiter.limit("5 per minute")
def guest_buy_ticket():
    """
    Misafir bilet satın alma endpoint'i.
    Kullanıcı giriş yapmadan e-posta, ad, soyad ve ödeme bilgilerini göndererek bilet satın alabilir.
    """
    data = request.get_json()
    event_id     = data.get('event_id')
    guest_email  = (data.get('guest_email') or '').strip().lower()
    guest_name   = (data.get('guest_name')  or '').strip()
    guest_surname= (data.get('guest_surname') or '').strip()
    promo_code   = data.get('promo_code', '').strip().upper()
    tickets_info = data.get('tickets_info', [])
    quantity     = len(tickets_info)

    # ── Validation ──────────────────────────────────────────────
    if not event_id:
        return jsonify({'message': 'event_id is required'}), 400
    if not guest_email or '@' not in guest_email:
        return jsonify({'message': 'Please enter a valid email address'}), 400
    if not guest_name or not guest_surname:
        return jsonify({'message': 'First name and last name are required'}), 400
    if quantity < 1 or quantity > 10:
        return jsonify({'message': 'You can buy between 1 and 10 tickets at once'}), 400

    card_name   = data.get('card_name', '').strip()
    card_number = data.get('card_number', '').replace(' ', '')
    card_exp    = data.get('card_exp', '').strip()
    cvc         = data.get('cvc', '').strip()
    if not card_name or not card_number or not cvc or not card_exp:
        return jsonify({'message': 'Payment information missing! Please enter all card details.'}), 400

    conn = get_db_connection()
    c = conn.cursor()

    # ── Get or create a guest user for this e-mail ───────────────
    existing = c.execute("SELECT * FROM users WHERE email = ? AND role = 'guest'", (guest_email,)).fetchone()
    if existing:
        guest_user_id = existing['id']
        guest_fullname = existing['fullname']
    else:
        # Also check if a real account with this email already exists
        real_user = c.execute("SELECT id FROM users WHERE email = ? AND role != 'guest'", (guest_email,)).fetchone()
        if real_user:
            conn.close()
            return jsonify({'message': 'An account is already registered with this email. Please log in to purchase.'}), 409

        import secrets
        from werkzeug.security import generate_password_hash
        random_pw = generate_password_hash(secrets.token_hex(32))
        guest_fullname = f"{guest_name} {guest_surname}"
        c.execute(
            "INSERT INTO users (fullname, email, password, role) VALUES (?, ?, ?, 'guest')",
            (guest_fullname, guest_email, random_pw)
        )
        guest_user_id = c.lastrowid

    # ── Event check ─────────────────────────────────────────────
    event = c.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Event not found'}), 404
    if event['status'] == 'cancelled':
        conn.close()
        return jsonify({'message': 'This event has been cancelled'}), 400

    total_price = 0
    seat_labels_str = "Standard"
    seats_dict = {}

    if event['has_seating']:
        seat_ids = [t.get('seat_id') for t in tickets_info if t.get('seat_id')]
        if len(seat_ids) != quantity:
            conn.close()
            return jsonify({'message': 'Seat selection is required for each ticket in events with a seating plan.'}), 400

        placeholders = ','.join(['?'] * len(seat_ids))
        params = list(seat_ids) + [event_id]
        seats = c.execute(
            f"SELECT * FROM seats WHERE id IN ({placeholders}) AND event_id = ? AND status = 'available'",
            params
        ).fetchall()

        if len(seats) != quantity:
            conn.close()
            return jsonify({'message': 'Some of the seats you selected are sold or invalid.'}), 400

        for s in seats:
            total_price += s['price']
            seats_dict[str(s['id'])] = s
        seat_labels_str = ", ".join(f"{s['zone']} {s['row_label']}-{s['col_label']}" for s in seats)
        c.execute(f"UPDATE seats SET status = 'sold' WHERE id IN ({placeholders})", seat_ids)
        c.execute("UPDATE events SET sold_count = sold_count + ? WHERE id = ?", (quantity, event_id))
    else:
        c.execute(
            "UPDATE events SET sold_count = sold_count + ? WHERE id = ? AND capacity - sold_count >= ? AND status = 'active'",
            (quantity, event_id, quantity)
        )
        if c.rowcount == 0:
            rechk = c.execute('SELECT capacity, sold_count FROM events WHERE id = ?', (event_id,)).fetchone()
            remaining = rechk['capacity'] - rechk['sold_count']
            conn.close()
            if remaining <= 0:
                return jsonify({'message': 'Capacity full! No tickets left for this event.'}), 400
            return jsonify({'message': f'Only {remaining} tickets left'}), 400

        unit_price  = event['price']
        total_price = unit_price * quantity

    # ── Promo code ──────────────────────────────────────────────
    promo_record = None
    if promo_code:
        if promo_code == 'BDAY26':
            conn.close()
            return jsonify({'message': 'Please log in to your account to use your birthday promotion.'}), 400
        else:
            promo_record = c.execute(
                'SELECT * FROM promotions WHERE event_id = ? AND code = ?', (event_id, promo_code)
            ).fetchone()
            
        if not promo_record:
            conn.close()
            return jsonify({'message': 'Invalid promotion code.'}), 400
        if promo_record['usage_limit'] and promo_record['used_count'] >= promo_record['usage_limit']:
            conn.close()
            return jsonify({'message': "Promotion code's usage limit has been reached."}), 400

        if promo_record['discount_type'] == 'percentage':
            total_price -= (total_price * promo_record['discount_value']) // 100
        elif promo_record['discount_type'] == 'fixed':
            total_price -= promo_record['discount_value']
        if total_price < 0:
            total_price = 0

    # ── Payment ──────────────────────────────────────────────────
    from payment import PaymentGateway
    payment_result = PaymentGateway.process_payment(
        amount=total_price,
        card_name=card_name,
        card_number=card_number,
        exp_date=card_exp,
        cvc=cvc
    )
    if not payment_result['success']:
        conn.close()
        return jsonify({'message': payment_result['message']}), 400

    if promo_record and promo_record.get('id', 0) != 0:
        c.execute('UPDATE promotions SET used_count = used_count + 1 WHERE id = ?', (promo_record['id'],))

    # ── Generate tickets ─────────────────────────────────────────
    generated_tickets = []
    email_images = []

    for t_info in tickets_info:
        ticket_key = uuid.uuid4().hex.upper()[:12]
        qr_data    = sign_ticket_data(f"EVENTIX-{ticket_key}-{event_id}")
        qr_base64  = make_qr_base64(qr_data)
        qr_bytes   = make_qr_bytes(qr_data)
        qr_cid     = f"qr_{ticket_key}"

        t_price    = event['price'] if not event['has_seating'] else seats_dict[str(t_info['seat_id'])]['price']
        seat_id_val = t_info.get('seat_id') if event['has_seating'] else None
        
        seat_info = ""
        if event['has_seating'] and seat_id_val:
            s_obj = seats_dict.get(str(seat_id_val))
            if s_obj:
                seat_info = f"{s_obj['zone']} {s_obj['row_label']}-{s_obj['col_label']}"

        c.execute(
            "INSERT INTO tickets (user_id, event_id, ticket_key, qr_code, quantity, total_price, status, owner_name, owner_surname, seat_id) "
            "VALUES (?, ?, ?, ?, ?, ?, 'valid', ?, ?, ?)",
            (guest_user_id, event_id, ticket_key, qr_data, 1, t_price,
             t_info.get('name'), t_info.get('surname'), seat_id_val)
        )
        email_images.append({'cid': qr_cid, 'data': qr_bytes})
        generated_tickets.append({
            'ticket_key': ticket_key,
            'qr_code':    qr_base64,
            'qr_data':    qr_data,
            'name':       t_info.get('name'),
            'surname':    t_info.get('surname'),
            'price':      t_price,
            'seat_info':  seat_info
        })

    conn.commit()
    conn.close()

    # ── Confirmation e-mail ──────────────────────────────────────
    try:
        send_ticket_confirmation_email(
            guest_email, 
            guest_fullname, 
            event, 
            generated_tickets, 
            total_price, 
            seat_labels_str
        )
    except Exception as e:
        print(f"Error sending guest confirmation email: {e}")

    return jsonify({
        'message': 'Ticket purchased! Your tickets have been sent to your email address.',
        'tickets': generated_tickets,
        'total_price': total_price,
        'quantity': quantity
    }), 201

@tickets_bp.route('/buy', methods=['POST'])
@token_required
@limiter.limit("5 per minute")
def buy_ticket():
    import time
    data = request.get_json()
    event_id = data.get('event_id')
    promo_code = data.get('promo_code', '').strip().upper()
    # tickets_info = [{"name": "...", "surname": "...", ("seat_id": "X")}]
    tickets_info = data.get('tickets_info', [])
    quantity = len(tickets_info)

    if not event_id:
        return jsonify({'message': 'event_id is required'}), 400
    if quantity < 1 or quantity > 10:
        return jsonify({'message': 'You can buy between 1 and 10 tickets at once'}), 400

    # Payment info
    card_name = data.get('card_name', '').strip()
    card_number = data.get('card_number', '').replace(' ', '')
    card_exp = data.get('card_exp', '').strip()
    cvc = data.get('cvc', '').strip()

    if not card_name or not card_number or not cvc or not card_exp:
        return jsonify({'message': 'Payment information missing! Please enter all card details.'}), 400

    conn = get_db_connection()
    c = conn.cursor()

    event = c.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Event not found'}), 404
    if event['status'] == 'cancelled':
        conn.close()
        return jsonify({'message': 'This event has been cancelled'}), 400

    total_price = 0
    seat_labels_str = "Standard"
    seats_dict = {}

    if event['has_seating']:
        seat_ids = [t.get('seat_id') for t in tickets_info if t.get('seat_id')]
        if len(seat_ids) != quantity:
             conn.close()
             return jsonify({'message': 'Seat selection is required for each ticket in events with a seating plan.'}), 400

        placeholders = ','.join(['?'] * len(seat_ids))
        params = list(seat_ids)
        params.append(event_id)
        
        # Lock seats
        seats = c.execute(f"SELECT * FROM seats WHERE id IN ({placeholders}) AND event_id = ? AND status = 'available'", params).fetchall()
        
        if len(seats) != quantity:
            conn.close()
            return jsonify({'message': 'Some of the seats you selected are sold or invalid. Please try again.'}), 400
            
        for s in seats:
            total_price += s['price']
            seats_dict[str(s['id'])] = s
            
        seat_labels = [f"{s['zone']} {s['row_label']}-{s['col_label']}" for s in seats]
        seat_labels_str = ", ".join(seat_labels)
        
        # Mark seats as sold
        c.execute(f"UPDATE seats SET status = 'sold' WHERE id IN ({placeholders})", seat_ids)
        
        # Update event capacity
        c.execute("UPDATE events SET sold_count = sold_count + ? WHERE id = ?", (quantity, event_id))
    else:
        # Non-seated atomic update
        c.execute('''
            UPDATE events 
            SET sold_count = sold_count + ? 
            WHERE id = ? AND capacity - sold_count >= ? AND status = 'active'
        ''', (quantity, event_id, quantity))

        if c.rowcount == 0:
            event_recheck = c.execute('SELECT capacity, sold_count FROM events WHERE id = ?', (event_id,)).fetchone()
            remaining = event_recheck['capacity'] - event_recheck['sold_count']
            conn.close()
            if remaining <= 0:
                return jsonify({'message': 'Capacity full! No tickets left for this event.'}), 400
            else:
                return jsonify({'message': f'Only {remaining} tickets left'}), 400
                
        unit_price = event['price']
        total_price = unit_price * quantity

    promo_record = None
    if promo_code:
        if promo_code == 'BDAY26':
            user_bday_check = c.execute('SELECT birthdate, bday_promo_used_year FROM users WHERE id = ?', (g.user['id'],)).fetchone()
            from datetime import datetime
            now_dt = datetime.now()
            today_md = now_dt.strftime('%m-%d')
            c_bdate = user_bday_check['birthdate'] if user_bday_check else ''
            
            if not c_bdate or len(c_bdate) < 10 or c_bdate[5:10] != today_md:
                conn.close()
                return jsonify({'message': 'This special discount code is only valid on your birthday!'}), 400
                
            if user_bday_check['bday_promo_used_year'] == now_dt.year:
                conn.close()
                return jsonify({'message': 'You have already used your birthday code this year!'}), 400
                
            promo_record = {'id': 0, 'discount_type': 'percentage', 'discount_value': 15, 'usage_limit': None, 'used_count': 0, 'is_bday': True}
        else:
            promo_record = c.execute('SELECT * FROM promotions WHERE event_id = ? AND code = ?', (event_id, promo_code)).fetchone()
            
        if not promo_record:
            conn.close()
            return jsonify({'message': 'Invalid promotion code.'}), 400
        if promo_record['usage_limit'] and promo_record['used_count'] >= promo_record['usage_limit']:
            conn.close()
            return jsonify({'message': "Promotion code's usage limit has been reached."}), 400

        # Apply discount to total_price
        if promo_record['discount_type'] == 'percentage':
            discount_amount = (total_price * promo_record['discount_value']) // 100
            total_price -= discount_amount
        elif promo_record['discount_type'] == 'fixed':
            total_price -= promo_record['discount_value']
            
        if total_price < 0:
            total_price = 0

    # ─────────────────────────────────────────────
    # PAYMENT GATEWAY (Sanal POS İşlemi)
    # ─────────────────────────────────────────────
    from payment import PaymentGateway
    payment_result = PaymentGateway.process_payment(
        amount=total_price,
        card_name=card_name,
        card_number=card_number,
        exp_date=card_exp,
        cvc=cvc
    )
    
    # Eğer kart reddedilirse / bakiye yetersizse işlemleri iptal et (rollback yap)
    if not payment_result['success']:
        conn.close() # SQL tarafında commit edilmediği için tüm güncelleme veya koltuk kilitleme iptal olur.
        return jsonify({'message': payment_result['message']}), 400

    # İşlem başarılı. Promosyon kodu kullanıldıysa sayacını artır veya doğum yılını işaretle.
    if promo_record:
        if promo_record.get('is_bday'):
            from datetime import datetime
            c.execute('UPDATE users SET bday_promo_used_year = ? WHERE id = ?', (datetime.now().year, g.user['id']))
        elif promo_record.get('id', 0) != 0:
            c.execute('UPDATE promotions SET used_count = used_count + 1 WHERE id = ?', (promo_record['id'],))

    generated_tickets = []
    email_images = []
    for t_info in tickets_info:
        ticket_key = uuid.uuid4().hex.upper()[:12]
        qr_data = sign_ticket_data(f"EVENTIX-{ticket_key}-{event_id}")
        qr_base64 = make_qr_base64(qr_data)
        qr_bytes = make_qr_bytes(qr_data)
        qr_cid = f"qr_{ticket_key}"
        
        t_price = unit_price if not event['has_seating'] else seats_dict[str(t_info['seat_id'])]['price']
        seat_id_val = t_info.get('seat_id') if event['has_seating'] else None
        
        seat_info = ""
        if event['has_seating'] and seat_id_val:
            s_obj = seats_dict.get(str(seat_id_val))
            if s_obj:
                seat_info = f"{s_obj['zone']} {s_obj['row_label']}-{s_obj['col_label']}"

        c.execute('''
            INSERT INTO tickets (user_id, event_id, ticket_key, qr_code, quantity, total_price, status, owner_name, owner_surname, seat_id)
            VALUES (?, ?, ?, ?, ?, ?, 'valid', ?, ?, ?)
        ''', (g.user['id'], event_id, ticket_key, qr_data, 1, t_price, t_info.get('name'), t_info.get('surname'), seat_id_val))
        
        email_images.append({'cid': qr_cid, 'data': qr_bytes})
        generated_tickets.append({
            'ticket_key': ticket_key,
            'qr_code': qr_base64,
            'name': t_info.get('name'),
            'surname': t_info.get('surname'),
            'price': t_price,
            'seat_info': seat_info
        })

    create_notification(
        conn, g.user['id'],
        f"{quantity} tickets for the event '{event['title']}' were successfully purchased."
    )

    conn.commit()
    conn.close()

    # ── Confirmation e-mail ──────────────────────────────────────
    try:
        send_ticket_confirmation_email(
            g.user['email'], 
            g.user['fullname'], 
            event, 
            generated_tickets, 
            total_price, 
            seat_labels_str
        )
    except Exception as e:
        print(f"Error sending ticket confirmation email: {e}")

    return jsonify({
        'message': 'Ticket purchased!',
        'tickets': generated_tickets,
        'total_price': total_price,
        'quantity': quantity
    }), 201

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

@tickets_bp.route('/validate/<qr_code>', methods=['GET', 'POST'])
@token_required
def validate_ticket(qr_code):
    if not verify_ticket_signature(qr_code):
        return jsonify({'valid': False, 'message': 'Ticket signature is invalid or fake ticket!'}), 400

    conn = get_db_connection()
    ticket = conn.execute('''
        SELECT t.*, e.title, e.date, e.location, u.fullname
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        JOIN users u ON t.user_id = u.id
        WHERE t.qr_code = ?
    ''', (qr_code,)).fetchone()

    if not ticket:
        conn.close()
        return jsonify({'valid': False, 'message': 'QR code not found'}), 404

    if ticket['status'] == 'used':
        conn.close()
        return jsonify({
            'valid': False,
            'status': 'already_used',
            'message': 'This ticket has already been used!',
            'ticket': dict(ticket)
        }), 200

    if ticket['status'] == 'refund_pending':
        conn.close()
        return jsonify({
            'valid': False,
            'status': 'refund_pending',
            'message': 'This ticket is in the refund process!',
            'ticket': dict(ticket)
        }), 200

    if request.method == 'POST':
        conn.execute("UPDATE tickets SET status = 'used' WHERE qr_code = ?", (qr_code,))
        conn.commit()

    conn.close()
    return jsonify({
        'valid': True,
        'status': 'valid',
        'message': '✓ Valid Ticket',
        'ticket': dict(ticket)
    }), 200

@tickets_bp.route('/validate_by_qr', methods=['POST'])
@token_required
def validate_by_qr():
    """
    Daha güvenli ve esnek QR doğrulama endpoint'i.
    qr_code ve opsiyonel event_id POST body'sinden alınır.
    action = 'check' (sadece kontrol) veya 'use' (kullanıldı olarak işaretle)
    Eğer event_id gönderilirse, biletin o etkinliğe ait olup olmadığı kontrol edilir.
    """
    data = request.get_json() or {}
    qr_code = data.get('qr_code', '').strip()
    action  = data.get('action', 'check')   # 'check' veya 'use'
    event_id_filter = data.get('event_id')  # Opsiyonel: organizatör filtresi

    if not qr_code:
        return jsonify({'valid': False, 'message': 'QR code not entered.'}), 400

    # İmza doğrulaması
    if not verify_ticket_signature(qr_code):
        return jsonify({'valid': False, 'message': 'Ticket signature is invalid or fake ticket!'}), 400

    conn = get_db_connection()
    ticket = conn.execute('''
        SELECT t.*, e.title, e.date, e.location, e.organizer_id, u.fullname, u.email
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        JOIN users u ON t.user_id = u.id
        WHERE t.qr_code = ?
    ''', (qr_code,)).fetchone()

    if not ticket:
        conn.close()
        return jsonify({'valid': False, 'message': 'QR code not found. Ticket is not registered in the system.'}), 404

    # Eğer organizatör kendi etkinliğini filtrelemediyse kontrol et
    if event_id_filter:
        if str(ticket['event_id']) != str(event_id_filter):
            conn.close()
            return jsonify({'valid': False, 'message': 'This QR code does not belong to the selected event!'}), 400

    # Rol kontrolü: sadece organizatör kendi etkinliğini doğrulayabilir (admin hepsini)
    if g.user['role'] == 'organizer' and ticket['organizer_id'] != g.user['id']:
        conn.close()
        return jsonify({'valid': False, 'message': 'You do not have permission for this event\'s ticket.'}), 403

    ticket_dict = dict(ticket)

    if ticket['status'] == 'used':
        conn.close()
        return jsonify({
            'valid': False,
            'status': 'already_used',
            'message': 'This ticket has already been used!',
            'ticket': ticket_dict
        }), 200

    if ticket['status'] == 'refund_pending':
        conn.close()
        return jsonify({
            'valid': False,
            'status': 'refund_pending',
            'message': 'This ticket is in the refund process, invalid!',
            'ticket': ticket_dict
        }), 200

    if action == 'use':
        conn.execute("UPDATE tickets SET status = 'used' WHERE qr_code = ?", (qr_code,))
        conn.commit()
        ticket_dict['status'] = 'used'

    conn.close()
    return jsonify({
        'valid': True,
        'status': 'used' if action == 'use' else 'valid',
        'message': '✓ Valid Ticket' + (' - Marked as used.' if action == 'use' else ''),
        'ticket': ticket_dict
    }), 200


@tickets_bp.route('/validate_promo', methods=['POST'])
@token_required
def validate_promo():
    data = request.get_json()
    event_id = data.get('event_id')
    code = data.get('code', '').strip().upper()

    if not event_id or not code:
        return jsonify({'valid': False, 'message': 'Missing information.'}), 400

    if code == 'BDAY26':
        conn = get_db_connection()
        user_check = conn.execute('SELECT birthdate, bday_promo_used_year FROM users WHERE id = ?', (g.user['id'],)).fetchone()
        conn.close()
        
        from datetime import datetime
        now = datetime.now()
        today_md = now.strftime('%m-%d')
        bdate = user_check['birthdate'] if user_check else ''
        
        if not bdate or len(bdate) < 10 or bdate[5:10] != today_md:
            return jsonify({'valid': False, 'message': 'This special discount code is only valid on your birthday!'}), 400
            
        if user_check['bday_promo_used_year'] == now.year:
            return jsonify({'valid': False, 'message': 'You have already used your birthday code this year!'}), 400
            
        return jsonify({
            'valid': True,
            'discount_type': 'percentage',
            'discount_value': 15,
            'message': 'Birthday discount successfully applied! 🎉'
        }), 200

    conn = get_db_connection()
    promo = conn.execute('''
        SELECT * FROM promotions 
        WHERE event_id = ? AND code = ?
    ''', (event_id, code)).fetchone()

    conn.close()

    if not promo:
        return jsonify({'valid': False, 'message': 'Invalid discount code.'}), 404

    if promo['usage_limit'] and promo['used_count'] >= promo['usage_limit']:
        return jsonify({'valid': False, 'message': "This discount code's usage limit has been reached."}), 400

    return jsonify({
        'valid': True,
        'discount_type': promo['discount_type'],
        'discount_value': promo['discount_value'],
        'message': 'Discount code successfully applied!'
    }), 200
