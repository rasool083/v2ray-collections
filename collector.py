import requests
import base64
import logging
from urllib.parse import urlparse, parse_qs
import re

# --- تنظیمات اولیه اسکریپت ---
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
SOURCES_FILE = "sources.txt"
OUTPUT_FILE = "filtered_configs_v2.txt" # نام فایل خروجی جدید
REQUEST_TIMEOUT = 20

def decode_base64_content(encoded_content: str) -> str:
    """محتوای Base64 را با مدیریت خطای padding دیکود می‌کند."""
    try:
        padded_content = encoded_content + '=' * (-len(encoded_content) % 4)
        return base64.b64decode(padded_content).decode('utf-8')
    except Exception:
        return ""

def get_configs_from_sources(source_files: list) -> set:
    """کانفیگ‌ها را از لیستی از URLها دریافت و یک مجموعه (set) از کانفیگ‌های منحصر به فرد برمی‌گرداند."""
    all_configs = set()
    for url in source_files:
        try:
            logging.info(f"در حال دریافت از منبع: {url[:70]}...")
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            content = response.text
            
            if "vmess://" not in content and "vless://" not in content:
                content = decode_base64_content(content)
            
            # استفاده از findall برای استخراج تمام کانفیگ‌ها، حتی اگر به هم چسبیده باشند
            found = re.findall(r'(vless|vmess)://[^\s\'"<>]+', content)
            for config in found:
                all_configs.add(config)
        except requests.RequestException as e:
            logging.error(f"خطا در دریافت اطلاعات از {url}: {e}")
    return all_configs

def score_and_filter_config(config: str) -> int:
    """
    به هر کانفیگ بر اساس کیفیت آن امتیازی می‌دهد. امتیاز 0 به معنی رد شدن است.
    """
    try:
        if not config.startswith("vless://"):
            return 0 # فقط VLESS را می‌پذیریم

        parsed_url = urlparse(config)
        params = parse_qs(parsed_url.query)
        
        # --- بررسی‌های اصلی برای رد کردن کانفیگ ---
        if params.get('security', [''])[0] != 'tls':
            return 0
        
        transport = params.get('type', [''])[0]
        if transport not in ['ws', 'grpc']:
            return 0

        # برای gRPC، باید serviceName وجود داشته باشد
        if transport == 'grpc' and not params.get('serviceName', [''])[0]:
            return 0
            
        # برای ws، باید host وجود داشته باشد
        if transport == 'ws' and not params.get('host', [''])[0]:
            return 0

        # --- شروع امتیازدهی ---
        score = 10 # امتیاز پایه برای پاس کردن فیلترهای اولیه

        # امتیاز برای استفاده از پورت استاندارد
        if parsed_url.port == 443:
            score += 10

        # امتیاز برای استفاده از دامنه تمیز (نه IP یا DDNS)
        hostname = parsed_url.hostname
        if hostname and not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', hostname):
            if not any(ddns in hostname for ddns in ['.ddns.net', '.xyz', '.pw']):
                score += 20
        
        # امتیاز برای داشتن SNI مناسب
        if params.get('sni') or params.get('host'):
             score += 5

        return score
        
    except Exception:
        return 0

def main():
    """تابع اصلی برای اجرای کل فرآیند."""
    try:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            sources = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"فایل منابع '{SOURCES_FILE}' یافت نشد.")
        return

    logging.info(f"شروع جمع‌آوری از {len(sources)} منبع...")
    unique_configs = get_configs_from_sources(sources)
    logging.info(f"مجموعاً {len(unique_configs)} کانفیگ منحصر به فرد یافت شد.")

    logging.info("شروع فرآیند امتیازدهی و فیلتر پیشرفته...")
    
    scored_configs = []
    for config in unique_configs:
        score = score_and_filter_config(config)
        if score > 0:
            # یک دیکشنری برای حذف کانفیگ‌های با UUID و آدرس یکسان (سرورهای انبوه)
            # ما فقط بهترین امتیاز هر سرور را نگه می‌داریم
            server_id = config.split('@')[0]
            scored_configs.append({'id': server_id, 'score': score, 'config': config})

    # مرتب‌سازی بر اساس امتیاز (بیشترین به کمترین)
    scored_configs.sort(key=lambda x: x['score'], reverse=True)
    
    # حذف سرورهای تکراری و نگه داشتن بهترین امتیاز
    final_configs = []
    seen_ids = set()
    for item in scored_configs:
        if item['id'] not in seen_ids:
            final_configs.append(item['config'])
            seen_ids.add(item['id'])

    logging.info(f"پس از فیلتر پیشرفته، {len(final_configs)} کانفیگ با کیفیت بالا باقی ماند.")

    if final_configs:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(final_configs))
        logging.info(f"لیست نهایی در فایل '{OUTPUT_FILE}' ذخیره شد. این لیست بسیار با کیفیت‌تر است.")
    else:
        logging.warning("هیچ کانفیگی از فیلترهای پیشرفته عبور نکرد.")

if __name__ == "__main__":
    main()
    
