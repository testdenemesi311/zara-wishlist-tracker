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

    name_match = re.search(
        r'data-qa-qualifier="product-detail-secondary-product-info-name">(.*?)<',
        html
    )
    product_name = name_match.group(1).strip() if name_match else "Ürün adı bulunamadı"

    size_pattern = r'\{"availability":"(.*?)".*?"name":"(XS|S|M|L|XL)"'
    matches = re.findall(size_pattern, html)

    found_sizes = []

    for availability, size in matches:
        if size in TARGET_SIZES and availability in ["low_on_stock", "in_stock"]:
            found_sizes.append(size)

    return product_name, found_sizes


def main():
    product_links = get_product_links()

    results = []

    for link in product_links:
        name, sizes = check_product(link)
        results.append((name, sizes, link))

    available = [r for r in results if r[1]]

    if available:
        subject = "✅ Zara Wishlist: XS / S StOKTA"
        body = "Stok bulunan ürünler:\n\n"
        for name, sizes, link in available:
            body += f"- {name} → {', '.join(sizes)}\n{link}\n\n"
    else:
        subject = "❌ Zara Wishlist: XS / S YOK"
        body = "Şu anda XS veya S stokta değil.\n\nKontrol edilen ürünler:\n"
        for name, _, link in results:
            body += f"- {name}\n{link}\n"

    send_email(subject, body)


if __name__ == "__main__":
    main()

