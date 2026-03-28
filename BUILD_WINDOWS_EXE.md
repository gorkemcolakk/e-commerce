# 🖥️ Eventix - Windows .exe Oluşturma Rehberi

## Gereksinimler
- **Python 3.10+** kurulu olmalı → [python.org/downloads](https://www.python.org/downloads/)
  - Kurulum sırasında **"Add Python to PATH"** seçeneğini işaretle!

## Adımlar

### 1. Repoyu klonla
```bash
git clone https://github.com/gorkemcolakk/e-commerce.git
cd e-commerce
```

### 2. .env dosyasını oluştur
Proje kök dizinine `.env` dosyası oluştur ve içine şunu yaz:
```
# SMTP Sunucu Ayarlari (Gmail)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=ticketeventix@gmail.com
SMTP_PASSWORD=ykrhpcnzllyhmbro
SMTP_FROM_NAME=Eventix Ticket

# Frontend URL
FRONTEND_URL=http://localhost:5002

# Turso Cloud DB Settings
TURSO_DB_URL=libsql://e-commerce-grkeemcolak.aws-eu-west-1.turso.io
TURSO_AUTH_TOKEN=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzM5MzE1ODYsImlkIjoiMDE5ZDA2OGQtNjkwMS03ZGVkLTljMTYtZDgwMzA4MTE1NDZlIiwicmlkIjoiYjEyM2JlYWItM2NkMS00YzBhLWI2MjgtMGVjYzAzZjQ1NGJmIn0.jn27jQUhr2IObRVkFuEMTQAd5gYVNUk3EIjsfyjlnynMDdu8nfz_fEelJBaZh_GzIMjp52VKkM99fl96EEBrCQ
```

### 3. Bağımlılıkları kur
```bash
pip install -r requirements.txt
```

### 4. Build script'ini çalıştır
```bash
python build_exe.py
```

### 5. Sonuç
Build tamamlandığında `dist/Eventix.exe` dosyası oluşacak.

## Çalıştırma
1. `dist/Eventix.exe` dosyasını çift tıkla
2. Tarayıcıda `http://localhost:5002` adresini aç
3. Uygulama açılacak! 🎉

## Sorun Giderme
- **"Python bulunamadı" hatası**: Python'ı PATH'e eklediğinden emin ol
- **pip hatası**: `python -m pip install -r requirements.txt` dene
- **Build hatası**: `pip install pyinstaller --upgrade` dene
- **Antivirüs uyarısı**: Windows Defender PyInstaller exe'lerini bazen yanlışlıkla işaretler, "Yine de çalıştır" de
