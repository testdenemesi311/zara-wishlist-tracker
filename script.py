import os
import json
import time
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ENV
load_dotenv()

WISHLIST_URL = os.getenv("WISHLIST_URL")

EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")

TARGET_SIZES = ["XS", "S"]
STATE_FILE = "state.json"


def send_email(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = TO_EMAIL

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def check_wishlist():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(WISHLIST_URL)

    wait = WebDriverWait(driver, 30)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.wishlist-item")))

    wishlist_items = driver.find_elements(By.CSS_SELECTOR, "li.wishlist-item")
    results = []

    for item in wishlist_items:
        # Ürün adı
        try:
            name = item.find_element(
                By.CSS_SELECTOR,
                "span[data-qa-qualifier='product-detail-secondary-product-info-name']"
            ).text.strip()
        except:
            continue

        # Ekle / Tükendi
        try:
            button = item.find_element(
                By.CSS_SELECTOR,
                "button[data-qa-id='show-size-selector']"
            )
        except:
            results.append((name, []))
            continue

        if button.get_attribute("disabled"):
            results.append((name, []))
            continue

        # Bedenleri aç
        driver.execute_script("arguments[0].click();", button)
        time.sleep(1)

        found_sizes = []

        sizes = item.find_elements(
            By.CSS_SELECTOR,
            "li.size-selector-sizes__size.size-selector-sizes-size--enabled"
        )

        for s in sizes:
            label = s.find_element(
                By.CSS_SELECTOR,
                ".size-selector-sizes-size__label"
            ).text.strip()

            if label in TARGET_SIZES:
                found_sizes.append(label)

        results.append((name, found_sizes))

    driver.quit()
    return results


if __name__ == "__main__":
    previous_state = load_state()
    current_state = {}
    mail_lines = []

    results = check_wishlist()

    for name, sizes in results:
        has_stock = len(sizes) > 0
        current_state[name] = has_stock

        # İlk kez stok geldiyse
        if has_stock and not previous_state.get(name, False):
            mail_lines.append(f"✅ {name} → {', '.join(sizes)}")

    save_state(current_state)

    if mail_lines:
        send_email(
            "🎉 Zara Wishlist – XS / S Stok Geldi!",
            "Aşağıdaki ürünlerde XS veya S stok geldi:\n\n"
            + "\n".join(mail_lines)
            + "\n\nLink:\n"
            + WISHLIST_URL
        )

