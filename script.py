import os
import re
import requests
import smtplib
from email.mime.text import MIMEText

WISHLIST_URL = os.getenv("WISHLIST_URL")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

TARGET_SIZES = ["XS", "S","M","L"]


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = TO_EMAIL

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.send_message(msg)


def get_product_links():
    html = requests.get(WISHLIST_URL, headers=HEADERS).text

    links = set(
        re.findall(r'https://www\.zara\.com/tr/tr/[^"]+-p\d+\.html', html)
    )

    return list(links)


def check_product(url):
    html = requests.get(url, headers=HEADERS).text

    # Ürün adı
    name_match = re.search(
        r'data-qa-qualifier="product-detail-secondary-product-info-name">(.*?)<',
        html
    )
    product_name = name_match.group(1).strip() if name_match else "Ürün adı bulunamadı"

    found_sizes = []

    # availability bloklarını tek tek yakala
    blocks = re.findall(r'\{[^{}]*"availability":"[^"]+"[^{}]*\}', html)

    for block in blocks:
        size_match = re.search(r'"name":"(XS|S|M|L|XL)"', block)
        avail_match = re.search(r'"availability":"(in_stock|low_on_stock)"', block)

        if size_match and avail_match:
            size = size_match.group(1)
            if size in TARGET_SIZES:
                found_sizes.append(size)

    return product_name, list(set(found_sizes))

def main():
    product_links = get_product_links()
    results = []

    for link in product_links:
        name, sizes = check_product(link)
        results.append((name, sizes, link))

    available = [r for r in results if r[1]]

    size_text = " / ".join(TARGET_SIZES)

    if available:
        subject = f"✅ Zara Wishlist: {size_text} Stokta"
        body = "Stok bulunan ürünler:\n\n"

        for name, sizes, link in available:
            body += f"- {name} → {', '.join(sizes)}\n{link}\n\n"
    else:
        subject = f"❌ Zara Wishlist: {size_text} Yok"
        body = f"Şu anda {size_text} beden stokta değil.\n\nKontrol edilen ürünler:\n"

        for name, _, link in results:
            body += f"- {name}\n{link}\n"

    send_email(subject, body)

if __name__ == "__main__":
    main()




