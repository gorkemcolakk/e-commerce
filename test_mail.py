from dotenv import load_dotenv
load_dotenv()

import os, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

smtp_server   = os.environ.get('SMTP_SERVER')
smtp_port     = os.environ.get('SMTP_PORT', 587)
smtp_username = os.environ.get('SMTP_USERNAME')
smtp_password = os.environ.get('SMTP_PASSWORD')

print(f"SMTP_SERVER   = {smtp_server}")
print(f"SMTP_PORT     = {smtp_port}")
print(f"SMTP_USERNAME = {smtp_username}")

msg = MIMEMultipart('alternative')
msg['Subject'] = 'Eventix Test - Mail Sistemi Calisiyor!'
msg['From']    = f'Eventix <{smtp_username}>'
msg['To']      = smtp_username

plain = "Bu bir test mailidir. Eventix mail sistemi calisiyor!"
html = """
<html>
<body style="font-family:Arial; background:#0f0f1a; padding:30px; color:#e2e8f0;">
  <div style="max-width:500px; margin:0 auto; background:#161625; border-radius:16px; padding:30px; border:1px solid #2d2d4e; text-align:center;">
    <h1 style="color:#a78bfa;">Eventix</h1>
    <p style="font-size:18px; color:#22c55e;">Mail sistemi basariyla calisiyor!</p>
    <p style="color:#94a3b8;">Bu bir test mailidir. Bilet aldiginizda bu sekilde profesyonel bir mail alacaksiniz.</p>
    <hr style="border:none; border-top:1px solid #2d2d4e; margin:20px 0;">
    <p style="color:#64748b; font-size:12px;">2026 Eventix Biletleme Platformu</p>
  </div>
</body>
</html>
"""

msg.attach(MIMEText(plain, 'plain'))
msg.attach(MIMEText(html, 'html'))

try:
    print("\nSMTP sunucusuna baglaniliyor...")
    server = smtplib.SMTP(smtp_server, int(smtp_port))
    server.starttls()
    print("TLS baglantisi kuruldu.")
    server.login(smtp_username, smtp_password)
    print("Giris basarili!")
    server.send_message(msg)
    server.quit()
    print(f"\nBASARILI! Test maili {smtp_username} adresine gonderildi!")
    print("Gmail gelen kutunuzu kontrol edin.")
except Exception as e:
    print(f"\nHATA: {e}")
