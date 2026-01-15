import os
import time
import json
import smtplib
import re
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from seleniumbase import SB
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================== AYARLAR ==================

GOOGLE_JSON = os.getenv("GOOGLE_CREDENTIALS")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")

# Hem harf hem sayı bedenleri (Pantolon, Kot, Üst Giyim)
TARGET_SIZES = ["XS", "S", "34", "36", "38", "25", "26", "27"]

HISTORY_FILE = "stock_history.json"
SHEET_NAME = "ZaraTakip"

# ================== GOOGLE SHEETS ==================

def get_links_from_sheet():
    if not GOOGLE_JSON:
        print("❌ Google Credentials bulunamadı.")
        return []

    try:
        creds_dict = json.loads(GOOGLE_JSON)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open(SHEET_NAME).sheet1
        links = sheet.col_values(1)
        
        valid_links = []
        for link in links:
            # -p ürün ID'sini kontrol et ama linki BOZMA (v1 parametresi kalsın)
            if "zara.com" in link and "-p" in link:
                valid_links.append(link.strip())
                
        print(f"📋 Google Sheet'ten {len(valid_links)} link çekildi.")
        # Set kullanarak tekrar edenleri temizle ama listeye çevir
        return list(set(valid_links))
        
    except Exception as e:
        print(f"❌ Google Sheets Hatası: {e}")
        return []

# ================== YARDIMCI FONKSİYONLAR ==================

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(data):
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
        print("✅ Mail gönderildi.")
    except Exception as e:
        print(f"❌ Mail hatası: {e}")

def check_stock_via_schema(sb, product_url):
    try:
        # 1. URL içinde v1 kodu var mı? (Spesifik renk takibi)
        target_v1 = None
        v1_match = re.search(r'[?&]v1=(\d+)', product_url)
        if v1_match:
            target_v1 = v1_match.group(1)
            print(f"   🎯 Hedef Renk Kodu (v1): {target_v1}")

        sb.open(product_url)
        time.sleep(3)
        
        soup = BeautifulSoup(sb.get_page_source(), "html.parser")
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        
        product_data = []
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict): data = [data]
                for item in data:
                    if item.get("@type") == "Product" and "offers" in item:
                        product_data.append(item)
            except: continue

        if not product_data: return [], ""

        # Ürün adı (Genel isim)
        product_name = product_data[0].get("name", "Ürün")
        current_in_stock = set()
        
        for item in product_data:
            # 2. Schema içindeki URL'yi kontrol et
            # Schema verisi bazen sayfadaki TÜM renkleri içerir.
            # Eğer kullanıcı özel bir renk istediyse (v1), sadece o rengi işle.
            
            offer = item.get("offers", {})
            schema_url = offer.get("url", "")
            
            # KRİTİK FİLTRE: Eğer hedef v1 var ise ve bu item o v1'e sahip değilse -> ATLA
            if target_v1 and target_v1 not in schema_url:
                continue
            
            size = item.get("size")
            availability = offer.get("availability", "")
            
            is_stock = False
            if "InStock" in availability or "LimitedAvailability" in availability:
                is_stock = True
            
            # Hedef bedenlerden biri mi?
            if size in TARGET_SIZES and is_stock:
                current_in_stock.add(size)

        return sorted(list(current_in_stock)), product_name

    except Exception as e:
        print(f"⚠️ Link Hatası ({product_url}): {e}")
        return [], ""

# ================== MAIN ==================

def main():
    product_links = get_links_from_sheet()
    
    if not product_links:
        print("❌ Takip edilecek link yok.")
        return

    history = load_history()
    current_state = {}
    email_messages = []

    with SB(uc=True, headless=True, page_load_strategy="normal") as sb:
        print("🚀 Stok kontrolü başlıyor...")

        for link in product_links:
            # Loglarda temiz görünsün ama fonksiyona TAM linki gönder
            display_link = link.split('?')[0]
            print(f"🔎 İnceleniyor: {display_link}")
            
            # Fonksiyona orjinal linki (v1 parametreli) gönderiyoruz
            sizes_now, name = check_stock_via_schema(sb, link)
            
            # Linki geçmişe kaydederken tam haliyle kaydet (farklı renkler karışmasın)
            current_state[link] = sizes_now
            
            # Geçmiş kontrolü
            sizes_old = history.get(link, [])
            new_arrivals = set(sizes_now) - set(sizes_old)
            
            if new_arrivals:
                found_msg = f"🔥 YENİ STOK: {', '.join(new_arrivals)}"
                print(f"   {found_msg}")
                # Mailde tıklanabilir link tam link olsun
                email_messages.append(f"👗 {name}\n{found_msg}\nTam Liste: {sizes_now}\n{link}")
            
            time.sleep(2)

    save_history(current_state)
    
    if email_messages:
        subject = "🚨 ZARA: YENİ STOK GELDİ!"
        body = "Takip ettiğin ürün/renkte hareket var:\n\n" + "\n\n".join(email_messages)
        send_email(subject, body)
    else:
        print("🏁 Değişiklik yok.")

if __name__ == "__main__":
    main()
