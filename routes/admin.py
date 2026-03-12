from flask import Blueprint, request, jsonify
from database import get_db_connection
from utils import role_required, event_to_dict, create_notification

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.route('/users', methods=['GET'])
@role_required('admin')
def admin_list_users():
    conn = get_db_connection()
    users = conn.execute(
        'SELECT id, fullname, email, role, created_at FROM users ORDER BY id'
    ).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users]), 200

@admin_bp.route('/all-events', methods=['GET'])
@role_required('admin')
def admin_all_events():
    conn = get_db_connection()
    events = conn.execute('SELECT * FROM events ORDER BY id').fetchall()
    conn.close()
    return jsonify([event_to_dict(e) for e in events]), 200

@admin_bp.route('/pending-events', methods=['GET'])
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

@admin_bp.route('/events/<event_id>/approve', methods=['POST'])
@role_required('admin')
def approve_event(event_id):
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404
    conn.execute("UPDATE events SET status = 'active' WHERE id = ?", (event_id,))
    if event['organizer_id']:
        create_notification(conn, event['organizer_id'],
            f"'{event['title']}' etkinliğiniz onaylandı ve sitede yayınlandı!")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Etkinlik onaylandı ve yayınlandı'}), 200

@admin_bp.route('/events/<event_id>/reject', methods=['POST'])
@role_required('admin')
def reject_event(event_id):
    data = request.get_json() or {}
    reason = data.get('reason', 'Belirtilmedi')
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Etkinlik bulunamadı'}), 404
    conn.execute("UPDATE events SET status = 'rejected', rejection_reason = ? WHERE id = ?", (reason, event_id))
    if event['organizer_id']:
        create_notification(conn, event['organizer_id'],
            f"'{event['title']}' etkinliğiniz için düzenleme talep edildi. Sebep: {reason}")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Etkinlik reddedildi'}), 200
