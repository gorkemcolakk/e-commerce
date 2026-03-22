import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

TURSO_DB_URL = os.getenv('TURSO_DB_URL')
if TURSO_DB_URL and TURSO_DB_URL.startswith('libsql://'):
    TURSO_DB_URL = TURSO_DB_URL.replace('libsql://', 'https://')
TURSO_AUTH_TOKEN = os.getenv('TURSO_AUTH_TOKEN')

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

USING_TURSO = False
try:
    if TURSO_DB_URL and TURSO_AUTH_TOKEN:
        import libsql_client
        _client = libsql_client.create_client_sync(url=TURSO_DB_URL, auth_token=TURSO_AUTH_TOKEN)
        USING_TURSO = True
except Exception as e:
    print("Turso init_db error:", e)

class TursoRowFakeDict:
    def __init__(self, libsql_row, columns):
        self._row = libsql_row
        self._columns = columns
        
    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                idx = self._columns.index(key)
                return self._row[idx]
            except ValueError:
                raise KeyError(key)
        return self._row[key]
        
    def keys(self):
        return self._columns

class TursoCursor:
    def __init__(self):
        self._result = None
        self.lastrowid = None
        
    def execute(self, sql, parameters=()):
        args = list(parameters) if parameters else []
        try:
            self._result = _client.execute(sql, args)
            if hasattr(self._result, 'rows_affected') and self._result.rows_affected > 0:
                self.lastrowid = self._result.last_insert_rowid
        except Exception as e:
            # Emulate SQLite by passing the error to try-catch blocks expecting sqlite3
            raise sqlite3.OperationalError(str(e))
        return self
        
    def fetchone(self):
        if self._result and len(self._result.rows) > 0:
            return TursoRowFakeDict(self._result.rows[0], self._result.columns)
        return None
        
    def fetchall(self):
        if self._result and self._result.rows:
            return [TursoRowFakeDict(r, self._result.columns) for r in self._result.rows]
        return []
        
    def close(self):
        pass

class TursoConnection:
    def __init__(self):
        self.row_factory = sqlite3.Row  # Fake property to pass validation
        
    def cursor(self):
        return TursoCursor()
        
    def execute(self, sql, parameters=()):
        cur = self.cursor()
        cur.execute(sql, parameters)
        return cur
        
    def commit(self):
        pass
        
    def close(self):
        pass

def get_db_connection():
    if USING_TURSO:
        return TursoConnection()
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Users table — role: customer / organizer / admin
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Events table — with capacity, status, organizer_id
    c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            location TEXT NOT NULL,
            price INTEGER NOT NULL,
            image TEXT NOT NULL,
            featured INTEGER NOT NULL DEFAULT 0,
            description TEXT,
            lineup_json TEXT,
            capacity INTEGER NOT NULL DEFAULT 100,
            sold_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            organizer_id INTEGER,
            has_seating INTEGER NOT NULL DEFAULT 0,
            seating_image TEXT,
            rejection_reason TEXT,
            parent_event_id TEXT,
            recurring_config TEXT,
            FOREIGN KEY (organizer_id) REFERENCES users (id)
        )
    ''')

    # Seats table
    c.execute('''
        CREATE TABLE IF NOT EXISTS seats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            zone TEXT NOT NULL,
            row_label TEXT NOT NULL,
            col_label TEXT NOT NULL,
            price INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'available',
            FOREIGN KEY (event_id) REFERENCES events (id)
        )
    ''')

    # Tickets table — with QR code and status
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            ticket_key TEXT NOT NULL UNIQUE,
            qr_code TEXT NOT NULL UNIQUE,
            quantity INTEGER NOT NULL DEFAULT 1,
            total_price INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'valid',
            purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (event_id) REFERENCES events (id)
        )
    ''')
    
    # Try adding seat_id to tickets if it doesn't exist
    try:
        c.execute('ALTER TABLE tickets ADD COLUMN seat_id INTEGER')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        c.execute('ALTER TABLE events ADD COLUMN has_seating INTEGER NOT NULL DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute('ALTER TABLE events ADD COLUMN seating_image TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        c.execute('ALTER TABLE events ADD COLUMN rejection_reason TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute('ALTER TABLE events ADD COLUMN cancelled_by TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        c.execute('ALTER TABLE events ADD COLUMN parent_event_id TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        c.execute('ALTER TABLE events ADD COLUMN recurring_config TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE tickets ADD COLUMN owner_name TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        c.execute("ALTER TABLE tickets ADD COLUMN owner_surname TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE users ADD COLUMN birthdate TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE users ADD COLUMN bday_promo_used_year INTEGER")
    except sqlite3.OperationalError:
        pass

    # Wishlist table
    c.execute('''
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE(user_id, event_id)
        )
    ''')

    # Notifications table
    c.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Promotions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS promotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            code TEXT NOT NULL,
            discount_type TEXT NOT NULL, -- 'percentage' or 'fixed'
            discount_value INTEGER NOT NULL,
            valid_from TIMESTAMP,
            valid_until TIMESTAMP,
            usage_limit INTEGER,
            used_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE(event_id, code)
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database and tables created successfully.")
