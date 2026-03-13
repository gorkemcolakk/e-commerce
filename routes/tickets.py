import uuid
from flask import Blueprint, request, jsonify, g
from database import get_db_connection
from utils import token_required, make_qr_base64, make_qr_bytes, create_notification, sign_ticket_data, verify_ticket_signature, send_email, limiter

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
        return jsonify({'message': 'event_id zorunludur'}), 400
    if not guest_email or '@' not in guest_email:
        return jsonify({'message': 'Geçerli bir e-posta adresi giriniz'}), 400
    if not guest_name or not guest_surname:
        return jsonify({'message': 'Ad ve soyad zorunludur'}), 400
    if quantity < 1 or quantity > 10:
        return jsonify({'message': 'Tek seferde 1 ile 10 arasında bilet alabilirsiniz'}), 400

    card_name   = data.get('card_name', '').strip()
    card_number = data.get('card_number', '').replace(' ', '')
    card_exp    = data.get('card_exp', '').strip()
    cvc         = data.get('cvc', '').strip()
    if not card_name or not card_number or not cvc or not card_exp:
        return jsonify({'message': 'Ödeme bilgileri eksik! Lütfen tüm kart bilgilerinizi giriniz.'}), 400

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
            return jsonify({'message': 'Bu e-posta ile kayıtlı bir hesap mevcut. Lütfen giriş yaparak satın alın.'}), 409

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
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404
    if event['status'] == 'cancelled':
        conn.close()
        return jsonify({'message': 'Bu etkinlik iptal edildi'}), 400

    total_price = 0
    seat_labels_str = "Standart"
    seats_dict = {}

    if event['has_seating']:
        seat_ids = [t.get('seat_id') for t in tickets_info if t.get('seat_id')]
        if len(seat_ids) != quantity:
            conn.close()
            return jsonify({'message': 'Oturma planlı etkinlikler için her biletin koltuk seçimi zorunludur.'}), 400

        placeholders = ','.join(['?'] * len(seat_ids))
        params = list(seat_ids) + [event_id]
        seats = c.execute(
            f"SELECT * FROM seats WHERE id IN ({placeholders}) AND event_id = ? AND status = 'available'",
            params
        ).fetchall()

        if len(seats) != quantity:
            conn.close()
            return jsonify({'message': 'Seçtiğiniz koltuklardan bazıları satılmış veya geçersiz.'}), 400

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
                return jsonify({'message': 'Kapasite dolu! Bu etkinlik için bilet kalmadı.'}), 400
            return jsonify({'message': f'Yalnızca {remaining} bilet kaldı'}), 400

        unit_price  = event['price']
        total_price = unit_price * quantity

    # ── Promo code ──────────────────────────────────────────────
    promo_record = None
    if promo_code:
        promo_record = c.execute(
            'SELECT * FROM promotions WHERE event_id = ? AND code = ?', (event_id, promo_code)
        ).fetchone()
        if not promo_record:
            conn.close()
            return jsonify({'message': 'Geçersiz promosyon kodu.'}), 400
        if promo_record['usage_limit'] and promo_record['used_count'] >= promo_record['usage_limit']:
            conn.close()
            return jsonify({'message': 'Promosyon kodunun kullanım hakkı dolmuş.'}), 400

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

    if promo_record:
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
            'price':      t_price
        })

    # ── Confirmation e-mail ──────────────────────────────────────
    plain_body = f"Merhaba {guest_fullname},\n\n'{event['title']}' için biletleriniz oluşturuldu.\n\n"
    for gt in generated_tickets:
        plain_body += f"🎟️ {gt['name']} {gt['surname']} | #{gt['ticket_key']}\n"
    # Rebuild proper HTML with correct CIDs
    tickets_html_parts = ""
    for gt, ei in zip(generated_tickets, email_images):
        tickets_html_parts += f"""
        <div style="border:1px dashed #ccc;padding:15px;margin-bottom:15px;text-align:center;border-radius:8px;background:#fafafa;">
          <p style="margin:0 0 10px;font-weight:bold;">{gt['name']} {gt['surname']}</p>
          <img src="cid:{ei['cid']}" alt="QR Kod" style="width:180px;height:180px;display:block;margin:0 auto;border-radius:5px;" />
          <p style="margin:10px 0 0;font-family:monospace;font-size:1.1em;color:#8b5cf6;">#{gt['ticket_key']}</p>
        </div>"""

    final_html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f4f4f9;padding:20px;color:#333;">
      <div style="max-width:600px;margin:0 auto;background:white;border-radius:10px;padding:25px;box-shadow:0 4px 10px rgba(0,0,0,0.1);">
        <h2 style="color:#8b5cf6;text-align:center;">🎟️ Biletleriniz Hazır!</h2>
        <p>Merhaba <strong>{guest_fullname}</strong>,</p>
        <p><strong>{event['title']}</strong> için biletleriniz oluşturuldu.</p>
        <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
        <p>📅 <strong>Tarih:</strong> {event['date']}<br>
           📍 <strong>Konum:</strong> {event['location']}<br>
           🪑 <strong>Koltuk(lar):</strong> {seat_labels_str}<br>
           💳 <strong>Ödenen Tutar:</strong> {total_price} ₺</p>
        <h3>Biletler:</h3>
        {tickets_html_parts}
        <p style="text-align:center;color:#999;font-size:0.85em;">© 2026 Eventix Biletleme Platformu</p>
      </div></body></html>"""

    send_email(
        guest_email,
        f"Biletleriniz Hazır - {event['title']}",
        plain_body,
        final_html,
        images=email_images
    )

    conn.commit()
    conn.close()

    return jsonify({
        'message': 'Bilet satın alındı! Biletleriniz e-posta adresinize gönderildi.',
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
        return jsonify({'message': 'event_id zorunludur'}), 400
    if quantity < 1 or quantity > 10:
        return jsonify({'message': 'Tek seferde 1 ile 10 arasında bilet alabilirsiniz'}), 400

    # Payment info
    card_name = data.get('card_name', '').strip()
    card_number = data.get('card_number', '').replace(' ', '')
    card_exp = data.get('card_exp', '').strip()
    cvc = data.get('cvc', '').strip()

    if not card_name or not card_number or not cvc or not card_exp:
        return jsonify({'message': 'Ödeme bilgileri eksik! Lütfen tüm kart bilgilerinizi giriniz.'}), 400

    conn = get_db_connection()
    c = conn.cursor()

    event = c.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404
    if event['status'] == 'cancelled':
        conn.close()
        return jsonify({'message': 'Bu etkinlik iptal edildi'}), 400

    total_price = 0
    seat_labels_str = "Standart"
    seats_dict = {}

    if event['has_seating']:
        seat_ids = [t.get('seat_id') for t in tickets_info if t.get('seat_id')]
        if len(seat_ids) != quantity:
             conn.close()
             return jsonify({'message': 'Oturma planlı etkinlikler için her biletin koltuk seçimi zorunludur.'}), 400

        placeholders = ','.join(['?'] * len(seat_ids))
        params = list(seat_ids)
        params.append(event_id)
        
        # Lock seats
        seats = c.execute(f"SELECT * FROM seats WHERE id IN ({placeholders}) AND event_id = ? AND status = 'available'", params).fetchall()
        
        if len(seats) != quantity:
            conn.close()
            return jsonify({'message': 'Seçtiğiniz koltuklardan bazıları satılmış veya geçersiz. Lütfen tekrar deneyin.'}), 400
            
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
                return jsonify({'message': 'Kapasite dolu! Bu etkinlik için bilet kalmadı.'}), 400
            else:
                return jsonify({'message': f'Yalnızca {remaining} bilet kaldı'}), 400
                
        unit_price = event['price']
        total_price = unit_price * quantity

    promo_record = None
    if promo_code:
        promo_record = c.execute('SELECT * FROM promotions WHERE event_id = ? AND code = ?', (event_id, promo_code)).fetchone()
        if not promo_record:
            conn.close()
            return jsonify({'message': 'Geçersiz promosyon kodu.'}), 400
        if promo_record['usage_limit'] and promo_record['used_count'] >= promo_record['usage_limit']:
            conn.close()
            return jsonify({'message': 'Promosyon kodunun kullanım hakkı dolmuş.'}), 400

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

    # İşlem başarılı. Promosyon kodu kullanıldıysa sayacını artır.
    if promo_record:
        c.execute('UPDATE promotions SET used_count = used_count + 1 WHERE id = ?', (promo_record['id'],))

    generated_tickets = []
    for t_info in tickets_info:
        ticket_key = uuid.uuid4().hex.upper()[:12]
        qr_data = sign_ticket_data(f"EVENTIX-{ticket_key}-{event_id}")
        qr_base64 = make_qr_base64(qr_data)
        
        qr_bytes = make_qr_bytes(qr_data)   # Ham PNG byte'ları (e-posta CID için)
        qr_cid = f"qr_{ticket_key}"            # Benzersiz CID
        
        t_price = unit_price if not event['has_seating'] else seats_dict[str(t_info['seat_id'])]['price']
        seat_id_val = t_info.get('seat_id') if event['has_seating'] else None
        
        c.execute('''
            INSERT INTO tickets (user_id, event_id, ticket_key, qr_code, quantity, total_price, status, owner_name, owner_surname, seat_id)
            VALUES (?, ?, ?, ?, ?, ?, 'valid', ?, ?, ?)
        ''', (g.user['id'], event_id, ticket_key, qr_data, 1, t_price, t_info.get('name'), t_info.get('surname'), seat_id_val))
        
        generated_tickets.append({
            'ticket_key': ticket_key,
            'qr_code': qr_base64,
            'qr_data': qr_data,
            'qr_bytes': qr_bytes,
            'qr_cid': qr_cid,
            'name': t_info.get('name'),
            'surname': t_info.get('surname'),
            'price': t_price
        })

    create_notification(
        conn, g.user['id'],
        f"'{event['title']}' etkinliği için {quantity} adet bilet başarıyla satın alındı."
    )

    email_body = f"Merhaba {g.user['fullname']},\n\n'{event['title']}' etkinliği için biletleriniz başarıyla oluşturuldu.\n\n"
    
    # CID gömülü resimler için liste
    email_images = []
    
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; padding: 20px; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 25px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
          <div style="text-align: center; margin-bottom: 20px;">
            <h2 style="color: #8b5cf6; margin: 0;">🎟️ Biletleriniz Hazır!</h2>
          </div>
          <p>Merhaba <strong>{g.user['fullname']}</strong>,</p>
          <p><strong>{event['title']}</strong> etkinliği için biletleriniz başarıyla oluşturuldu.</p>
          <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
          <p style="font-size: 0.95em; line-height: 1.6;">
             📅 <strong>Tarih:</strong> {event['date']}<br>
             📍 <strong>Konum:</strong> {event['location']}<br>
             🪑 <strong>Koltuk(lar):</strong> {seat_labels_str}<br>
             💳 <strong>Ödenen Tutar:</strong> {total_price} ₺
          </p>
          <h3 style="margin-top: 30px; border-bottom: 2px solid #f4f4f9; padding-bottom: 10px;">Biletler:</h3>
    """

    for gt in generated_tickets:
         email_body += f"🎟️ İsim: {gt['name']} {gt['surname']} | Bilet Kodunuz: #{gt['ticket_key']}\n"
         # CID listesine ekle
         email_images.append({'cid': gt['qr_cid'], 'data': gt['qr_bytes']})
         html_body += f"""
          <div style="border: 1px dashed #ccc; padding: 15px; margin-bottom: 15px; text-align: center; border-radius: 8px; background-color: #fafafa;">
            <p style="margin: 0 0 10px; font-weight: bold; color: #333;">Yolcu: {gt['name']} {gt['surname']}</p>
            <img src="cid:{gt['qr_cid']}" alt="QR Kod" style="width: 180px; height: 180px; display: block; margin: 0 auto; border-radius: 5px;" />
            <p style="margin: 10px 0 0; font-family: monospace; font-size: 1.1em; color: #8b5cf6; letter-spacing: 1px;">#{gt['ticket_key']}</p>
          </div>
         """

    email_body += f"\n📅 Tarih: {event['date']}\n📍 Konum: {event['location']}\n🪑 Koltuk(lar): {seat_labels_str}\n💳 Toplam Tutar: {total_price} ₺\n\nQR biletlerinizi portalımızdan 'Biletlerim' kısmına giderek görüntüleyebilirsiniz.\n"

    html_body += f"""
          <p style="text-align: center; margin-top: 30px; color: #666; font-size: 0.9em;">
             Biletlerinizi portalımız üzerinden 
             <a href="http://localhost:5000/dashboard.html" style="color: #ec4899; text-decoration: none; font-weight: bold;">Biletlerim</a> 
             kısmına giderek de görüntüleyebilirsiniz.
          </p>
          <div style="text-align: center; margin-top: 20px; font-size: 0.8em; color: #aaa;">
            &copy; 2026 Eventix Biletleme Platformu. Tüm Hakları Saklıdır.
          </div>
        </div>
      </body>
    </html>
    """

    send_email(g.user['email'], f"Biletleriniz Hazır - {event['title']}", email_body, html_body, images=email_images)

    conn.commit()
    conn.close()

    return jsonify({
        'message': 'Bilet satın alındı!',
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
        return jsonify({'valid': False, 'message': 'Bilet imzası geçersiz veya sahte bilet!'}), 400

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
        return jsonify({'valid': False, 'message': 'QR kod bulunamadı'}), 404

    if ticket['status'] == 'used':
        conn.close()
        return jsonify({
            'valid': False,
            'status': 'already_used',
            'message': 'Bu bilet daha önce kullanıldı!',
            'ticket': dict(ticket)
        }), 200

    if ticket['status'] == 'refund_pending':
        conn.close()
        return jsonify({
            'valid': False,
            'status': 'refund_pending',
            'message': 'Bu bilet iade sürecinde!',
            'ticket': dict(ticket)
        }), 200

    if request.method == 'POST':
        conn.execute("UPDATE tickets SET status = 'used' WHERE qr_code = ?", (qr_code,))
        conn.commit()

    conn.close()
    return jsonify({
        'valid': True,
        'status': 'valid',
        'message': '✓ Geçerli Bilet',
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
        return jsonify({'valid': False, 'message': 'QR kod girilmedi.'}), 400

    # İmza doğrulaması
    if not verify_ticket_signature(qr_code):
        return jsonify({'valid': False, 'message': 'Bilet imzası geçersiz veya sahte bilet!'}), 400

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
        return jsonify({'valid': False, 'message': 'QR kod bulunamadı. Bilet sistemde kayıtlı değil.'}), 404

    # Eğer organizatör kendi etkinliğini filtrelemediyse kontrol et
    if event_id_filter:
        if str(ticket['event_id']) != str(event_id_filter):
            conn.close()
            return jsonify({'valid': False, 'message': 'Bu QR kodu seçili etkinliğe ait değil!'}), 400

    # Rol kontrolü: sadece organizatör kendi etkinliğini doğrulayabilir (admin hepsini)
    if g.user['role'] == 'organizer' and ticket['organizer_id'] != g.user['id']:
        conn.close()
        return jsonify({'valid': False, 'message': 'Bu etkinliğin bileti için yetkiniz yok.'}), 403

    ticket_dict = dict(ticket)

    if ticket['status'] == 'used':
        conn.close()
        return jsonify({
            'valid': False,
            'status': 'already_used',
            'message': 'Bu bilet daha önce kullanıldı!',
            'ticket': ticket_dict
        }), 200

    if ticket['status'] == 'refund_pending':
        conn.close()
        return jsonify({
            'valid': False,
            'status': 'refund_pending',
            'message': 'Bu bilet iade sürecinde, geçersiz!',
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
        'message': '✓ Geçerli Bilet' + (' - Kullanıldı olarak işaretlendi.' if action == 'use' else ''),
        'ticket': ticket_dict
    }), 200


@tickets_bp.route('/validate_promo', methods=['POST'])
@token_required
def validate_promo():
    data = request.get_json()
    event_id = data.get('event_id')
    code = data.get('code', '').strip().upper()

    if not event_id or not code:
        return jsonify({'valid': False, 'message': 'Eksik bilgi.'}), 400

    conn = get_db_connection()
    promo = conn.execute('''
        SELECT * FROM promotions 
        WHERE event_id = ? AND code = ?
    ''', (event_id, code)).fetchone()

    conn.close()

    if not promo:
        return jsonify({'valid': False, 'message': 'Geçersiz indirim kodu.'}), 404

    if promo['usage_limit'] and promo['used_count'] >= promo['usage_limit']:
        return jsonify({'valid': False, 'message': 'Bu indirim kodunun kullanım limiti dolmuş.'}), 400

    return jsonify({
        'valid': True,
        'discount_type': promo['discount_type'],
        'discount_value': promo['discount_value'],
        'message': 'İndirim kodu başarıyla uygulandı!'
    }), 200
