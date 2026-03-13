
import sqlite3
import os

DB_PATH = os.path.join(os.getcwd(), 'database.db')
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Get events for organizer 'görkem çolak' (OrgID 5)
org_id = 5
events = conn.execute("SELECT id, title, sold_count FROM events WHERE organizer_id = ?", (org_id,)).fetchall()

print("EVENT BREAKDOWN (from events table):")
total_sold_count = 0
for e in events:
    print(f"ID: {e['id']} | Title: {e['title']} | SoldCount: {e['sold_count']}")
    total_sold_count += e['sold_count']
print(f"Total from events table: {total_sold_count}")

print("\nTICKETS BREAKDOWN (from tickets table, status='valid'):")
tickets = conn.execute("""
    SELECT e.title, SUM(t.quantity) as total_qty, SUM(t.total_price) as total_revenue
    FROM tickets t
    JOIN events e ON t.event_id = e.id
    WHERE e.organizer_id = ? AND t.status = 'valid'
    GROUP BY e.id
""", (org_id,)).fetchall()

total_tickets = 0
for t in tickets:
    print(f"Title: {t['title']} | Qty: {t['total_qty']} | Revenue: {t['total_revenue']}")
    total_tickets += t['total_qty']
print(f"Total from tickets table: {total_tickets}")

conn.close()
