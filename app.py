from flask import Flask
from flask_cors import CORS
from utils import SECRET_KEY, limiter

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

if __name__ == '__main__':
    from database import init_db
    init_db()
    app.run(debug=True, port=5000)
