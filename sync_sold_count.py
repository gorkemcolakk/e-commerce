
import sqlite3
import os

DB_PATH = os.path.join(os.getcwd(), 'database.db')
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Update sold_count for all events based on the sum of ticket quantities
print("Syncing events.sold_count with actual tickets...")
c.execute('''
    UPDATE events 
    SET sold_count = (
        SELECT COALESCE(SUM(quantity), 0)
        FROM tickets 
        WHERE event_id = events.id AND status = 'valid'
    )
''')

rows_affected = c.rowcount
print(f"Sync complete. {rows_affected} events updated.")

conn.commit()
conn.close()
