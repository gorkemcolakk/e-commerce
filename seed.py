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
    }
]

def seed_db():
    init_db()
    conn = get_db_connection()
    c = conn.cursor()

    # Sadece eski örnek hesapları temizle, tüm veritabanını değil
    examples_to_delete = ["ahmet@example.com", "zeynep@example.com", "john@example.com", "jane@example.com"]
    for email in examples_to_delete:
        c.execute('DELETE FROM users WHERE email = ?', (email,))

    # Seed users (Eğer yoksa ekle)
    for u in mockUsers:
        c.execute('SELECT id FROM users WHERE email = ?', (u['email'],))
        if not c.fetchone():
            c.execute(
                'INSERT INTO users (fullname, email, password, role) VALUES (?, ?, ?, ?)',
                (u['fullname'], u['email'], generate_password_hash(u['password']), u['role'])
            )

    conn.commit()
    conn.close()
    print("Database synced successfully!")
    print("  Admin:     admin@eventix.com / admin123")
    print("  Organizer: organizer@eventix.com / organizer123")
    print("  (Old example customers removed, your own accounts kept.)")

if __name__ == '__main__':
    seed_db()
