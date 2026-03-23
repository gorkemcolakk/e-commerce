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
    events = conn.execute('''
        SELECT e.*, 
        (SELECT COUNT(*) FROM events WHERE parent_event_id = e.id) + 1 as s_count
        FROM events e
        WHERE e.parent_event_id IS NULL 
        ORDER BY e.id
    ''').fetchall()
    conn.close()
    
    result = []
    for e in events:
        d = event_to_dict(e)
        d['session_count'] = e['s_count']
        
        # Fetch only ACTIVE session info
        conn_sessions = get_db_connection()
        s_data = conn_sessions.execute("SELECT id, date FROM events WHERE (parent_event_id = ? OR id = ?) AND status = 'active' ORDER BY date", (e['id'], e['id'])).fetchall()
        d['sessions'] = [{'id': sd['id'], 'date': sd['date']} for sd in s_data]
        conn_sessions.close()
        
        result.append(d)
    return jsonify(result), 200

@admin_bp.route('/pending-events', methods=['GET'])
@role_required('admin')
def admin_pending_events():
    conn = get_db_connection()
    # Ana etkinlik bekliyor olabilir VEYA içindeki seanslardan en az biri bekliyor olabilir
    events = conn.execute('''
        SELECT e.*, u.fullname as organizer_name, u.email as organizer_email,
        (SELECT COUNT(*) FROM events WHERE parent_event_id = e.id) + 1 as s_count
        FROM events e
        LEFT JOIN users u ON e.organizer_id = u.id
        WHERE e.parent_event_id IS NULL 
        AND (
            e.status IN ('pending', 'rejected') 
            OR EXISTS (
                SELECT 1 FROM events s 
                WHERE s.parent_event_id = e.id 
                AND s.status IN ('pending', 'rejected')
            )
        )
        ORDER BY e.id DESC
    ''').fetchall()
    conn.close()
    
    result = []
    for e in events:
        d = event_to_dict(e)
        d['organizer_name'] = e['organizer_name']
        d['organizer_email'] = e['organizer_email']
        d['session_count'] = e['s_count']
        
        # Sadece onay bekleyen veya reddedilmiş seansları getir
        conn_sessions = get_db_connection()
        s_data = conn_sessions.execute('''
            SELECT id, date, price, capacity FROM events 
            WHERE (parent_event_id = ? OR id = ?) 
            AND status IN ('pending', 'rejected')
            ORDER BY date
        ''', (e['id'], e['id'])).fetchall()
        
        d['sessions'] = [{'id': sd['id'], 'date': sd['date'], 'price': sd['price'], 'capacity': sd['capacity']} for sd in s_data]
        
        # Eğer bekleyen seans varsa, kart bilgilerini o seanstaki en güncel verilerle (örn: 5000 TL) doldur
        if s_data:
            d['price'] = s_data[0]['price']
            d['capacity'] = s_data[0]['capacity']
            d['date'] = s_data[0]['date']
            
        conn_sessions.close()
        
        result.append(d)
    return jsonify(result), 200

@admin_bp.route('/events/<event_id>/approve', methods=['POST'])
@role_required('admin')
def approve_event(event_id):
    data = request.get_json() or {}
    selected_ids = data.get('selected_ids', []) # List of session IDs to approve

    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Event not found'}), 404
    
    if not selected_ids:
        # Default behavior: approve as single or approve all sessions if parent
        conn.execute("UPDATE events SET status = 'active' WHERE id = ? OR parent_event_id = ?", (event_id, event_id))
    else:
        # Granular approval: only approve the selected IDs
        # We use placeholders for the IN clause
        placeholders = ','.join(['?'] * len(selected_ids))
        conn.execute(f"UPDATE events SET status = 'active' WHERE id IN ({placeholders})", selected_ids)

    if event['organizer_id']:
        create_notification(conn, event['organizer_id'],
            f"Your event '{event['title']}' has been partially or fully approved!")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Approval processed successfully'}), 200

@admin_bp.route('/events/<event_id>/reject', methods=['POST'])
@role_required('admin')
def reject_event(event_id):
    data = request.get_json() or {}
    reason = data.get('reason', 'Not specified')
    selected_ids = data.get('selected_ids', [])

    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Event not found'}), 404

    if selected_ids:
        # Rejection for ONLY selected sessions
        placeholders = ','.join(['?'] * len(selected_ids))
        params = [reason] + list(selected_ids)
        conn.execute(f"UPDATE events SET status = 'rejected', rejection_reason = ? WHERE id IN ({placeholders})", params)
    else:
        # Fallback to whole series if nothing selected
        conn.execute("UPDATE events SET status = 'rejected', rejection_reason = ? WHERE id = ? OR parent_event_id = ?", (reason, event_id, event_id))

    if event['organizer_id']:
        create_notification(conn, event['organizer_id'], f"An edit has been requested for your session(s) in '{event['title']}'. Reason: {reason}")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Selected sessions rejected'}), 200
