import os
import threading

import telebot
from supabase import create_client, Client
from flask import Flask

# ==========================
# Environment Variables
# ==========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================
# Flask App
# ==========================
app = Flask(__name__)

@app.route("/")
def home():
    return "ربات دیوان بخت‌زاده فعال است."

# ==========================
# Bale Bot Commands
# ==========================
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "سلام جناب بخت‌زاده عزیز؛ به دیوان دیجیتال خود خوش آمدید. 🌷"
    )

# ==========================
# Run Bot
# ==========================
def run_bot():
    bot.infinity_polling(skip_pending=True)

# اجرای ربات فقط یکبار هنگام بالا آمدن Gunicorn
thread = threading.Thread(target=run_bot, daemon=True)
thread.start()
