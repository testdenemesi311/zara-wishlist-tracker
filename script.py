import os
import time
import json
import smtplib
import re
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from seleniumbase import SB

# ================== AYARLAR ==================

WISHLIST_URL = os.getenv("WISHLIST_URL")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")

# Hangi bedenleri takip ediyoruz?
TARGET_SIZES = ["XS", "S", "M", "L"]

# ================== YARDIMCI FONKSİYONLAR ==================

def send_email(subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        print("⚠️ Mail bilgileri eksik, gönderim yapılmadı.")
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = TO_EMAIL

        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
        print("✅ Mail başarıyla gönderildi.")
    except Exception as e:
        print(f"❌ Mail hatası: {e}")

def check_stock_via_schema(sb, product_url):
    """
    Sayfadaki 'application/ld+json' scriptini bulur ve parse eder.
    API çağırmaz, doğrudan HTML içindeki veriyi okur.
    """
    sb.open(product_url)
    # Sayfanın render olması için kısa süre bekle
    time.sleep(4) 
    
    soup = BeautifulSoup(sb.get_page_source(), "html.parser")
    
    # Tüm JSON-LD scriptlerini bul
    scripts = soup.find_all("script", {"type": "application/ld+json"})
    
    product_data = []
    
    for script in scripts:
        try:
            data = json.loads(script.string)
            
            # Bazen data liste gelir (senin örneğindeki gibi), bazen obje gelir.
            # Hepsini listeye çevirelim ki döngüye sokabilelim.
            if isinstance(data, dict):
                data = [data]
                
            # İçinde "Product" ve "offers" geçen veriyi arıyoruz
            for item in data:
                if item.get("@type") == "Product" and "offers" in item:
                    product_data.append(item)
                    
        except Exception:
            continue

    if not product_data:
        print("   ⚠️ Schema verisi bulunamadı!")
        return [], ""

    # Ürün adını ilk elemandan alalım
    product_name = product_data[0].get("name", "Ürün")
    available_sizes = []

    print(f"   🏷️  Ürün: {product_name}")

    for item in product_data:
        size = item.get("size")
        offer = item.get("offers", {})
        availability = offer.get("availability", "")
        
        # URL formatında gelir: "https://schema.org/InStock"
        status = "STOKTA YOK"
        is_in_stock = False

        if "InStock" in availability:
            status = "VAR"
            is_in_stock = True
        elif "LimitedAvailability" in availability:
            status = "AZ KALDI"
            is_in_stock = True
        
        # Log ekranına yazdıralım
        print(f"   👉 Beden: {size:<4} | Durum: {status}")

        if size in TARGET_SIZES and is_in_stock:
            available_sizes.append(f"{size} ({status})")

    return available_sizes, product_name

# ================== MAIN ==================

def main():
    if not WISHLIST_URL:
        print("❌ WISHLIST_URL tanımlı değil!")
        return

    # Browser'ı başlat
    with SB(uc=True, headless=True, page_load_strategy="normal") as sb:
        print("🚀 Tarayıcı başlatılıyor (Schema Mode)...")
        
        # 1. Wishlist'ten Linkleri Topla
        try:
            print(f"📂 Wishlist taranıyor...")
            sb.open(WISHLIST_URL)
            time.sleep(5)
            sb.scroll_to_bottom()
            time.sleep(2)
            
            soup = BeautifulSoup(sb.get_page_source(), "html.parser")
            product_links = set()
            
            # Sadece ürün linklerini al, ID yerine direkt link saklıyoruz
            for a in soup.find_all('a', href=True):
                href = a['href']
                # Zara ürün linki kontrolü (-p...html)
                if "-p" in href and ".html" in href:
                    # Linkin temiz halini alalım
                    full_link = href if href.startswith("http") else f"https://www.zara.com{href}"
                    product_links.add(full_link)
            
            print(f"📦 Bulunan Link Sayısı: {len(product_links)}")
            
        except Exception as e:
            print(f"❌ Wishlist okuma hatası: {e}")
            return

        found_products = []

        # 2. Her linke git ve Schema kontrolü yap
        for link in product_links:
            print(f"\n🔎 Linke gidiliyor: {link}")
            
            sizes, name = check_stock_via_schema(sb, link)
            
            if sizes:
                print(f"   ✅ BULUNDU: {sizes}")
                found_products.append(f"👗 {name}\nBedenler: {', '.join(sizes)}\n{link}")
            
            # Hızlı istek atıp banlanmamak için bekle
            time.sleep(2)

        # 3. Sonuç
        if found_products:
            subject = "🚨 ZARA STOK YAKALANDI!"
            body = "\n\n".join(found_products)
            send_email(subject, body)
        else:
            print("\n🏁 Tarama bitti, stok yok.")

if __name__ == "__main__":
    main()
