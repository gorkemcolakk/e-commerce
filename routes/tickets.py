import uuid
from flask import Blueprint, request, jsonify, g
from database import get_db_connection
from utils import token_required, make_qr_base64, create_notification, sign_ticket_data, verify_ticket_signature, send_mock_email, limiter

tickets_bp = Blueprint('tickets', __name__, url_prefix='/api/tickets')

@tickets_bp.route('/buy', methods=['POST'])
@token_required
@limiter.limit("5 per minute")
def buy_ticket():
    import time
    data = request.get_json()
    event_id = data.get('event_id')
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
    cvc = data.get('cvc', '').strip()

    if not card_name or not card_number or not cvc:
        return jsonify({'message': 'Ödeme bilgileri eksik! Lütfen kart bilgilerinizi giriniz.'}), 400
    if len(card_number) < 15 or not card_number.isdigit():
        return jsonify({'message': 'Geçersiz kart numarası! En az 15 haneli olmalıdır.'}), 400
    if len(cvc) < 3 or not cvc.isdigit():
        return jsonify({'message': 'Geçersiz CVC numarası!'}), 400

    if card_number.startswith('0000'):
        # Simulate payment rejected
        time.sleep(1)
        return jsonify({'message': 'Ödeme reddedildi. Lütfen başka bir kart deneyin.'}), 400

    # Simulate payment processing delay
    time.sleep(1.5)

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

    generated_tickets = []
    for t_info in tickets_info:
        ticket_key = uuid.uuid4().hex.upper()[:12]
        qr_data = sign_ticket_data(f"EVENTIX-{ticket_key}-{event_id}")
        qr_base64 = make_qr_base64(qr_data)
        
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
            'name': t_info.get('name'),
            'surname': t_info.get('surname'),
            'price': t_price
        })

    create_notification(
        conn, g.user['id'],
        f"'{event['title']}' etkinliği için {quantity} adet bilet başarıyla satın alındı."
    )

    email_body = f"Merhaba {g.user['fullname']},\n\n'{event['title']}' etkinliği için biletleriniz başarıyla oluşturuldu.\n\n"
    for gt in generated_tickets:
         email_body += f"🎫 İsim: {gt['name']} {gt['surname']} | Bilet Kodunuz: #{gt['ticket_key']}\n"
    email_body += f"\n📅 Tarih: {event['date']}\n📍 Konum: {event['location']}\n🪑 Koltuk(lar): {seat_labels_str}\n💳 Toplam Tutar: {total_price} ₺\n\nQR biletlerinizi portalımızdan 'Biletlerim' kısmına giderek görüntüleyebilirsiniz.\n"

    send_mock_email(g.user['email'], f"Biletleriniz Hazır - {event['title']}", email_body)

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
