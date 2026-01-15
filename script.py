import os
import time
import json
import smtplib
import re
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from seleniumbase import SB

# ================== AYARLAR ==================

# GitHub Secrets'tan gelecek veriler
WISHLIST_URL = os.getenv("WISHLIST_URL")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")

STORE_ID = "11766"  # Türkiye Store ID
TARGET_SIZES = ["XS", "S", "M", "L"]

# ================== YARDIMCI FONKSİYONLAR ==================

def send_email(subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        print("⚠️ Mail credentials bulunamadı, mail atlanıyor.")
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

def get_json_via_browser(sb, url):
    """
    API isteğini requests yerine Browser üzerinden yapar.
    Bu sayede Bot korumasına takılmaz.
    """
    sb.open(url)
    # Sayfanın yüklenmesini bekle ve içeriği al (JSON text olarak döner)
    content = sb.get_text("body")
    try:
        return json.loads(content)
    except:
        return None

# ================== ANA İŞLEM (SB CONTEXT) ==================

def main():
    if not WISHLIST_URL:
        print("❌ WISHLIST_URL tanımlı değil.")
        return

    # UC=True (Undetected) ve Headless (Ekran yok) modu
    with SB(uc=True, headless=True, page_load_strategy="eager") as sb:
        print("🚀 Tarayıcı başlatılıyor...")
        
        # 1. Wishlist Sayfasına Git
        try:
            sb.open(WISHLIST_URL)
            time.sleep(5) # Sayfanın tam yüklenmesi için bekle
            sb.scroll_to_bottom() # Lazy load varsa tetikle
            time.sleep(2)
            
            page_source = sb.get_page_source()
            soup = BeautifulSoup(page_source, "html.parser")
            
            product_ids = set()
            # Linklerden ID toplama
            for link in soup.find_all('a', href=True):
                match = re.search(r'-p(\d+)\.html', link['href'])
                if match:
                    product_ids.add(match.group(1))
            
            product_ids = list(product_ids)
            print(f"📦 Bulunan ID sayısı: {len(product_ids)}")
            
        except Exception as e:
            print(f"❌ Wishlist açılırken hata: {e}")
            return

        # 2. Ürünleri Kontrol Et
        found_products = []
        
        for pid in product_ids:
            print(f"🔍 Kontrol ediliyor: {pid}")
            api_url = f"https://www.zara.com/itxrest/3/catalog/store/{STORE_ID}/product/{pid}/detail?languageId=-1"
            
            # API'ye tarayıcı ile git
            data = get_json_via_browser(sb, api_url)
            
            if not data:
                continue

            name = data.get("name", "Ürün")
            link = f"https://www.zara.com/tr/tr/-p{pid}.html"
            sizes_found = []

            for bundle in data.get("detail", {}).get("colors", []):
                for size in bundle.get("sizes", []):
                    s_name = size.get("name")
                    avail = size.get("availability")
                    
                    if s_name in TARGET_SIZES and avail in ["in_stock", "low_on_stock"]:
                        sizes_found.append(s_name)
            
            sizes_found = sorted(list(set(sizes_found)))
            
            if sizes_found:
                print(f"   ✅ STOK VAR: {sizes_found}")
                found_products.append(f"👗 {name}\nBeden: {', '.join(sizes_found)}\n{link}")
            
            time.sleep(2) # Hızlı istek atıp banlanmamak için

        # 3. Sonuç
        if found_products:
            subject = "🚨 ZARA STOK BULUNDU"
            body = "\n\n".join(found_products)
            send_email(subject, body)
        else:
            print("🏁 Stok bulunamadı.")

if __name__ == "__main__":
    main()
