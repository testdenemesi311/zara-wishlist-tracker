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

STORE_ID = "11766"  
TARGET_SIZES = ["XS", "S", "M", "L", "XL"] # XL'ı da ekleyelim test için

# ================== YARDIMCI FONKSİYONLAR ==================

def send_email(subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        print("⚠️ Mail credentials bulunamadı.")
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
    Tarayıcıdan alınan text bazen HTML tagleri içerebilir.
    Bunu temizleyip saf JSON'a çeviriyoruz.
    """
    sb.open(url)
    content = sb.get_text("body") # Tüm sayfayı text olarak al
    
    # Eğer tarayıcı JSON'u bir HTML içine gömdüyse temizle
    try:
        # Önce direkt parse etmeyi dene
        return json.loads(content)
    except:
        # Hata verirse Pre tagı içindekini veya soup ile text'i almayı dene
        try:
            soup = BeautifulSoup(sb.get_page_source(), "html.parser")
            # Genelde JSON verisi 'pre' tagi içinde olur
            if soup.find("pre"):
                text = soup.find("pre").text
                return json.loads(text)
            else:
                return json.loads(soup.text)
        except Exception as e:
            print(f"⚠️ JSON Parse Hatası ({url}): {e}")
            return None

# ================== MAIN ==================

def main():
    if not WISHLIST_URL:
        print("❌ WISHLIST_URL eksik.")
        return

    with SB(uc=True, headless=True, page_load_strategy="eager") as sb:
        print("🚀 Tarayıcı başlatılıyor (Debug Modu)...")
        
        # 1. Wishlist'ten ID'leri çek
        try:
            sb.open(WISHLIST_URL)
            time.sleep(5)
            sb.scroll_to_bottom()
            time.sleep(2)
            
            page_source = sb.get_page_source()
            soup = BeautifulSoup(page_source, "html.parser")
            
            product_ids = set()
            for link in soup.find_all('a', href=True):
                match = re.search(r'-p(\d+)\.html', link['href'])
                if match:
                    product_ids.add(match.group(1))
            
            # Set'i listeye çevir
            product_ids = list(product_ids)
            print(f"📦 Bulunan ID sayısı: {len(product_ids)} -> {product_ids}")
            
        except Exception as e:
            print(f"❌ Wishlist Hatası: {e}")
            return

        found_products = []
        
        # 2. Ürünleri Kontrol Et
        for pid in product_ids:
            print(f"\n🔎 İNCELENİYOR: {pid}")
            api_url = f"https://www.zara.com/itxrest/3/catalog/store/{STORE_ID}/product/{pid}/detail?languageId=-1"
            
            data = get_json_via_browser(sb, api_url)
            
            if not data:
                print("   ❌ API verisi alınamadı (None)")
                continue

            name = data.get("name", "İsimsiz Ürün")
            print(f"   🏷️  Ürün Adı: {name}")

            # --- DETAYLI DEBUG KISMI ---
            # Varyantları gezip ne görüyoruz yazdıralım
            colors = data.get("detail", {}).get("colors", [])
            if not colors:
                 print("   ⚠️ Renk/Varyant bilgisi boş!")

            sku_found = False
            for bundle in colors:
                for size in bundle.get("sizes", []):
                    s_name = size.get("name")
                    avail = size.get("availability")
                    
                    # Loglara her şeyi yaz (Debug için kritik)
                    print(f"   👉 Beden: {s_name:<4} | Durum: {avail}")
                    
                    if s_name in TARGET_SIZES and avail in ["in_stock", "low_on_stock"]:
                        sku_found = True
                        found_products.append(f"👗 {name}\nBeden: {s_name} ({avail})\nLink: https://www.zara.com/tr/tr/-p{pid}.html")
            
            if sku_found:
                print("   ✅ STOK TESPİT EDİLDİ!")
            else:
                print("   ❌ İstenen bedenlerde stok yok.")

            time.sleep(2)

        # 3. Sonuç Bildirimi
        if found_products:
            # Aynı üründen birden fazla beden varsa mesajı birleştir
            subject = "🚨 ZARA STOK BULUNDU"
            body = "\n\n".join(found_products)
            send_email(subject, body)
        else:
            print("\n🏁 Tarama bitti, mail atılacak ürün yok.")

if __name__ == "__main__":
    main()
