from database import get_db_connection
import json

def check_recurring():
    conn = get_db_connection()
    c = conn.cursor()
    event = c.execute("SELECT recurring_config FROM events WHERE id='evt-C4B7D4F5'").fetchone()
    conn.close()
    
    if event:
        print(f"Recurring Config: {event['recurring_config']}")
    else:
        print("Event not found.")

if __name__ == '__main__':
    check_recurring()
