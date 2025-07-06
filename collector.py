import requests
import base64
import logging
from urllib.parse import urlparse, parse_qs

# --- تنظیمات اولیه اسکریپت ---
# تنظیمات لاگ‌گیری برای نمایش مراحل اجرا در ترمینال
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# نام فایل ورودی که حاوی لینک منابع است
SOURCES_FILE = "sources.txt"
# نام فایل خروجی که کانفیگ‌های فیلتر شده در آن ذخیره می‌شوند
OUTPUT_FILE = "filtered_configs.txt"
# زمان انتظار برای هر درخواست (به ثانیه)
REQUEST_TIMEOUT = 15

def decode_base64_content(encoded_content: str) -> str:
    """
    محتوای Base64 را با مدیریت خطای padding دیکود می‌کند.
    """
    try:
        # افزودن padding صحیح برای جلوگیری از خطای base64.b64decode
        padded_content = encoded_content + '=' * (-len(encoded_content) % 4)
        return base64.b64decode(padded_content).decode('utf-8')
    except (base64.binascii.Error, UnicodeDecodeError) as e:
        logging.warning(f"خطا در دیکود کردن محتوای Base64: {e}")
        return ""

def get_configs_from_source(url: str) -> list[str]:
    """
    کانفیگ‌ها را از یک لینک اشتراک (URL) دریافت می‌کند.
    این تابع هم لینک‌های حاوی متن خام و هم لینک‌های Base64 را مدیریت می‌کند.
    """
    try:
        logging.info(f"در حال دریافت از منبع: {url[:70]}...")
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        # اگر درخواست ناموفق بود (مثلاً خطای 404)، یک استثنا ایجاد می‌کند
        response.raise_for_status()
        
        content = response.text
        
        # تشخیص خودکار: اگر محتوا شبیه به لینک کانفیگ نیست، احتمالاً Base64 است.
        if "vmess://" not in content and "vless://" not in content:
            logging.info("محتوا به نظر Base64 می‌رسد. در حال دیکود کردن...")
            content = decode_base64_content(content)
        
        # جداسازی کانفیگ‌ها بر اساس خط جدید و حذف خطوط خالی
        return [line.strip() for line in content.splitlines() if line.strip()]
    except requests.RequestException as e:
        logging.error(f"خطا در دریافت اطلاعات از {url}: {e}")
        return []

def intelligent_filter(config: str) -> bool:
    """
    یک فیلتر هوشمند برای جداسازی کانفیگ‌های با شانس موفقیت بالا.
    فقط کانفیگ‌های VLESS که از WS یا gRPC با امنیت TLS استفاده می‌کنند را عبور می‌دهد.
    """
    # 1. فقط پروتکل VLESS را می‌پذیریم
    if not config.startswith("vless://"):
        return False
    
    try:
        # 2. تجزیه URL برای دسترسی به پارامترها
        parsed_url = urlparse(config)
        params = parse_qs(parsed_url.query)

        # 3. فیلتر نوع Transport: فقط ws یا grpc
        transport_type = params.get('type', ['tcp'])[0]
        if transport_type not in ['ws', 'grpc']:
            return False
            
        # 4. فیلتر امنیت: فقط tls
        security = params.get('security', ['none'])[0]
        if security != 'tls':
            return False
            
        # اگر تمام شرایط برقرار بود، کانفیگ معتبر است
        return True
    except Exception as e:
        # در صورت وجود هرگونه خطا در تجزیه کانفیگ، آن را نامعتبر می‌دانیم
        logging.warning(f"خطا در تجزیه کانفیگ و رد آن: {config[:40]}... | خطا: {e}")
        return False

def main():
    """
    تابع اصلی برای اجرای کل فرآیند جمع‌آوری و فیلتر کردن.
    """
    all_configs = []
    
    try:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            # خواندن منابع از فایل و حذف خطوط خالی
            sources = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"فایل منابع '{SOURCES_FILE}' یافت نشد. لطفاً آن را ایجاد کنید.")
        return

    logging.info(f"تعداد {len(sources)} منبع برای پردازش یافت شد.")

    for source_url in sources:
        configs = get_configs_from_source(source_url)
        all_configs.extend(configs)

    logging.info(f"مجموعاً {len(all_configs)} کانفیگ از تمام منابع جمع‌آوری شد.")
    
    # حذف کانفیگ‌های تکراری با حفظ ترتیب
    unique_configs = list(dict.fromkeys(all_configs))
    logging.info(f"تعداد {len(unique_configs)} کانفیگ منحصر به فرد یافت شد.")

    # اعمال فیلتر هوشمند روی کانفیگ‌های منحصر به فرد
    logging.info("در حال اعمال فیلتر هوشمند برای جداسازی بهترین کانفیگ‌ها...")
    filtered_list = [cfg for cfg in unique_configs if intelligent_filter(cfg)]
    logging.info(f"پس از فیلتر، تعداد {len(filtered_list)} کانفیگ با پتانسیل بالا باقی ماند.")

    # ذخیره لیست نهایی در فایل خروجی
    if filtered_list:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(filtered_list))
        logging.info(f"لیست نهایی در فایل '{OUTPUT_FILE}' ذخیره شد. این لیست آماده تست دستی است.")
    else:
        logging.warning("هیچ کانفیگی از فیلترها عبور نکرد. فایل خروجی ایجاد نشد.")

if __name__ == "__main__":
    main()
  
