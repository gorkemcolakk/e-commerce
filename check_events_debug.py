from database import get_db_connection
import json

def check_events():
    conn = get_db_connection()
    c = conn.cursor()
    # Güldür Güldür ile başlayan tüm etkinlikleri çekelim
    events = c.execute("SELECT id, title, date, parent_event_id, status FROM events WHERE title LIKE '%Güldür%' ORDER BY date").fetchall()
    conn.close()
    
    print(f"Buldum! Toplam {len(events)} tane 'Güldür Güldür' oturumu var:")
    for e in events:
        print(f"- {e['date']} | ID: {e['id']} | Parent: {e['parent_event_id']} | Status: {e['status']}")

if __name__ == '__main__':
    check_events()
