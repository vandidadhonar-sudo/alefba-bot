import os
import telebot
from telebot import apihelper
from supabase import create_client, Client
from flask import Flask
import threading

# تغییر مسیر حیاتی: اتصال به سرورهای پیام‌رسان بله به جای تلگرام برای رفع خطای 401
apihelper.API_URL = "https://tapi.bale.ai/bot{0}/{1}"

# خواندن امن کلیدها از متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# راه‌اندازی ربات و دیتابیس
bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ساخت یک سرور مجازی (Flask) برای جلوگیری از به خواب رفتن سرور رایگان رندر
app = Flask(__name__)

@app.route('/')
def index():
    return "ربات دیوان بخت‌زاده با موفقیت به پیام‌رسان بله متصل شد و فعال است."

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "سلام جناب بخت‌زاده عزیز؛ به دیوان دیجیتال خود خوش آمدید. 🌷")

def run_bot():
    # استفاده از skip_pending برای جلوگیری از کرش کردن ربات به دلیل پیام‌های انباشته شده قدیمی
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    # اجرای همزمان و بدون تداخلِ ربات پیام‌رسان و سرور بیدارباش
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
