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
        
        # Fetch actual session dates
        conn_sessions = get_db_connection()
        s_dates = conn_sessions.execute('SELECT date FROM events WHERE parent_event_id = ? OR id = ? ORDER BY date', (e['id'], e['id'])).fetchall()
        d['session_dates'] = [sd['date'] for sd in s_dates]
        conn_sessions.close()
        
        result.append(d)
    return jsonify(result), 200

@admin_bp.route('/pending-events', methods=['GET'])
@role_required('admin')
def admin_pending_events():
    conn = get_db_connection()
    events = conn.execute('''
        SELECT e.*, u.fullname as organizer_name, u.email as organizer_email,
        (SELECT COUNT(*) FROM events WHERE parent_event_id = e.id) + 1 as s_count
        FROM events e
        LEFT JOIN users u ON e.organizer_id = u.id
        WHERE e.status = 'pending' AND e.parent_event_id IS NULL
        ORDER BY e.id DESC
    ''').fetchall()
    conn.close()
    result = []
    for e in events:
        d = event_to_dict(e)
        d['organizer_name'] = e['organizer_name']
        d['organizer_email'] = e['organizer_email']
        d['session_count'] = e['s_count']
        
        # Fetch actual session dates
        conn_sessions = get_db_connection()
        s_dates = conn_sessions.execute('SELECT date FROM events WHERE parent_event_id = ? OR id = ? ORDER BY date', (e['id'], e['id'])).fetchall()
        d['session_dates'] = [sd['date'] for sd in s_dates]
        conn_sessions.close()
        
        result.append(d)
    return jsonify(result), 200

@admin_bp.route('/events/<event_id>/approve', methods=['POST'])
@role_required('admin')
def approve_event(event_id):
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Event not found'}), 404
    conn.execute("UPDATE events SET status = 'active' WHERE id = ? OR parent_event_id = ?", (event_id, event_id))
    if event['organizer_id']:
        create_notification(conn, event['organizer_id'],
            f"Your event '{event['title']}' has been approved and published on the site!")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Event approved and published'}), 200

@admin_bp.route('/events/<event_id>/reject', methods=['POST'])
@role_required('admin')
def reject_event(event_id):
    data = request.get_json() or {}
    reason = data.get('reason', 'Not specified')
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'message': 'Event not found'}), 404
    conn.execute("UPDATE events SET status = 'rejected', rejection_reason = ? WHERE id = ? OR parent_event_id = ?", (reason, event_id, event_id))
    if event['organizer_id']:
        create_notification(conn, event['organizer_id'],
            f"An edit has been requested for your event '{event['title']}'. Reason: {reason}")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Event rejected'}), 200
