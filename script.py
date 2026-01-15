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

TARGET_SIZES = ["XS", "S"]
HISTORY_FILE = "stock_history.json"

# ================== YARDIMCI FONKSİYONLAR ==================

def load_history():
    """Önceki taramadan kalan stok verilerini yükler."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(data):
    """Güncel stok verilerini dosyaya kaydeder."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

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
        print("✅ Mail başarıyla gönderildi.")
    except Exception as e:
        print(f"❌ Mail hatası: {e}")

def check_stock_via_schema(sb, product_url):
    sb.open(product_url)
    time.sleep(3)
    
    soup = BeautifulSoup(sb.get_page_source(), "html.parser")
    scripts = soup.find_all("script", {"type": "application/ld+json"})
    
    product_data = []
    
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
        return [], ""

    product_name = product_data[0].get("name", "Ürün")
    
    # Şu an stokta olan hedef bedenleri bul
    current_in_stock = set()
    
    for item in product_data:
        size = item.get("size")
        offer = item.get("offers", {})
        availability = offer.get("availability", "")
        
        is_stock = False
        if "InStock" in availability or "LimitedAvailability" in availability:
            is_stock = True
        
        if size in TARGET_SIZES and is_stock:
            current_in_stock.add(size)

    return sorted(list(current_in_stock)), product_name

# ================== MAIN ==================

def main():
    if not WISHLIST_URL:
        print("❌ WISHLIST_URL eksik.")
        return

    # Geçmiş veriyi yükle
    history = load_history()
    # Bu turdaki güncel durumu saklayacağımız sözlük
    current_state = {}
    
    email_messages = []

    with SB(uc=True, headless=True, page_load_strategy="normal") as sb:
        print("🚀 Akıllı Stok Kontrolü Başlıyor...")
        
        # --- LİNKLERİ TOPLA ---
        try:
            sb.open(WISHLIST_URL)
            time.sleep(5)
            sb.scroll_to_bottom()
            time.sleep(2)
            
            soup = BeautifulSoup(sb.get_page_source(), "html.parser")
            product_links = set()
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                if re.search(r'-p\d+\.html', href):
                    full_link = href if href.startswith("http") else f"https://www.zara.com{href}"
                    product_links.add(full_link)
            
            print(f"📦 Taranacak Ürün Sayısı: {len(product_links)}")
            
        except Exception as e:
            print(f"❌ Hata: {e}")
            return

        # --- KONTROL ET VE KARŞILAŞTIR ---
        for link in product_links:
            clean_link = link.split('?')[0]
            print(f"🔎 {clean_link}")
            
            sizes_now, name = check_stock_via_schema(sb, link)
            
            # Bu ürün için güncel durumu kaydet (JSON'a yazılacak)
            current_state[clean_link] = sizes_now
            
            # --- MANTIK KISMI ---
            # Eskiden ne vardı?
            sizes_old = history.get(clean_link, [])
            
            # Yeni ne geldi? (Küme farkı işlemi: Şimdikiler - Eskiler)
            new_arrivals = set(sizes_now) - set(sizes_old)
            
            if new_arrivals:
                # Sadece YENİ gelen bedenler için bildirim oluştur
                found_msg = f"🔥 YENİ STOK: {', '.join(new_arrivals)}"
                print(f"   {found_msg}")
                email_messages.append(f"👗 {name}\n{found_msg}\nTam Liste: {sizes_now}\n{clean_link}")
            elif sizes_now:
                print(f"   ℹ️ Stok var ama değişiklik yok ({sizes_now}) -> Mail atılmıyor.")
            else:
                print("   💤 Stok yok.")
            
            time.sleep(2)

    # --- VERİYİ GÜNCELLE VE MAİL AT ---
    
    # Geçmiş dosyasını güncelle
    save_history(current_state)
    
    if email_messages:
        subject = "🚨 ZARA: YENİ BEDEN GELDİ!"
        body = "Gözün aydın, takip ettiğin ürünlerde YENİ stok hareketleri var:\n\n" + "\n\n".join(email_messages)
        send_email(subject, body)
    else:
        print("🏁 Yeni bir stok gelişmesi yok, mail atılmadı.")

if __name__ == "__main__":
    main()
