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

# Google JSON Credentials (Secret'tan gelecek)
GOOGLE_JSON = os.getenv("GOOGLE_CREDENTIALS")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")

TARGET_SIZES = ["XS", "S"]
HISTORY_FILE = "stock_history.json"
SHEET_NAME = "ZaraTakip" # Google Sheet dosyanın adı ile aynı olmalı!

# ================== GOOGLE SHEETS BAĞLANTISI ==================

def get_links_from_sheet():
    """Google Sheets'e bağlanır ve A sütunundaki linkleri çeker."""
    if not GOOGLE_JSON:
        print("❌ Google Credentials bulunamadı.")
        return []

    try:
        # JSON stringini dict'e çevir
        creds_dict = json.loads(GOOGLE_JSON)
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Tabloyu aç
        sheet = client.open(SHEET_NAME).sheet1
        
        # 1. Sütundaki (A sütunu) tüm verileri al
        links = sheet.col_values(1)
        
        # Zara linki olmayanları ve başlıkları temizle
        valid_links = []
        for link in links:
            if "zara.com" in link and "-p" in link:
                valid_links.append(link.strip())
                
        print(f"📋 Google Sheet'ten {len(valid_links)} link çekildi.")
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

        product_name = product_data[0].get("name", "Ürün")
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
    except Exception as e:
        print(f"⚠️ Link Hatası ({product_url}): {e}")
        return [], ""

# ================== MAIN ==================

def main():
    # 1. Linkleri Sheet'ten al
    product_links = get_links_from_sheet()
    
    if not product_links:
        print("❌ Takip edilecek link yok.")
        return

    history = load_history()
    current_state = {}
    email_messages = []

    with SB(uc=True, headless=True, page_load_strategy="normal") as sb:
        print("🚀 Stok kontrolü başlıyor (Sheets Modu)...")

        for link in product_links:
            clean_link = link.split('?')[0]
            print(f"🔎 {clean_link}")
            
            sizes_now, name = check_stock_via_schema(sb, link)
            current_state[clean_link] = sizes_now
            
            sizes_old = history.get(clean_link, [])
            new_arrivals = set(sizes_now) - set(sizes_old)
            
            if new_arrivals:
                found_msg = f"🔥 YENİ STOK: {', '.join(new_arrivals)}"
                print(f"   {found_msg}")
                email_messages.append(f"👗 {name}\n{found_msg}\nTam Liste: {sizes_now}\n{clean_link}")
            
            time.sleep(2)

    save_history(current_state)
    
    if email_messages:
        subject = "🚨 ZARA: STOK GÜNCELLEMESİ (SHEETS)"
        body = "Takip listendeki ürünlerde hareket var:\n\n" + "\n\n".join(email_messages)
        send_email(subject, body)
    else:
        print("🏁 Değişiklik yok.")

if __name__ == "__main__":
    main()
