import os
import telebot
from supabase import create_client, Client
from flask import Flask
import threading

# خواندن کلیدها از متغیرهای محیطی برای امنیت کامل
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ساخت یک سرور مجازی برای بیدار نگه داشتن رندر
app = Flask(__name__)

@app.route('/')
def index():
    return "ربات دیوان بخت‌زاده فعال است و سرور بیدار است."

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "سلام جناب بخت‌زاده عزیز؛ به دیوان دیجیتال خود خوش آمدید. 🌷")

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    # اجرای همزمان ربات پیام‌رسان و سرور بیدارباش
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
