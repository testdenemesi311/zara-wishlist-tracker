import os
import re
import json
import requests
import smtplib
from email.mime.text import MIMEText

# ================== AYARLAR ==================

WISHLIST_URL = os.getenv("WISHLIST_URL")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")

STORE_ID = "11766"  # Türkiye
TARGET_SIZES = ["XS", "S", "M", "L"]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/html"
}

# ================== MAIL ==================

def send_email(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = TO_EMAIL

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.send_message(msg)

# ================== WISHLIST ==================

def get_product_ids():
    html = requests.get(WISHLIST_URL, headers=HEADERS).text
    ids = set(re.findall(r'"productId":(\d+)', html))
    return list(ids)

# ================== SKU → BEDEN MAP ==================

def get_sku_size_map(product_id):
    url = f"https://www.zara.com/tr/tr/products-details/{product_id}.json"
    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        return {}

    data = r.json()
    sku_map = {}

    for color in data.get("colors", []):
        for size in color.get("sizes", []):
            sku = size.get("sku")
            name = size.get("name")
            if sku and name:
                sku_map[sku] = name

    return sku_map

# ================== STOK KONTROL ==================

def check_stock(product_id):
    sku_map = get_sku_size_map(product_id)
    if not sku_map:
        return []

    url = f"https://www.zara.com/itxrest/1/catalog/store/{STORE_ID}/product/id/{product_id}/availability"
    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        return []

    data = r.json()
    found_sizes = []

    for item in data.get("skusAvailability", []):
        sku = item.get("sku")
        availability = item.get("availability")

        size = sku_map.get(sku)
        if (
            size in TARGET_SIZES
            and availability in ["in_stock", "low_on_stock"]
        ):
            found_sizes.append(size)

    return sorted(set(found_sizes))

# ================== MAIN ==================

def main():
    product_ids = get_product_ids()
    available_products = []

    for pid in product_ids:
        sizes = check_stock(pid)
        if sizes:
            link = f"https://www.zara.com/tr/tr/-p{pid}.html"
            available_products.append((pid, sizes, link))

    size_text = " / ".join(TARGET_SIZES)

    if available_products:
        subject = f"✅ Zara Stok Geldi: {size_text}"
        body = "Stok bulunan ürünler:\n\n"
        for pid, sizes, link in available_products:
            body += f"- {pid} → {', '.join(sizes)}\n{link}\n\n"
    else:
        subject = f"❌ Zara Stok Yok: {size_text}"
        body = "Şu an hedef bedenlerde stok yok.\n"

    send_email(subject, body)

# ================== RUN ==================

if __name__ == "__main__":
    main()
