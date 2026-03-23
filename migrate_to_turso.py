import os
import sqlite3
import certifi
import asyncio
from dotenv import load_dotenv
import libsql_client

load_dotenv()
os.environ['SSL_CERT_FILE'] = certifi.where()

TURSO_DB_URL = os.getenv('TURSO_DB_URL')
TURSO_AUTH_TOKEN = os.getenv('TURSO_AUTH_TOKEN')
DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
ALT_DB_PATH = os.path.join(os.path.dirname(__file__), 'eventix.db')

if TURSO_DB_URL and TURSO_DB_URL.startswith('libsql://'):
    TURSO_DB_URL = TURSO_DB_URL.replace('libsql://', 'https://')

async def migrate(db_file):
    print(f"Connecting to local DB: {db_file}")
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    try:
        events = c.execute("SELECT * FROM events").fetchall()
    except Exception as e:
        print("Error reading events from local DB:", e)
        return

    if not events:
        print(f"No events found in {db_file}.")
        return

    print(f"Found {len(events)} events locally. Pushing to Turso...")
    
    try:
        async with libsql_client.create_client(TURSO_DB_URL, auth_token=TURSO_AUTH_TOKEN) as client:
            for ev in events:
                # Assuming table structure: id, title, category, date, location, price, image, featured, description, lineup_json, capacity, sold_count, status, organizer_id, has_seating, seating_image, rejection_reason, parent_event_id, recurring_config
                # We will just insert exactly into events. Let's dynamically get columns.
                columns = ev.keys()
                placeholders = ", ".join(["?" for _ in columns])
                col_names = ", ".join(columns)
                values = [ev[col] for col in columns]
                
                # Check if event already exists
                check = await client.execute("SELECT id FROM events WHERE id = ?", [ev['id']])
                if len(check.rows) > 0:
                    print(f"Event {ev['title']} already exists on Turso. Skipping.")
                else:
                    await client.execute(f"INSERT INTO events ({col_names}) VALUES ({placeholders})", values)
                    print(f"Migrated event: {ev['title']}")
                    
            print("Migration completely successful!")
    except Exception as e:
        print("Turso error during migration: ", e)

if __name__ == '__main__':
    if os.path.exists(DB_PATH):
        asyncio.run(migrate(DB_PATH))
    elif os.path.exists(ALT_DB_PATH):
        asyncio.run(migrate(ALT_DB_PATH))
    else:
        print("Local database file not found. Could not migrate.")
