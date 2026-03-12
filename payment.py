import time

class PaymentGateway:
    """
    Sanal POS entegrasyonu için genel sarmalayıcı (wrapper) sınıf.
    İleride Iyzico, Stripe veya Param gibi gerçek POS API servislerine buradan entegre olabilirsiniz.
    Şu anki halinde kredi kartı kurallarına göre bir ödeme simülasyonu çalıştırır.
    """
    
    @staticmethod
    def process_payment(amount: float, card_name: str, card_number: str, exp_date: str, cvc: str) -> dict:
        """
        amount: Siparişin son tutarı (İndirimler hesaplandıktan sonra)
        
        DÖNÜŞ (Return):
        {"success": True/False, "transaction_id": "...", "message": "Hata açıklaması"}
        """
        
        # Gerçek bir API isteğini simüle etmek için gecikme (network latency)
        time.sleep(1.2)
        
        # Sadece sayıları al
        clean_number = "".join(filter(str.isdigit, str(card_number)))
        
        # Eğer tutar 0 ise (Tamamı hediye/indirim koduyla ödenmişse) pos'a bile gitmeden direkt onayla
        if amount == 0:
            return {
                "success": True, 
                "transaction_id": "FREE_" + str(int(time.time() * 1000)),
                "message": "Ücretsiz işlem başarılı."
            }

        # TEST KARTLARI (Simülasyon Senaryoları)
        
        # 1. Her zaman reddedilen test kartı:
        if clean_number.startswith('0000'):
            return {"success": False, "message": "Ödeme reddedildi: Sahte/Test kartı kuralı."}
            
        # 2. Bakiye yetersiz limiti dönen test kartı (5111 ile başlayanlar)
        if clean_number.startswith('5111'):
             return {"success": False, "message": "Ödeme başarısız: Kart bakiyesi veya limiti yetersiz."}
             
        # 3. İletişim Hatası
        if clean_number.startswith('9999'):
             return {"success": False, "message": "Ödeme sistemi ile iletişim kurulamadı (Timeout)."}

        # GENEL KONTROLLER
        if len(clean_number) < 15 or len(clean_number) > 19:
            return {"success": False, "message": "Geçersiz kart numarası. (Minimum 15, Makimum 19 Hane)"}
            
        if not exp_date or '/' not in exp_date:
            return {"success": False, "message": "Son kullanma tarihi geçerli değil. (Beklenen: AA/YY)"}
            
        try:
            month, year = exp_date.split('/')
            if int(month) < 1 or int(month) > 12:
                return {"success": False, "message": "Geçersiz ay formatı. Lütfen 01 ile 12 arasında girin."}
        except ValueError:
            return {"success": False, "message": "Geçersiz son kullanma tarihi formatı."}
            
        clean_cvc = "".join(filter(str.isdigit, str(cvc)))
        if len(clean_cvc) < 3 or len(clean_cvc) > 4:
            return {"success": False, "message": "Geçersiz CVC numarası."}
            
        # Eğer yukarıdaki koşullara takılmadıysa BAŞARILI KABUL ET
        transaction_id = "TRX_" + str(int(time.time() * 1000))
        
        return {
            "success": True,
            "transaction_id": transaction_id,
            "message": "Ödeme Başarılı"
        }
