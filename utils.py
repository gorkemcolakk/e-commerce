import qrcode
import io
import base64
import json
import jwt
import hmac
import hashlib
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from flask import request, jsonify, g
import uuid
from functools import wraps
from database import get_db_connection
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

SECRET_KEY = 'eventix-super-secret-key-2026'
COMMISSION_RATE = 0.10

limiter = Limiter(key_func=get_remote_address)

def sign_ticket_data(data: str) -> str:
    """Creates an HMAC-SHA256 signature for the ticket data."""
    signature = hmac.new(SECRET_KEY.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{data}-{signature[:16]}"

def verify_ticket_signature(signed_data: str) -> bool:
    """Verifies the HMAC signature of the ticket data."""
    parts = signed_data.rsplit('-', 1)
    if len(parts) != 2:
        return False
    data, signature = parts
    expected_signature = hmac.new(SECRET_KEY.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()[:16]
    return hmac.compare_digest(signature, expected_signature)

def make_qr_base64(data: str) -> str:
    """Generate a QR code image and return it as a base64 PNG data URL."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{b64}"

def make_qr_bytes(data: str) -> bytes:
    """Generate a QR code image and return raw PNG bytes (for email CID embedding)."""
    qr = qrcode.QRCode(version=1, box_size=8, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()

def event_to_dict(e):
    evt = dict(e)
    evt['featured'] = bool(evt['featured'])
    evt['lineup'] = json.loads(evt['lineup_json']) if evt.get('lineup_json') else []
    evt.pop('lineup_json', None)
    return evt

def create_notification(conn, user_id: int, message: str):
    conn.execute(
        'INSERT INTO notifications (user_id, message) VALUES (?, ?)',
        (user_id, message)
    )

def send_email(to_email: str, subject: str, message: str, html_message: str = None, images: list = None):
    """
    Gerçek SMTP kullanarak e-posta gönderir.
    images: [{'cid': 'unique_id', 'data': bytes_of_png}, ...] — CID ile gömülü resimler.
    Çevresel değişkenlerde SMTP ayarları yoksa mock (simülasyon) email atar.
    """
    smtp_server = os.environ.get('SMTP_SERVER')
    smtp_port = os.environ.get('SMTP_PORT', 587)
    smtp_username = os.environ.get('SMTP_USERNAME')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    from_name = os.environ.get('SMTP_FROM_NAME', 'Eventix')

    if smtp_server and smtp_username and smtp_password:
        try:
            # Eğer resim varsa related/mixed yapısı kur, yoksa alternative yeterli
            if images:
                outer = MIMEMultipart('mixed')
                outer['Subject'] = subject
                outer['From'] = f"{from_name} <{smtp_username}>"
                outer['To'] = to_email
                outer['Reply-To'] = smtp_username

                alt = MIMEMultipart('alternative')
                alt.attach(MIMEText(message, 'plain'))
                if html_message:
                    related = MIMEMultipart('related')
                    related.attach(MIMEText(html_message, 'html'))
                    for img in images:
                        mime_img = MIMEImage(img['data'], _subtype='png')
                        mime_img.add_header('Content-ID', f"<{img['cid']}>")  
                        mime_img.add_header('Content-Disposition', 'inline', filename=f"{img['cid']}.png")
                        related.attach(mime_img)
                    alt.attach(related)
                outer.attach(alt)
            else:
                outer = MIMEMultipart('alternative')
                outer['Subject'] = subject
                outer['From'] = f"{from_name} <{smtp_username}>"
                outer['To'] = to_email
                outer['Reply-To'] = smtp_username
                outer.attach(MIMEText(message, 'plain'))
                if html_message:
                    outer.attach(MIMEText(html_message, 'html'))

            server = smtplib.SMTP(smtp_server, int(smtp_port))
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(outer)
            server.quit()
            print(f"[REAL] EMAIL SENT TO: {to_email}")
            return
        except Exception as e:
            print(f"[ERROR] SMTP Email Sending Error: {e}")
            print("Warning: Continuing with Simulation (Mock) email...")

    # Fallback to mock
    send_mock_email(to_email, subject, message)

def send_mock_email(to_email: str, subject: str, message: str):
    """
    Simulates sending an email by printing formatted output to the console.
    """
    print(f"\n{'='*50}")
    print(f"[MOCK] EMAIL SENT TO: {to_email}")
    print(f"SUBJECT: {subject}")
    print(f"--------------------------------------------------")
    print(f"{message}")
    print(f"{'='*50}\n")

def send_birthday_emails():
    """
    Her gün çağrılıp, doğum günü bugün olan kullanıcılara HTML tasarımlı şık kutlama mailleri atar.
    Veritabanındaki format 'YYYY-MM-DD' olduğu için son 5 karakter (MM-DD) alınıp bugünün tarihi ile eşlenir.
    """
    from database import get_db_connection
    from datetime import datetime
    import os

    today_mm_dd = datetime.now().strftime("%m-%d")
    
    conn = get_db_connection()
    c = conn.cursor()
    # Tum kayitlari alip python ile MM-DD filter yapmak cloud sqlite (Turso vs) icin en guvenlisidir.
    users = c.execute("SELECT fullname, email, birthdate FROM users WHERE birthdate IS NOT NULL AND birthdate != ''").fetchall()
    conn.close()

    base_url = os.environ.get('FRONTEND_URL', 'http://localhost:5000').rstrip('/')

    count = 0
    for u in users:
        bdate = u['birthdate'] # format expected: YYYY-MM-DD
        if len(bdate) >= 10 and bdate[5:10] == today_mm_dd:
            name = u['fullname']
            email = u['email']

            subject = "🎂 Happy Birthday! - EVENTIX Special Surprise"
            plain_body = f"Happy birthday {name}! At Eventix, we wish you a wonderful year. To make your day special, we have a surprise for you: you've earned a 15% discount with the code BDAY26."
            html_body = f"""
            <html>
            <body style="font-family:'Segoe UI', sans-serif; background-color:#0f0f1a; padding:30px; color:#e2e8f0; text-align:center;">
              <div style="max-width:550px; margin:0 auto; background:linear-gradient(to bottom, #1e1e2e, #161625); border-radius:20px; padding:40px 30px; box-shadow:0 15px 35px rgba(0,0,0,0.6); border:1px solid #2d2d4e;">
                <div style="font-size:60px; margin-bottom:10px;">🎉🎂</div>
                <h1 style="color:#a78bfa; margin:0; font-size:32px; letter-spacing:1px;">Happy Birthday!</h1>
                <h2 style="color:#ffffff; margin-top:10px; font-weight:400;">Dear {name},</h2>
                
                <p style="font-size:16px; line-height:1.6; color:#94a3b8; margin:25px 0;">
                  As the Eventix family, we wish your new age brings you health, happiness, and many more unforgettable event-filled memories!
                </p>
                
                <div style="background:rgba(236,72,153,0.1); border:1px dashed #ec4899; padding:20px; border-radius:12px; margin:30px 0;">
                  <span style="display:block; font-size:12px; color:#ec4899; font-weight:700; text-transform:uppercase; margin-bottom:8px;">🎁 Our Special Surprise Gift for You</span>
                  <div style="font-family:monospace; font-size:24px; color:#ffffff; font-weight:bold; letter-spacing:3px;">BDAY26</div>
                  <span style="display:block; font-size:13px; color:#94a3b8; margin-top:8px;">A <strong>15% Discount</strong> coupon valid instantly on all event tickets!</span>
                </div>
                
                <a href="{base_url}/index.html" style="display:inline-block; padding:15px 32px; background:linear-gradient(135deg, #8b5cf6, #ec4899); color:#ffffff; font-weight:bold; text-decoration:none; border-radius:30px; font-size:15px; box-shadow:0 4px 15px rgba(236,72,153,0.4);">
                  Treat Yourself Today ✨
                </a>
                
                <div style="margin-top:40px; border-top:1px solid #2d2d4e; padding-top:20px;">
                  <p style="color:#475569; font-size:12px; margin:0;">Wishing you a very special day...<br>Eventix Ticketing Platform © 2026</p>
                </div>
              </div>
            </body>
            </html>
            """
            try:
                send_email(to_email=email, subject=subject, message=plain_body, html_message=html_body)
                count += 1
            except Exception as e:
                pass

    if count > 0:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {count} birthday emails successfully sent!")

def send_ticket_confirmation_email(to_email, fullname, event, generated_tickets, total_price, seat_labels_str):
    """
    Centralized function to send professional ticket confirmation emails.
    """
    # Format the date nicely
    def format_event_date(raw_date):
        """Convert ISO date (2026-03-16T19:00:00) to Turkish readable format."""
        try:
            from datetime import datetime
            months_en = {
                1: 'January', 2: 'February', 3: 'March', 4: 'April',
                5: 'May', 6: 'June', 7: 'July', 8: 'August',
                9: 'September', 10: 'October', 11: 'November', 12: 'December'
            }
            # Try parsing with time
            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(str(raw_date), fmt)
                    month_name = months_en.get(dt.month, '')
                    if dt.hour or dt.minute:
                        return f"{dt.day} {month_name} {dt.year} - {dt.strftime('%H:%M')}"
                    else:
                        return f"{dt.day} {month_name} {dt.year}"
                except ValueError:
                    continue
            return str(raw_date)
        except Exception:
            return str(raw_date)

    event_date_formatted = format_event_date(event['date'])

    plain_body = f"Hello {fullname},\n\nYour tickets for '{event['title']}' have been created.\n\n"
    email_images = []
    tickets_html_parts = ""

    for gt in generated_tickets:
        plain_body += f"🎟️ {gt['name']} {gt['surname']} | #{gt['ticket_key']}\n"
        qr_cid = f"qr_{gt['ticket_key']}"
        
        # If the caller provided the bytes directly in the ticket object
        if 'qr_bytes' in gt:
            email_images.append({'cid': qr_cid, 'data': gt['qr_bytes']})
        else:
            # Fallback: re-generate bytes if missing (needs qr_data)
            qr_data_val = gt.get('qr_data') or sign_ticket_data(f"EVENTIX-{gt['ticket_key']}-{event['id']}")
            email_images.append({'cid': qr_cid, 'data': make_qr_bytes(qr_data_val)})

        tickets_html_parts += f"""
        <div style="border:1px dashed #444; padding:20px; margin-bottom:20px; text-align:center; border-radius:12px; background:#1e1e2e; color:#ffffff;">
          <p style="margin:0 0 10px; font-weight:bold; font-size:1.1em; color:#a78bfa;">{gt['name']} {gt['surname']}</p>
          <img src="cid:{qr_cid}" alt="QR Kod" style="width:180px; height:180px; display:block; margin:10px auto; border-radius:8px; border:4px solid #ffffff;" />
          <p style="margin:10px 0 0; font-family:monospace; font-size:1.2em; color:#c4b5fd; letter-spacing:2px; font-weight:bold;">#{gt['ticket_key']}</p>
        </div>"""

    final_html = f"""
    <html>
    <body style="font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color:#0f0f1a; padding:20px; color:#e2e8f0;">
      <div style="max-width:600px; margin:0 auto; background:#161625; border-radius:16px; padding:30px; box-shadow:0 10px 30px rgba(0,0,0,0.5); border:1px solid #2d2d4e;">
        <div style="text-align:center; margin-bottom:25px;">
           <h1 style="color:#a78bfa; margin:0; font-size:28px;">🎟️ Your Tickets are Ready!</h1>
           <p style="color:#94a3b8; font-size:14px; margin-top:5px;">EVENTIX - Witness Unforgettable Moments</p>
        </div>
        
        <p style="font-size:16px;">Hello <strong>{fullname}</strong>,</p>
        <p style="font-size:16px; line-height:1.6;">Your tickets for the event <strong>{event['title']}</strong> have been successfully created. You can enter by showing your QR code to the staff at the event entrance.</p>
        
        <div style="background:rgba(167,139,250,0.05); border-radius:12px; padding:20px; margin:25px 0; border:1px solid rgba(167,139,250,0.2);">
          <p style="margin:0 0 10px; font-size:14px;"><strong style="color:#a78bfa;">📅 Date:</strong> {event_date_formatted}</p>
          <p style="margin:0 0 10px; font-size:14px;"><strong style="color:#a78bfa;">📍 Location:</strong> {event['location']}</p>
          <p style="margin:0 0 10px; font-size:14px;"><strong style="color:#a78bfa;">🪑 Seat(s):</strong> {seat_labels_str}</p>
          <p style="margin:0; font-size:18px; font-weight:bold;"><strong style="color:#2dd4bf;">💳 Total:</strong> {total_price} ₺</p>
        </div>

        <h3 style="color:#ffffff; border-bottom:1px solid #2d2d4e; padding-bottom:10px; margin-bottom:20px;">Event Tickets</h3>
        {tickets_html_parts}
        
        <div style="text-align:center; margin-top:30px; padding-top:20px; border-top:1px solid #2d2d4e;">
          <p style="color:#94a3b8; font-size:13px;">You can access your tickets anytime from the "My Tickets" page on our platform.</p>
          <p style="color:#64748b; font-size:11px; margin-top:20px;">© 2026 Eventix Ticketing Platform. All rights reserved.</p>
        </div>
      </div>
    </body>
    </html>"""

    send_email(
        to_email,
        f"Your Tickets are Ready - {event['title']}",
        plain_body,
        final_html,
        images=email_images
    )

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        if not token:
            return jsonify({'message': 'Token missing!'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE id = ?', (data['id'],)).fetchone()
            conn.close()
            if not user:
                return jsonify({'message': 'Invalid token!'}), 401
            g.user = dict(user)
        except Exception:
            return jsonify({'message': 'Token is invalid or expired!'}), 401
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            if g.user.get('role') not in roles:
                return jsonify({'message': 'Insufficient permission!'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
