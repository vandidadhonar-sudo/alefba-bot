import os
import telebot
from telebot import apihelper
from flask import Flask
import threading
import time

# تنظیم دقیق سرور بله
apihelper.API_URL = "https://tapi.bale.ai/bot{0}/{1}"

# متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

@app.route('/')
def index():
    return "سرور بیدارباشِ ربات فعال است."

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "سلام جناب بخت‌زاده عزیز؛ به دیوان دیجیتال خود خوش آمدید. 🌷")

def run_bot():
    # ساختار یکپارچه و ضد کرش برای سرور بله (حذف skip_pending)
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Connection error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
