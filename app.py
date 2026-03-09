from flask import Flask, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import jwt
import datetime
import uuid
import json
import qrcode
import io
import base64
from functools import wraps
from database import get_db_connection

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

SECRET_KEY = 'eventix-super-secret-key-2026'
COMMISSION_RATE = 0.10  # 10% platform commission

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_qr_base64(data: str) -> str:
    """Generate a QR code image and return it as a base64 PNG data URL."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{b64}"

def event_to_dict(e):
    evt = dict(e)
    evt['featured'] = bool(evt['featured'])
    evt['lineup'] = json.loads(evt['lineup_json']) if evt.get('lineup_json') else []
    evt.pop('lineup_json', None)
    return evt

def create_notification(conn, user_id: int, message: str):
    conn.execute(
        'INSERT INTO notifications (user_id, message) VALUES (?, ?)',
        (user_id, message)
    )

# ─────────────────────────────────────────────
# AUTH DECORATORS
# ─────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        if not token:
            return jsonify({'message': 'Token eksik!'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE id = ?', (data['id'],)).fetchone()
            conn.close()
            if not user:
                return jsonify({'message': 'Geçersiz token!'}), 401
            g.user = dict(user)
        except Exception:
            return jsonify({'message': 'Token geçersiz veya süresi dolmuş!'}), 401
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            if g.user.get('role') not in roles:
                return jsonify({'message': 'Yetersiz yetki!'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ─────────────────────────────────────────────
# STATIC SERVE
# ─────────────────────────────────────────────

@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def serve_static(path):
    try:
        return app.send_static_file(path)
    except Exception:
        return app.send_static_file('index.html')

# ─────────────────────────────────────────────
# AUTH ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password') or not data.get('fullname'):
        return jsonify({'message': 'Eksik veri'}), 400

    role = data.get('role', 'customer')
    if role not in ('customer', 'organizer'):
        role = 'customer'

    conn = get_db_connection()
    c = conn.cursor()
    existing = c.execute('SELECT id FROM users WHERE email = ?', (data['email'],)).fetchone()
    if existing:
        conn.close()
        return jsonify({'message': 'Bu e-posta zaten kayıtlı'}), 409

    hashed_pw = generate_password_hash(data['password'])
    c.execute(
        'INSERT INTO users (fullname, email, password, role) VALUES (?, ?, ?, ?)',
        (data['fullname'], data['email'], hashed_pw, role)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Kayıt başarılı'}), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Eksik veri'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (data['email'],)).fetchone()
    conn.close()

    if not user or not check_password_hash(user['password'], data['password']):
        return jsonify({'message': 'Hatalı e-posta veya şifre'}), 401

    token = jwt.encode({
        'id': user['id'],
        'email': user['email'],
        'fullname': user['fullname'],
        'role': user['role'],
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
    }, SECRET_KEY, algorithm="HS256")

    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'fullname': user['fullname'],
            'role': user['role']
        }
    }), 200

# ─────────────────────────────────────────────
# USER / PROFILE ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/api/users/me', methods=['GET'])
@token_required
def get_profile():
    return jsonify({
        'id': g.user['id'],
        'fullname': g.user['fullname'],
        'email': g.user['email'],
        'role': g.user['role']
    }), 200


@app.route('/api/users/me', methods=['PATCH'])
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


@app.route('/api/admin/users', methods=['GET'])
@role_required('admin')
def admin_list_users():
    conn = get_db_connection()
    users = conn.execute(
        'SELECT id, fullname, email, role, created_at FROM users ORDER BY id'
    ).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users]), 200

# ─────────────────────────────────────────────
# EVENTS ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/api/events', methods=['GET'])
def get_events():
    category = request.args.get('category', '').strip()
    search = request.args.get('search', '').strip()

    conn = get_db_connection()
    query = "SELECT * FROM events WHERE status = 'active'"
    params = []

    if category and category != 'all':
        query += " AND category = ?"
        params.append(category)

    if search:
        query += " AND (title LIKE ? OR location LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])

    events = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([event_to_dict(e) for e in events]), 200


@app.route('/api/events/<event_id>', methods=['GET'])
def get_event(event_id):
    conn = get_db_connection()
    e = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    conn.close()
    if not e:
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404
    return jsonify(event_to_dict(e)), 200


@app.route('/api/events', methods=['POST'])
@role_required('organizer', 'admin')
def create_event():
    data = request.get_json()
    required = ['title', 'category', 'date', 'location', 'price', 'capacity']
    for field in required:
        if not data.get(field) and data.get(field) != 0:
            return jsonify({'message': f'{field} alanı zorunludur'}), 400

    event_id = 'evt-' + str(uuid.uuid4())[:8]
    lineup_json = json.dumps(data.get('lineup', []))

    # Default images by category
    default_images = {
        'concert': 'https://images.unsplash.com/photo-1540039155733-5bb30b4a574b?w=800&auto=format&fit=crop',
        'theater': 'https://images.unsplash.com/photo-1503095396549-807759245b35?w=800&auto=format&fit=crop',
        'workshop': 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&auto=format&fit=crop',
    }
    image_url = data.get('image', '').strip()
    if not image_url:
        image_url = default_images.get(data['category'], default_images['concert'])

    # Organizers create pending events; admins can create active directly
    event_status = 'active' if g.user['role'] == 'admin' else 'pending'

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO events (id, title, category, date, location, price, image, featured,
                            description, lineup_json, capacity, sold_count, status, organizer_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
    ''', (
        event_id,
        data['title'],
        data['category'],
        data['date'],
        data['location'],
        int(data['price']),
        image_url,
        1 if data.get('featured') else 0,
        data.get('description', ''),
        lineup_json,
        int(data['capacity']),
        event_status,
        g.user['id']
    ))

    # Notify organizer
    if event_status == 'pending':
        create_notification(conn, g.user['id'],
            f"'{data['title']}' etkinliğiniz admin onayına gönderildi. Onaylandıktan sonra sitede görünecek.")

    conn.commit()
    conn.close()

    msg = 'Etkinlik oluşturuldu ve admin onayına gönderildi.' if event_status == 'pending' else 'Etkinlik yayınlandı.'
    return jsonify({'message': msg, 'event_id': event_id, 'status': event_status}), 201


@app.route('/api/events/<event_id>', methods=['PATCH'])
@role_required('organizer', 'admin')
def update_event(event_id):
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404

    if g.user['role'] == 'organizer' and event['organizer_id'] != g.user['id']:
        conn.close()
        return jsonify({'message': 'Bu etkinliği düzenleme yetkiniz yok'}), 403

    data = request.get_json()
    fields = []
    values = []
    for col in ['title', 'category', 'date', 'location', 'price', 'capacity', 'description', 'image', 'featured']:
        if col in data:
            fields.append(f"{col} = ?")
            values.append(data[col])

    if not fields:
        conn.close()
        return jsonify({'message': 'Güncellenecek alan yok'}), 400

    values.append(event_id)
    conn.execute(f"UPDATE events SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return jsonify({'message': 'Etkinlik güncellendi'}), 200


@app.route('/api/events/<event_id>', methods=['DELETE'])
@role_required('organizer', 'admin')
def cancel_event(event_id):
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404

    if g.user['role'] == 'organizer' and event['organizer_id'] != g.user['id']:
        conn.close()
        return jsonify({'message': 'Bu etkinliği iptal etme yetkiniz yok'}), 403

    # Set event status to cancelled
    conn.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))

    # Mark all valid tickets as Refund Pending and notify users
    tickets = conn.execute(
        "SELECT * FROM tickets WHERE event_id = ? AND status = 'valid'", (event_id,)
    ).fetchall()
    for ticket in tickets:
        conn.execute(
            "UPDATE tickets SET status = 'refund_pending' WHERE id = ?", (ticket['id'],)
        )
        create_notification(
            conn, ticket['user_id'],
            f"'{event['title']}' etkinliği iptal edildi. Biletiniz (#{ticket['ticket_key']}) iade sürecine alındı."
        )

    conn.commit()
    conn.close()
    return jsonify({'message': 'Etkinlik iptal edildi, biletler iade sürecine alındı'}), 200

# ─────────────────────────────────────────────
# TICKETS ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/api/tickets/buy', methods=['POST'])
@token_required
def buy_ticket():
    data = request.get_json()
    event_id = data.get('event_id')
    quantity = int(data.get('quantity', 1))

    if not event_id:
        return jsonify({'message': 'event_id zorunludur'}), 400
    if quantity < 1 or quantity > 10:
        return jsonify({'message': 'Adet 1 ile 10 arasında olmalı'}), 400

    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404
    if event['status'] == 'cancelled':
        conn.close()
        return jsonify({'message': 'Bu etkinlik iptal edildi'}), 400

    # Capacity control (FR-17)
    remaining = event['capacity'] - event['sold_count']
    if remaining <= 0:
        conn.close()
        return jsonify({'message': 'Kapasite dolu! Bu etkinlik için bilet kalmadı.'}), 400
    if quantity > remaining:
        conn.close()
        return jsonify({'message': f'Yalnızca {remaining} bilet kaldı'}), 400

    # 10% discount if applicable (BR-02) — mock: always apply for demo
    unit_price = event['price']
    total_price = unit_price * quantity

    ticket_key = str(uuid.uuid4()).upper()[:12]
    qr_data = f"EVENTIX-{ticket_key}-{event_id}"
    qr_base64 = make_qr_base64(qr_data)

    c = conn.cursor()
    c.execute('''
        INSERT INTO tickets (user_id, event_id, ticket_key, qr_code, quantity, total_price, status)
        VALUES (?, ?, ?, ?, ?, ?, 'valid')
    ''', (g.user['id'], event_id, ticket_key, qr_data, quantity, total_price))

    # Update sold count
    conn.execute(
        'UPDATE events SET sold_count = sold_count + ? WHERE id = ?',
        (quantity, event_id)
    )

    # Notification (FR-12)
    create_notification(
        conn, g.user['id'],
        f"'{event['title']}' etkinliği için {quantity} bilet satın aldınız. Bilet kodunuz: #{ticket_key}"
    )

    conn.commit()
    conn.close()

    return jsonify({
        'message': 'Bilet satın alındı!',
        'ticket_key': ticket_key,
        'qr_code': qr_base64,
        'qr_data': qr_data,
        'total_price': total_price,
        'quantity': quantity
    }), 201


@app.route('/api/tickets/my-tickets', methods=['GET'])
@token_required
def my_tickets():
    conn = get_db_connection()
    tickets = conn.execute('''
        SELECT t.id, t.ticket_key, t.qr_code, t.quantity, t.total_price,
               t.status, t.purchase_date,
               e.title, e.date, e.location, e.image, e.id as event_id
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        WHERE t.user_id = ?
        ORDER BY t.purchase_date DESC
    ''', (g.user['id'],)).fetchall()
    conn.close()
    return jsonify([dict(t) for t in tickets]), 200


@app.route('/api/tickets/validate/<qr_code>', methods=['GET', 'POST'])
@token_required
def validate_ticket(qr_code):
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

    # Mark as used on POST (actual scan)
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

# ─────────────────────────────────────────────
# WISHLIST ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/api/wishlist', methods=['GET'])
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


@app.route('/api/wishlist/<event_id>', methods=['POST'])
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


@app.route('/api/wishlist/<event_id>', methods=['DELETE'])
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

# ─────────────────────────────────────────────
# NOTIFICATIONS ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/api/notifications', methods=['GET'])
@token_required
def get_notifications():
    conn = get_db_connection()
    notifications = conn.execute(
        'SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 20',
        (g.user['id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(n) for n in notifications]), 200


@app.route('/api/notifications/<int:notif_id>/read', methods=['PATCH'])
@token_required
def mark_notification_read(notif_id):
    conn = get_db_connection()
    conn.execute(
        'UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
        (notif_id, g.user['id'])
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Bildirim okundu'}), 200


@app.route('/api/notifications/read-all', methods=['PATCH'])
@token_required
def mark_all_notifications_read():
    conn = get_db_connection()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (g.user['id'],))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Tüm bildirimler okundu'}), 200

# ─────────────────────────────────────────────
# ORGANIZER ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/api/organizer/events', methods=['GET'])
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


@app.route('/api/organizer/revenue', methods=['GET'])
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

    # Per-event breakdown
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

# ─────────────────────────────────────────────
# ADMIN ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/api/admin/all-events', methods=['GET'])
@role_required('admin')
def admin_all_events():
    conn = get_db_connection()
    events = conn.execute('SELECT * FROM events ORDER BY id').fetchall()
    conn.close()
    return jsonify([event_to_dict(e) for e in events]), 200


@app.route('/api/admin/pending-events', methods=['GET'])
@role_required('admin')
def admin_pending_events():
    conn = get_db_connection()
    events = conn.execute('''
        SELECT e.*, u.fullname as organizer_name, u.email as organizer_email
        FROM events e
        LEFT JOIN users u ON e.organizer_id = u.id
        WHERE e.status = 'pending'
        ORDER BY e.id DESC
    ''').fetchall()
    conn.close()
    result = []
    for e in events:
        d = event_to_dict(e)
        d['organizer_name'] = e['organizer_name']
        d['organizer_email'] = e['organizer_email']
        result.append(d)
    return jsonify(result), 200


@app.route('/api/admin/events/<event_id>/approve', methods=['POST'])
@role_required('admin')
def approve_event(event_id):
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadi'}), 404
    conn.execute("UPDATE events SET status = 'active' WHERE id = ?", (event_id,))
    if event['organizer_id']:
        create_notification(conn, event['organizer_id'],
            f"'{event['title']}' etkinliginiz onaylandi ve sitede yayinlandi!")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Etkinlik onaylandi ve yayinlandi'}), 200


@app.route('/api/admin/events/<event_id>/reject', methods=['POST'])
@role_required('admin')
def reject_event(event_id):
    data = request.get_json() or {}
    reason = data.get('reason', 'Belirtilmedi')
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadi'}), 404
    conn.execute("UPDATE events SET status = 'rejected' WHERE id = ?", (event_id,))
    if event['organizer_id']:
        create_notification(conn, event['organizer_id'],
            f"'{event['title']}' etkinliginiz reddedildi. Sebep: {reason}")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Etkinlik reddedildi'}), 200


if __name__ == '__main__':
    from database import init_db
    init_db()
    app.run(debug=True, port=5000)

