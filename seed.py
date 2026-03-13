import json
from werkzeug.security import generate_password_hash
from database import get_db_connection, init_db

eventsData = []

mockUsers = [
    {
        "fullname": "Admin User",
        "email": "admin@eventix.com",
        "password": "admin123",
        "role": "admin"
    },
    {
        "fullname": "Organizer Demo",
        "email": "organizer@eventix.com",
        "password": "organizer123",
        "role": "organizer"
    },
    {
        "fullname": "Ahmet Yılmaz",
        "email": "ahmet@example.com",
        "password": "password123",
        "role": "customer"
    },
    {
        "fullname": "Zeynep Kaya",
        "email": "zeynep@example.com",
        "password": "password123",
        "role": "customer"
    }
]

def seed_db():
    init_db()
    conn = get_db_connection()
    c = conn.cursor()

    # Clear existing data
    c.execute('DELETE FROM notifications')
    c.execute('DELETE FROM wishlist')
    c.execute('DELETE FROM tickets')
    c.execute('DELETE FROM events')
    c.execute('DELETE FROM users')
    c.execute("DELETE FROM sqlite_sequence WHERE name IN ('users','tickets','wishlist','notifications')")

    # Seed users
    for u in mockUsers:
        c.execute(
            'INSERT INTO users (fullname, email, password, role) VALUES (?, ?, ?, ?)',
            (u['fullname'], u['email'], generate_password_hash(u['password']), u['role'])
        )

    # Seed events (organizer_id=2 = Organizer Demo)
    for evt in eventsData:
        c.execute('''
            INSERT INTO events (id, title, category, date, location, price, image, featured,
                                description, lineup_json, capacity, sold_count, status, organizer_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        ''', (
            evt['id'], evt['title'], evt['category'], evt['date'], evt['location'],
            evt['price'], evt['image'], 1 if evt['featured'] else 0,
            evt['description'], json.dumps(evt.get('lineup', [])),
            evt['capacity'], evt['sold_count'], evt.get('organizer_id', 2)
        ))

    conn.commit()
    conn.close()
    print("Database seeded successfully!")
    print("  Admin:     admin@eventix.com / admin123")
    print("  Organizer: organizer@eventix.com / organizer123")
    print("  Customer:  ahmet@example.com / password123")
    print("  Customer:  zeynep@example.com / password123")

if __name__ == '__main__':
    seed_db()
