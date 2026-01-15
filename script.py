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

# Eğer B sütunu boş bırakılırsa aranacak varsayılan bedenler
DEFAULT_SIZES = ["XS", "S", "34", "36"]

HISTORY_FILE = "stock_history.json"
SHEET_NAME = "ZaraTakip"

# ================== GOOGLE SHEETS ==================

def get_tasks_from_sheet():
    """
    Google Sheets'ten Link (Kolon A) ve İstenen Bedenleri (Kolon B) okur.
    Dönüş Formatı: [ (Link, [Bedenler]), ... ]
    """
    if not GOOGLE_JSON:
        print("❌ Google Credentials bulunamadı.")
        return []

    try:
        creds_dict = json.loads(GOOGLE_JSON)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open(SHEET_NAME).sheet1
        
        # Tüm satırları al (A ve B kolonları dahil)
        rows = sheet.get_all_values()
        
        tasks = []
        print(f"📋 Tablo okunuyor... ({len(rows)} satır)")

        for row in rows:
            # Satır boşsa veya link yoksa geç
            if not row or len(row) < 1:
                continue
                
            link = row[0].strip()
            
            # Zara linki değilse geç (Başlık satırını atlar)
            if "zara.com" not in link or "-p" not in link:
                continue

            # B Kolonu var mı? Varsa virgülle ayırıp listeye çevir
            desired_sizes = []
            if len(row) > 1 and row[1].strip():
                # Örn: "XS, S, 36" -> ["XS", "S", "36"]
                raw_sizes = row[1].split(',')
                # Boşlukları temizle ve hepsini büyük harf yap (xs -> XS)
                desired_sizes = [s.strip().upper() for s in raw_sizes if s.strip()]
            
            # Eğer B kolonu boşsa varsayılanları kullan
            if not desired_sizes:
                desired_sizes = DEFAULT_SIZES

            tasks.append((link, desired_sizes))
            
        return tasks
        
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

def check_stock_via_schema(sb, product_url, target_sizes):
    """
    Belirtilen URL'de, SADECE 'target_sizes' içinde verilen bedenleri arar.
    """
    try:
        # v1 Renk Filtresi
        target_v1 = None
        v1_match = re.search(r'[?&]v1=(\d+)', product_url)
        if v1_match:
            target_v1 = v1_match.group(1)

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
        
        print(f"   🎯 Aranan Bedenler: {target_sizes}")

        for item in product_data:
            # Renk Filtresi Kontrolü
            offer = item.get("offers", {})
            schema_url = offer.get("url", "")
            if target_v1 and target_v1 not in schema_url:
                continue
            
            size = item.get("size")
            availability = offer.get("availability", "")
            
            is_stock = False
            if "InStock" in availability or "LimitedAvailability" in availability:
                is_stock = True
            
            # --- KRİTİK NOKTA: Listeden gelen özel bedenleri kontrol et ---
            # item['size'] API'den bazen "XS " (boşluklu) gelebilir, strip() yapıyoruz.
            if size and size.strip().upper() in target_sizes and is_stock:
                current_in_stock.add(size.strip())

        return sorted(list(current_in_stock)), product_name

    except Exception as e:
        print(f"⚠️ Link Hatası ({product_url}): {e}")
        return [], ""

# ================== MAIN ==================

def main():
    # 1. Sheet'ten görevleri al: [(Link1, ['XS']), (Link2, ['36', '38'])]
    tasks = get_tasks_from_sheet()
    
    if not tasks:
        print("❌ Takip edilecek link yok.")
        return

    history = load_history()
    current_state = {}
    email_messages = []

    with SB(uc=True, headless=True, page_load_strategy="normal") as sb:
        print("🚀 Stok kontrolü başlıyor (Kişiselleştirilmiş Mod)...")

        for link, desired_sizes in tasks:
            display_link = link.split('?')[0]
            print(f"\n🔎 İnceleniyor: {display_link}")
            
            # Fonksiyona artık o satırın özel beden listesini gönderiyoruz
            sizes_now, name = check_stock_via_schema(sb, link, desired_sizes)
            
            # Geçmişe kaydet
            current_state[link] = sizes_now
            
            # Karşılaştırma
            sizes_old = history.get(link, [])
            new_arrivals = set(sizes_now) - set(sizes_old)
            
            if new_arrivals:
                found_msg = f"🔥 YENİ STOK: {', '.join(new_arrivals)}"
                print(f"   {found_msg}")
                email_messages.append(f"👗 {name}\n🎯 Aradığın: {', '.join(desired_sizes)}\n✨ Bulunan: {', '.join(new_arrivals)}\n{link}")
            elif sizes_now:
                print(f"   ℹ️ Stok var ama yeni değil: {sizes_now}")
            else:
                print("   💤 Stok yok.")
            
            time.sleep(2)

    save_history(current_state)
    
    if email_messages:
        subject = "🚨 ZARA: ARADIĞIN BEDENLER GELDİ!"
        body = "Listendeki özel bedenler stokta:\n\n" + "\n\n".join(email_messages)
        send_email(subject, body)
    else:
        print("\n🏁 Değişiklik yok.")

if __name__ == "__main__":
    main()
