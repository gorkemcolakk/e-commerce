import sqlite3
import uuid
import time
import os

# Mock the environment so we can test the logic
os.environ['SECRET_KEY'] = 'test-secret'

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Simplified mocks of utils functions
def sign_ticket_data(data):
    return data + "-signed"

def make_qr_base64(data):
    return "mock-qr-base64"

def create_notification(conn, user_id, message):
    conn.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (user_id, message))

def send_mock_email(email, subject, body):
    print(f"Sending email to {email}")

def test_buy_ticket(event_id, tickets_info, quantity, user_id):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        event = c.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            print("Error: Event not found")
            return
        
        total_price = 0
        seat_labels_str = "Standart"
        seats_dict = {}

        if event['has_seating']:
            print("Seated event logic branch")
            seat_ids = [t.get('seat_id') for t in tickets_info if t.get('seat_id')]
            placeholders = ','.join(['?'] * len(seat_ids))
            params = list(seat_ids)
            params.append(event_id)
            seats = c.execute(f"SELECT * FROM seats WHERE id IN ({placeholders}) AND event_id = ? AND status = 'available'", params).fetchall()
            
            for s in seats:
                total_price += s['price']
                seats_dict[str(s['id'])] = s
            seat_labels = [f"{s['zone']} {s['row_label']}-{s['col_label']}" for s in seats]
            seat_labels_str = ", ".join(seat_labels)
            c.execute(f"UPDATE seats SET status = 'sold' WHERE id IN ({placeholders})", seat_ids)
            c.execute("UPDATE events SET sold_count = sold_count + ? WHERE id = ?", (quantity, event_id))
        else:
            print("Non-seated event logic branch")
            c.execute('UPDATE events SET sold_count = sold_count + ? WHERE id = ?', (quantity, event_id))
            unit_price = event['price']
            total_price = unit_price * quantity

        generated_tickets = []
        for t_info in tickets_info:
            ticket_key = uuid.uuid4().hex.upper()[:12]
            qr_data = sign_ticket_data(f"EVENTIX-{ticket_key}-{event_id}")
            qr_base64 = make_qr_base64(qr_data)
            
            # This is where I suspect the bug is
            t_price = unit_price if not event['has_seating'] else seats_dict[str(t_info['seat_id'])]['price']
            seat_id_val = t_info.get('seat_id') if event['has_seating'] else None
            
            c.execute('''
                INSERT INTO tickets (user_id, event_id, ticket_key, qr_code, quantity, total_price, status, owner_name, owner_surname, seat_id)
                VALUES (?, ?, ?, ?, ?, ?, 'valid', ?, ?, ?)
            ''', (user_id, event_id, ticket_key, qr_data, 1, t_price, t_info.get('name'), t_info.get('surname'), seat_id_val))
            
            generated_tickets.append(ticket_key)

        create_notification(conn, user_id, "Bilet alindi")
        conn.commit()
        print(f"Success! Tickets: {generated_tickets}")
    except Exception as e:
        print(f"CAUGHT ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

# Execute test
# Check an existing event in DB first
conn = get_db_connection()
e = conn.execute("SELECT id, has_seating FROM events LIMIT 1").fetchone()
conn.close()

if e:
    print(f"Testing with event {e['id']} (Seated: {e['has_seating']})")
    tickets = [{'name': 'Test', 'surname': 'User'}]
    if e['has_seating']:
        # Need a seat ID
        conn = get_db_connection()
        s = conn.execute("SELECT id FROM seats WHERE event_id = ? AND status = 'available' LIMIT 1", (e['id'],)).fetchone()
        conn.close()
        if s:
            tickets[0]['seat_id'] = s['id']
            test_buy_ticket(e['id'], tickets, 1, 1)
        else:
            print("No available seats to test")
    else:
        test_buy_ticket(e['id'], tickets, 1, 1)
else:
    print("No events in DB to test")
