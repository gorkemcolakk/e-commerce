import json
from werkzeug.security import generate_password_hash
from database import get_db_connection, init_db

eventsData = [
  {
    "id": "evt-001",
    "title": "Neon Nights Festival",
    "category": "concert",
    "date": "24 May 2026 • 21:00",
    "location": "Volkswagen Arena, Istanbul",
    "price": 850,
    "image": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?q=80&w=800&auto=format&fit=crop",
    "featured": True,
    "capacity": 5000,
    "sold_count": 1200,
    "description": "Yılın en büyük elektronik müzik ve ışık şölenine hazır mısınız? Neon Nights Festival, Avrupa'nın önde gelen DJ'lerini ve görsel sanatçılarını tek bir sahnede buluşturuyor. Özel tasarlanmış sahne şovları ve binlerce kişilik coşkuyla unutulmaz bir gece yaşanacak.\n\nEtkinlik alanında özel dinlenme alanları, food truck'lar ve sanat sergileri gün boyu ziyaretçilere açık olacaktır. Etkinlik 18 yaş ve üzeri içindir.",
    "lineup": [
      {"name": "DJ KRYPTON", "image": "https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?q=80&w=200&auto=format&fit=crop"},
      {"name": "SARAH V.", "image": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?q=80&w=200&auto=format&fit=crop"},
      {"name": "THE NEONS", "image": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?q=80&w=200&auto=format&fit=crop"}
    ],
    "organizer_id": 2
  },
  {
    "id": "evt-002",
    "title": "Modern Art & Digital Design",
    "category": "workshop",
    "date": "12 June 2026 • 14:00",
    "location": "Zorlu PSM Studio, Istanbul",
    "price": 450,
    "image": "https://images.unsplash.com/photo-1544531586-fde5298cdd40?q=80&w=800&auto=format&fit=crop",
    "featured": True,
    "capacity": 30,
    "sold_count": 18,
    "description": "Geleceğin tasarım diliyle tanışın. Modern Art & Digital Design atölyesinde, dijital sanatın temellerini öğrenecek ve kendi eserlerinizi oluşturma fırsatı bulacaksınız. Uzman eğitmenler eşliğinde interaktif bir deneyim sizi bekliyor.\n\nKatılımcıların kendi dizüstü bilgisayarlarını getirmeleri rica olunur.",
    "lineup": [
      {"name": "ALICE M.", "image": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?q=80&w=200&auto=format&fit=crop"},
      {"name": "JOHN D.", "image": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?q=80&w=200&auto=format&fit=crop"}
    ],
    "organizer_id": 2
  },
  {
    "id": "evt-003",
    "title": "Hamlet: Cyberpunk Edition",
    "category": "theater",
    "date": "30 May 2026 • 20:30",
    "location": "DasDas Sahne, Istanbul",
    "price": 600,
    "image": "https://images.unsplash.com/photo-1510526955054-94fe6f2f0f80?q=80&w=800&auto=format&fit=crop",
    "featured": False,
    "capacity": 200,
    "sold_count": 75,
    "description": "Klasik bir eserin fütüristik bir yorumu. Hamlet: Cyberpunk Edition, distopik bir gelecekte geçen, teknolojinin ve insan doğasının çatışmasını anlatan büyüleyici bir tiyatro deneyimi.",
    "lineup": [
      {"name": "EMİR K.", "image": "https://images.unsplash.com/photo-1599566150163-29194dcaad36?q=80&w=200&auto=format&fit=crop"},
      {"name": "LEYLA T.", "image": "https://images.unsplash.com/photo-1580489944761-15a19d654956?q=80&w=200&auto=format&fit=crop"}
    ],
    "organizer_id": 2
  },
  {
    "id": "evt-004",
    "title": "Electronic Beats Sessions",
    "category": "concert",
    "date": "05 July 2026 • 22:00",
    "location": "Klein Phönix, Ankara",
    "price": 1200,
    "image": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?q=80&w=800&auto=format&fit=crop",
    "featured": True,
    "capacity": 800,
    "sold_count": 320,
    "description": "Yeraltı elektronik müzik sahnesinin en iyileri Electronic Beats Sessions'ta buluşuyor. Sabaha kadar sürecek bu kesintisiz müzik deneyiminde, techno ve house müziğin sınırları zorlanacak.\n\nVIP bilet sahiplerine özel kulis arkası erişim ve içecek ikramı mevcuttur.",
    "lineup": [
      {"name": "MARCO V.", "image": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?q=80&w=200&auto=format&fit=crop"},
      {"name": "NINA K.", "image": "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?q=80&w=200&auto=format&fit=crop"},
      {"name": "BEN K.", "image": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?q=80&w=200&auto=format&fit=crop"}
    ],
    "organizer_id": 2
  },
  {
    "id": "evt-005",
    "title": "Pottery & Wine Night",
    "category": "workshop",
    "date": "18 May 2026 • 19:00",
    "location": "Kadıköy Atölye, Istanbul",
    "price": 350,
    "image": "https://images.unsplash.com/photo-1610701596007-11502861dcfa?q=80&w=800&auto=format&fit=crop",
    "featured": False,
    "capacity": 20,
    "sold_count": 20,
    "description": "Günün yorgunluğunu atmak için mükemmel bir fırsat. Pottery & Wine Night'ta, şarabınızı yudumlarken seramik hamuruna şekil verecek ve kendi eşsiz eserlerinizi yaratacaksınız.",
    "lineup": [
      {"name": "CEREN A.", "image": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?q=80&w=200&auto=format&fit=crop"}
    ],
    "organizer_id": 2
  },
  {
    "id": "evt-006",
    "title": "Symphony of the Stars",
    "category": "concert",
    "date": "10 August 2026 • 20:00",
    "location": "Harbiye Açıkhava, Istanbul",
    "price": 950,
    "image": "https://images.unsplash.com/photo-1511192336575-5a79af67a629?q=80&w=800&auto=format&fit=crop",
    "featured": False,
    "capacity": 3000,
    "sold_count": 900,
    "description": "Klasik müziğin büyüsü yıldızların altında... Symphony of the Stars konserinde, dünyaca ünlü senfoni orkestrası en sevilen klasik eserleri seslendirecek.",
    "lineup": [
      {"name": "MAESTRO B.", "image": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?q=80&w=200&auto=format&fit=crop"},
      {"name": "İDİL B.", "image": "https://images.unsplash.com/photo-1544725176-7c40e5a71c5e?q=80&w=200&auto=format&fit=crop"}
    ],
    "organizer_id": 2
  }
]

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
