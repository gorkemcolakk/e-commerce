
import sqlite3
import os

DB_PATH = os.path.join(os.getcwd(), 'database.db')
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
events = conn.execute("SELECT id, title, organizer_id FROM events").fetchall()
for e in events:
    print(f"ID: {e['id']} | Title: {e['title']} | OrgID: {e['organizer_id']}")
conn.close()
