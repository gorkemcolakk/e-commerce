import sqlite3
import os

DB_PATH = 'database.db'
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    tickets = conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 2").fetchall()
    for t in tickets:
        print(dict(t))
    conn.close()
else:
    print("DB not found")
