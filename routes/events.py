import uuid
import json
from flask import Blueprint, request, jsonify, g
from database import get_db_connection
from utils import token_required, role_required, event_to_dict, create_notification

events_bp = Blueprint('events', __name__, url_prefix='/api/events')

@events_bp.route('', methods=['GET'])
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

    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 12, type=int)
    offset = (page - 1) * limit

    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    events = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([event_to_dict(e) for e in events]), 200

@events_bp.route('/<event_id>', methods=['GET'])
def get_event(event_id):
    conn = get_db_connection()
    e = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    conn.close()
    if not e:
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404
    
    event_dict = event_to_dict(e)
    if event_dict.get('has_seating'):
        # Just include a flag so the frontend knows it needs to fetch seats
        pass
        
    return jsonify(event_dict), 200

@events_bp.route('/<event_id>/seats', methods=['GET'])
def get_event_seats(event_id):
    conn = get_db_connection()
    seats = conn.execute('SELECT * FROM seats WHERE event_id = ?', (event_id,)).fetchall()
    conn.close()
    return jsonify([dict(s) for s in seats]), 200

@events_bp.route('', methods=['POST'])
@role_required('organizer', 'admin')
def create_event():
    data = request.get_json()
    required = ['title', 'category', 'date', 'location', 'price', 'capacity']
    for field in required:
        if not data.get(field) and data.get(field) != 0:
            return jsonify({'message': f'{field} alanı zorunludur'}), 400

    event_id = 'evt-' + uuid.uuid4().hex.upper()[:8]
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

    event_status = 'active' if g.user['role'] == 'admin' else 'pending'
    
    has_seating = 1 if data.get('has_seating') else 0
    zones = data.get('zones', [])

    conn = get_db_connection()
    
    # Calculate starting price if seated
    base_price = int(data.get('price', 0))
    total_capacity = int(data.get('capacity', 0))
    if has_seating and zones:
        base_price = min([int(z.get('price', 0)) for z in zones if 'price' in z], default=base_price)
        total_capacity = sum([int(z.get('rows', 1)) * int(z.get('cols', 1)) for z in zones])

    conn.execute('''
        INSERT INTO events (id, title, category, date, location, price, image, featured,
                            description, lineup_json, capacity, sold_count, status, organizer_id, has_seating, seating_image)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
    ''', (
        event_id, data['title'], data['category'], data['date'], data['location'],
        base_price, image_url, 1 if data.get('featured') else 0,
        data.get('description', ''), lineup_json, total_capacity,
        event_status, g.user['id'], has_seating, data.get('seating_image', '')
    ))
    
    if has_seating and zones:
        for z in zones:
            zone_name = z.get('name', 'Blok')
            rows = int(z.get('rows', 1))
            cols = int(z.get('cols', 1))
            z_price = int(z.get('price', base_price))
            
            for r in range(1, rows + 1):
                # Rows can be A, B, C or 1, 2, 3. Let's use A, B, C for < 26 rows
                if rows <= 26:
                    row_label = chr(64 + r)
                else:
                    row_label = str(r)
                
                for c in range(1, cols + 1):
                    col_label = str(c)
                    conn.execute('''
                        INSERT INTO seats (event_id, zone, row_label, col_label, price, status)
                        VALUES (?, ?, ?, ?, ?, 'available')
                    ''', (event_id, zone_name, row_label, col_label, z_price))

    if event_status == 'pending':
        create_notification(conn, g.user['id'],
            f"'{data['title']}' etkinliğiniz admin onayına gönderildi. Onaylandıktan sonra sitede görünecek.")

    conn.commit()
    conn.close()

    msg = 'Etkinlik oluşturuldu ve admin onayına gönderildi.' if event_status == 'pending' else 'Etkinlik yayınlandı.'
    return jsonify({'message': msg, 'event_id': event_id, 'status': event_status}), 201

@events_bp.route('/<event_id>', methods=['PATCH'])
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
    
    # Track if significant fields are changed
    needs_reapproval = False
    significant_fields = {'title', 'category', 'date', 'location', 'price', 'capacity', 'image', 'seating_image'}
    
    for col in ['title', 'category', 'date', 'location', 'price', 'capacity', 'description', 'image', 'featured', 'seating_image']:
        if col in data:
            fields.append(f"{col} = ?")
            values.append(data[col])
            if col in significant_fields:
                needs_reapproval = True

    if not fields:
        conn.close()
        return jsonify({'message': 'Güncellenecek alan yok'}), 400

    # If an organizer edits their event, bump it back to pending
    if g.user['role'] == 'organizer' and needs_reapproval and event['status'] == 'active':
        fields.append("status = 'pending'")
        create_notification(conn, g.user['id'], f"'{event['title']}' etkinliğinizde yaptığınız değişiklikler nedeniyle tekrar onaya gönderildi.")

    values.append(event_id)
    conn.execute(f"UPDATE events SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    
    if g.user['role'] == 'organizer' and needs_reapproval and event['status'] == 'active':
        return jsonify({'message': 'Etkinlik güncellendi ve tekrar admin onayına gönderildi', 'status': 'pending'}), 200
    return jsonify({'message': 'Etkinlik güncellendi', 'status': event['status']}), 200

@events_bp.route('/<event_id>', methods=['DELETE'])
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

    conn.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))

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
