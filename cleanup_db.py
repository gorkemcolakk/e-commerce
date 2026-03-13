
import sqlite3
import os

DB_PATH = os.path.join(os.getcwd(), 'database.db')
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Delete events belonging to OrgID 2 (Organizer Demo) and their related data
# These are the sample events like Neon Nights, etc.
# Also delete events with specific sample IDs
sample_ids = ['evt-001', 'evt-002', 'evt-003', 'evt-004', 'evt-005', 'evt-006']

# Find all events that should be deleted
to_delete = c.execute("SELECT id FROM events WHERE organizer_id = 2 OR id IN ({})".format(
    ','.join(['?']*len(sample_ids))
), sample_ids).fetchall()

ids = [row[0] for row in to_delete]

if ids:
    print(f"Deleting {len(ids)} sample events...")
    # Delete related data first (though PRAGMA foreign_keys = ON should handle some, let's be safe)
    c.execute("DELETE FROM seats WHERE event_id IN ({})".format(','.join(['?']*len(ids))), ids)
    c.execute("DELETE FROM wishlist WHERE event_id IN ({})".format(','.join(['?']*len(ids))), ids)
    c.execute("DELETE FROM promotions WHERE event_id IN ({})".format(','.join(['?']*len(ids))), ids)
    c.execute("DELETE FROM tickets WHERE event_id IN ({})".format(','.join(['?']*len(ids))), ids)
    c.execute("DELETE FROM events WHERE id IN ({})".format(','.join(['?']*len(ids))), ids)
    print("Cleanup complete.")
else:
    print("No sample events found.")

conn.commit()
conn.close()
