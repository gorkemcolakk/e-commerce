"""
Eventix - EXE Build Script
===========================
Bu script PyInstaller kullanarak Eventix uygulamasını
tek bir çalıştırılabilir dosya haline getirir.

Kullanım:
  1. pip install pyinstaller
  2. python build_exe.py

Not: 
  - Windows'ta çalıştırırsan .exe üretir
  - macOS'ta çalıştırırsan macOS executable üretir
  - Linux'ta çalıştırırsan Linux executable üretir
"""

import subprocess
import sys
import os

def main():
    # PyInstaller kurulu mu kontrol et
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__} bulundu.")
    except ImportError:
        print("[INFO] PyInstaller kuruluyor...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("[OK] PyInstaller kuruldu.")

    # certifi kurulu mu kontrol et
    try:
        import certifi
        print(f"[OK] certifi bulundu.")
    except ImportError:
        print("[INFO] certifi kuruluyor...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "certifi"])

    # Proje kök dizini
    project_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Toplamak istediğimiz data dosyaları
    # PyInstaller formatı: "kaynak_yol;hedef_yol" (Windows) veya "kaynak_yol:hedef_yol" (macOS/Linux)
    separator = ";" if sys.platform == "win32" else ":"
    
    datas = []
    
    # Frontend klasörü (HTML, CSS, JS dosyaları)
    frontend_dir = os.path.join(project_dir, "frontend")
    if os.path.isdir(frontend_dir):
        datas.append(f"{frontend_dir}{separator}frontend")
        print(f"[DIR] Frontend klasörü eklendi: {frontend_dir}")
    
    # .env dosyası
    env_file = os.path.join(project_dir, ".env")
    if os.path.isfile(env_file):
        datas.append(f"{env_file}{separator}.")
        print(f"[FILE] .env dosyası eklendi")
    
    # database.db (varsa)
    db_file = os.path.join(project_dir, "database.db")
    if os.path.isfile(db_file):
        datas.append(f"{db_file}{separator}.")
        print(f"[FILE] database.db eklendi")
    
    # certifi sertifika dosyası
    try:
        import certifi
        cert_file = certifi.where()
        datas.append(f"{cert_file}{separator}certifi")
        print(f"[SSL] SSL sertifikaları eklendi")
    except Exception:
        pass

    # Hidden imports - PyInstaller'ın otomatik bulamayabileceği modüller
    hidden_imports = [
        "routes",
        "routes.auth",
        "routes.users",
        "routes.events",
        "routes.tickets",
        "routes.wishlist",
        "routes.notifications",
        "routes.organizer",
        "routes.admin",
        "routes.upload",
        "database",
        "utils",
        "payment",
        "flask",
        "flask_cors",
        "flask_limiter",
        "werkzeug",
        "jinja2",
        "jinja2.ext",
        "jwt",
        "qrcode",
        "PIL",
        "PIL.Image",
        "dotenv",
        "certifi",
        "sqlite3",
        "email.mime.text",
        "email.mime.multipart",
        "email.mime.base",
        "smtplib",
        "hashlib",
        "json",
        "threading",
        "libsql_client",
    ]

    # PyInstaller komutu oluştur
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # Tek dosya olarak paketle
        "--name", "Eventix",            # Çıkış dosyası adı
        "--clean",                      # Önceki build dosyalarını temizle
        "--noconfirm",                  # Onay sorma
    ]
    
    # Data dosyalarını ekle
    for data in datas:
        cmd.extend(["--add-data", data])
    
    # Hidden import'ları ekle
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])
    
    # routes klasörünü data olarak da ekle (Python dosyaları için)
    routes_dir = os.path.join(project_dir, "routes")
    if os.path.isdir(routes_dir):
        cmd.extend(["--add-data", f"{routes_dir}{separator}routes"])
    
    # Ana uygulama dosyasını belirt
    cmd.append(os.path.join(project_dir, "app.py"))
    
    print("\n[BUILD] Build başlatılıyor...\n")
    print(f"Komut: {' '.join(cmd)}\n")
    
    # Build'i çalıştır
    result = subprocess.run(cmd, cwd=project_dir)
    
    if result.returncode == 0:
        if sys.platform == "win32":
            exe_path = os.path.join(project_dir, "dist", "Eventix.exe")
        else:
            exe_path = os.path.join(project_dir, "dist", "Eventix")
        
        print("\n" + "=" * 60)
        print("BUILD BASARILI!")
        print("=" * 60)
        print(f"\n[LOC] Dosya konumu: {exe_path}")
        print(f"\n[RUN] Çalıştırmak için:")
        if sys.platform == "win32":
            print(f"   dist\\Eventix.exe")
        else:
            print(f"   ./dist/Eventix")
        print(f"\n[URL] Tarayıcıda açmak için: http://localhost:5002")
        print("=" * 60)
    else:
        print("\n[FAIL] Build başarısız oldu! Yukarıdaki hata mesajlarını kontrol edin.")
        sys.exit(1)


if __name__ == "__main__":
    main()
