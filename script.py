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

TARGET_SIZES = ["XS", "S", "M", "L"]

# ================== YARDIMCI FONKSİYONLAR ==================

def send_email(subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        print("⚠️ Mail bilgileri eksik.")
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
        print("✅ Mail gönderildi.")
    except Exception as e:
        print(f"❌ Mail hatası: {e}")

def check_stock_via_schema(sb, product_url):
    """
    Sayfadaki Schema.org verisini okur.
    """
    sb.open(product_url)
    time.sleep(3) # Sayfanın oturması için bekle
    
    soup = BeautifulSoup(sb.get_page_source(), "html.parser")
    scripts = soup.find_all("script", {"type": "application/ld+json"})
    
    product_data = []
    
    # Tüm JSON bloklarını tara
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                data = [data]
            
            for item in data:
                if item.get("@type") == "Product" and "offers" in item:
                    product_data.append(item)
        except:
            continue

    if not product_data:
        print("   ⚠️ Schema verisi bulunamadı!")
        return [], ""

    product_name = product_data[0].get("name", "Ürün")
    
    # Set kullanarak aynı bedenin 2 kere yazılmasını engelliyoruz
    found_sizes_set = set()

    print(f"   🏷️  Ürün: {product_name}")

    for item in product_data:
        size = item.get("size")
        offer = item.get("offers", {})
        availability = offer.get("availability", "")
        
        status_text = "YOK"
        is_stock = False

        if "InStock" in availability:
            status_text = "VAR"
            is_stock = True
        elif "LimitedAvailability" in availability:
            status_text = "AZ KALDI"
            is_stock = True
        
        # Loga bas (Debug için)
        print(f"   👉 {size:<4} : {status_text}")

        if size in TARGET_SIZES and is_stock:
            found_sizes_set.add(f"{size} ({status_text})")

    # Set'i listeye çevirip sırala
    return sorted(list(found_sizes_set)), product_name

# ================== MAIN ==================

def main():
    if not WISHLIST_URL:
        print("❌ WISHLIST_URL eksik.")
        return

    with SB(uc=True, headless=True, page_load_strategy="normal") as sb:
        print("🚀 Tarayıcı başlatılıyor...")
        
        # --- ADIM 1: LİNKLERİ TOPLA ---
        try:
            print(f"📂 Wishlist taranıyor...")
            sb.open(WISHLIST_URL)
            time.sleep(5)
            sb.scroll_to_bottom()
            time.sleep(2)
            
            soup = BeautifulSoup(sb.get_page_source(), "html.parser")
            product_links = set()
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                
                # --- İYİLEŞTİRME BURADA ---
                # Sadece içinde "-p" ve sonrasında RAKAM olanları al.
                # Örn: ...-p123456.html (Geçerli)
                # Örn: ...pantolon-l123.html (Geçersiz)
                if re.search(r'-p\d+\.html', href):
                    full_link = href if href.startswith("http") else f"https://www.zara.com{href}"
                    product_links.add(full_link)
            
            print(f"📦 Bulunan Ürün Linki Sayısı: {len(product_links)}")
            
        except Exception as e:
            print(f"❌ Wishlist hatası: {e}")
            return

        found_products = []

        # --- ADIM 2: KONTROL ET ---
        for link in product_links:
            # Query parametrelerini (?v1=...) temizle ki log temiz dursun
            clean_link = link.split('?')[0]
            print(f"\n🔎 {clean_link}")
            
            sizes, name = check_stock_via_schema(sb, link)
            
            if sizes:
                print(f"   ✅ YAKALANDI: {sizes}")
                found_products.append(f"👗 {name}\nDurum: {', '.join(sizes)}\n{clean_link}")
            
            time.sleep(2)

        # --- ADIM 3: SONUÇ ---
        if found_products:
            subject = "🚨 ZARA STOK ALARMI"
            body = "\n\n".join(found_products)
            send_email(subject, body)
        else:
            print("\n🏁 Tarama bitti, stok yok.")

if __name__ == "__main__":
    main()
