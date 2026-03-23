from dotenv import load_dotenv
load_dotenv()  # Load SMTP and other settings from .env file

import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()

from flask import Flask
from flask_cors import CORS
from utils import SECRET_KEY, limiter, send_birthday_emails
import threading
import time
from datetime import datetime
import os

from routes.auth import auth_bp
from routes.users import users_bp
from routes.events import events_bp
from routes.tickets import tickets_bp
from routes.wishlist import wishlist_bp
from routes.notifications import notifications_bp
from routes.organizer import organizer_bp
from routes.admin import admin_bp
from routes.upload import upload_bp

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)
app.config['SECRET_KEY'] = SECRET_KEY
limiter.init_app(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(users_bp)
app.register_blueprint(events_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(wishlist_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(organizer_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(upload_bp)

# ─────────────────────────────────────────────
# STATIC SERVE
# ─────────────────────────────────────────────

@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def serve_static(path):
    try:
        return app.send_static_file(path)
    except Exception:
        return app.send_static_file('index.html')

def birthday_job():
    """Runs in background and sends emails at exactly 00:00."""
    while True:
        now = datetime.now()
        if now.hour == 0 and now.minute == 0:
            send_birthday_emails()
            time.sleep(65) # Aynı dakika içinde tekrar tetiklenmesini önle
        else:
            time.sleep(30)

if __name__ == '__main__':
    # init_db()  # <-- Turso kurulu olduğu için her başlatmada kapatıyoruz.
    
    # Check to prevent duplicate threads during development reload
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        t = threading.Thread(target=birthday_job, daemon=True)
        t.start()
        print(">>> Birthday Background Service Started (Waiting for 00:00)")
    # On Windows, using use_reloader=False is more stable for custom threading
    app.run(debug=True, port=5002, use_reloader=False)
