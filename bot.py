import os
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import time

# تنظیم مسیر سرور بله
apihelper.API_URL = "https://tapi.bale.ai/bot{0}/{1}"

# خواندن کلیدهای امنیتی
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# تابع ساخت دکمه‌های شیشه‌ای
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    btn1 = InlineKeyboardButton("📝 ارسال شعر جدید", callback_data="send_poem")
    btn2 = InlineKeyboardButton("🎙 ارسال دکلمه (صوت)", callback_data="send_voice")
    btn3 = InlineKeyboardButton("🖼 ارسال خطاطی (عکس)", callback_data="send_image")
    markup.add(btn1, btn2, btn3)
    return markup

# واکنش به دستور /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "سلام جناب بخت‌زاده عزیز؛ به دیوان دیجیتال خود خوش آمدید. 🌷\n\n"
        "لطفاً برای ثبت آثار، یکی از گزینه‌های زیر را انتخاب کنید:"
    )
    bot.reply_to(message, welcome_text, reply_markup=main_menu())

# هندل کردن کلیک روی دکمه‌های شیشه‌ای
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "send_poem":
        bot.send_message(call.message.chat.id, "لطفاً متن شعر خود را اینجا تایپ کنید یا بفرستید:")
    elif call.data == "send_voice":
        bot.send_message(call.message.chat.id, "لطفاً فایل صوتی دکلمه را ارسال کنید:")
    elif call.data == "send_image":
        bot.send_message(call.message.chat.id, "لطفاً عکس خطاطی یا دست‌نوشته را بفرستید:")
    
    # پایان دادن به حالت لودینگ (چرخیدن) دکمه در پیام‌رسان بله
    bot.answer_callback_query(call.id)

def run_bot():
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

# اجرای هسته ربات
threading.Thread(target=run_bot, daemon=True).start()

@app.route('/')
def index():
    return "سرور بیدارباشِ ربات به همراه منوی تعاملی فعال است."

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
