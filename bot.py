import os
import io
import time
import uuid
import threading

import requests
import telebot
from telebot import apihelper, types
from flask import Flask
import jdatetime
from PIL import Image, ImageOps
from supabase import create_client

# ---------------------------------------------------------------------------
#  پیکربندی پایه
# ---------------------------------------------------------------------------
# مسیر سرور پیام‌رسان بله
apihelper.API_URL = "https://tapi.bale.ai/bot{0}/{1}"

BOT_TOKEN     = os.getenv("BOT_TOKEN")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")


def _clean_supabase_url(raw):
    """کتابخانه فقط به آدرس پایه نیاز دارد؛ اگر کسی اشتباهاً /rest/v1 را هم
    اضافه کرده باشد، اینجا پاک می‌شود تا مسیر دوبار تکرار نشود."""
    url = (raw or "").strip().rstrip("/")
    for suffix in ("/rest/v1", "/rest"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


SUPABASE_URL = _clean_supabase_url(os.getenv("SUPABASE_URL"))
# رمزها فقط از متغیرهای محیطی رندر خوانده می‌شوند (در کد ذخیره نمی‌شوند)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
POET_PASSWORD  = os.getenv("POET_PASSWORD")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------------
#  برچسب دکمه‌ها (کیبورد بزرگ پایین صفحه)
# ---------------------------------------------------------------------------
BTN_POEM   = "✍️ ارسال شعر جدید"
BTN_VOICE  = "🎤 ارسال دکلمه (صدا)"
BTN_IMAGE  = "🖼 ارسال خطاطی"
BTN_HELP   = "❓ راهنما"
BTN_HOME   = "🏠 بازگشت به منو"

BTN_ADMIN_RECENT = "📋 آثار اخیر"
BTN_ADMIN_SEARCH = "🔍 جستجو"

PEN_ALEFBA = "الف ب"
PEN_SABA   = "صبا"
PEN_OTHER  = "✏️ نام دیگر"

CATEGORIES = ["غزلیات", "دوبیتی و رباعی", "مثنوی", "قطعات و اشعار کوتاه"]

BTN_CONFIRM = "✅ تأیید و انتشار"
BTN_EDIT    = "✏️ ویرایش"
BTN_RESTART = "🔄 از نو"

BTN_READ   = "🎙 خواندنِ شعر با صدا"
READ_OK    = "✅ بله، درست است"
READ_REDO  = "🔁 دوباره می‌خوانم"
VOICE_YES  = "✅ بله، صدای من هم باشد"
VOICE_NO   = "❌ فقط متنِ شعر"

EDIT_TEXT  = "✏️ متن شعر"
EDIT_TITLE = "✏️ عنوان"
EDIT_PEN   = "✏️ تخلص"
EDIT_DATE  = "✏️ زمان سرایش"
EDIT_CAT   = "✏️ دفتر"
EDIT_BACK  = "↩️ بازگشت به پیش‌نمایش"
DATE_UNKNOWN = "نامشخص"

# وضعیت گفت‌وگوی هر کاربر (در حافظه)
STATE = {}
# کش نقش کاربران برای اینکه هر بار از دیتابیس پرسیده نشود
_role_cache = {}

# ---------------------------------------------------------------------------
#  توابع کمکی نقش/دسترسی
# ---------------------------------------------------------------------------
def get_role(chat_id):
    """نقش کاربر را برمی‌گرداند: 'admin' | 'poet' | None"""
    if chat_id in _role_cache:
        return _role_cache[chat_id]
    try:
        res = supabase.table("allowed_users").select("role").eq("chat_id", chat_id).limit(1).execute()
        if res.data:
            _role_cache[chat_id] = res.data[0]["role"]
            return _role_cache[chat_id]
    except Exception as e:
        print("get_role error:", e)
    return None


def set_role(chat_id, role):
    """کاربر را برای همیشه مجاز می‌کند (یک‌بار ورود رمز)"""
    try:
        supabase.table("allowed_users").upsert({"chat_id": chat_id, "role": role}).execute()
    except Exception as e:
        print("set_role error:", e)
    _role_cache[chat_id] = role


# ---------------------------------------------------------------------------
#  کیبوردها
# ---------------------------------------------------------------------------
def main_keyboard(role):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(BTN_READ)
    kb.row(BTN_POEM)
    kb.row(BTN_VOICE)
    kb.row(BTN_IMAGE)
    if role == "admin":
        kb.row(BTN_ADMIN_RECENT)
        kb.row(BTN_ADMIN_SEARCH)
    kb.row(BTN_HELP)
    return kb


def back_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(BTN_HOME)
    return kb


def pen_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(PEN_ALEFBA)
    kb.row(PEN_SABA)
    kb.row(PEN_OTHER)
    kb.row(BTN_HOME)
    return kb


def date_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(DATE_UNKNOWN)
    kb.row(BTN_HOME)
    return kb


def category_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for c in CATEGORIES:
        kb.row(c)
    kb.row(BTN_HOME)
    return kb


def confirm_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(BTN_CONFIRM)
    kb.row(BTN_EDIT)
    kb.row(BTN_RESTART)
    kb.row(BTN_HOME)
    return kb


def edit_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(EDIT_TEXT)
    kb.row(EDIT_TITLE)
    kb.row(EDIT_PEN)
    kb.row(EDIT_DATE)
    kb.row(EDIT_CAT)
    kb.row(EDIT_BACK)
    kb.row(BTN_HOME)
    return kb


# ---------------------------------------------------------------------------
#  پیام‌های خوش‌آمد و راهنما
# ---------------------------------------------------------------------------
def send_welcome(chat_id, role):
    if role == "admin":
        txt = ("سلام جناب مدیر 👑\n"
               "به پنل مدیریت دیوان خوش آمدید. یکی از گزینه‌های زیر را انتخاب کنید:")
    else:
        txt = ("سلام جناب بخت‌زاده عزیز؛ به دیوان دیجیتال خود خوش آمدید. 🌷\n"
               "برای ثبت آثار، یکی از گزینه‌های زیر را انتخاب کنید:")
    bot.send_message(chat_id, txt, reply_markup=main_keyboard(role))


def send_help(chat_id, role):
    txt = ("📖 راهنمای ساده:\n\n"
           "• برای ثبت شعر، دکمهٔ «✍️ ارسال شعر جدید» را بزنید.\n"
           "• سپس مرحله‌به‌مرحله متن، عنوان، تخلص، زمان سرایش و دفتر پرسیده می‌شود.\n"
           "• در پایان یک پیش‌نمایش کامل می‌بینید؛ اگر درست بود «✅ تأیید و انتشار» را بزنید.\n"
           "• اگر جایی اشتباه تایپی بود، «✏️ ویرایش» را بزنید تا همان بخش را اصلاح کنید.\n"
           "• هر زمان خواستید از اول شروع کنید، «🏠 بازگشت به منو» را بزنید.")
    bot.send_message(chat_id, txt, reply_markup=main_keyboard(role))


# ---------------------------------------------------------------------------
#  ویزارد ثبت شعر
# ---------------------------------------------------------------------------
def start_poem_wizard(chat_id):
    STATE[chat_id] = {"step": "poem_text", "data": {"type": "poem", "author": PEN_ALEFBA}}
    bot.send_message(
        chat_id,
        "✍️ جناب بخت‌زاده عزیز، لطفاً متن شعر خود را بنویسید یا ارسال کنید:",
        reply_markup=back_keyboard(),
    )


def ask_date(chat_id):
    bot.send_message(
        chat_id,
        "🗓 این شعر در چه زمانی سروده شده است؟\n"
        "می‌توانید به عدد یا به حروف بنویسید؛ برای نمونه: «۱۳۵۲»، «بیست سال پیش»، «ماه گذشته».\n"
        "اگر زمان دقیق را به یاد ندارید، دکمهٔ «نامشخص» را بزنید.",
        reply_markup=date_keyboard(),
    )


def show_preview(chat_id, data):
    preview = (
        "📜 پیش‌نمایش اثر شما:\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"«{data.get('title') or '—'}»\n\n"
        f"{data.get('content') or ''}\n\n"
        f"— {data.get('author') or PEN_ALEFBA}\n"
        f"🗓 زمان سرایش: {data.get('composed_at_text') or '—'}\n"
        f"📚 دفتر: {data.get('category') or '—'}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "اگر همه‌چیز درست است، «✅ تأیید و انتشار» را بزنید.\n"
        "برای اصلاح غلط تایپی، «✏️ ویرایش» را بزنید."
    )
    bot.send_message(chat_id, preview, reply_markup=confirm_keyboard())


def publish_poem(chat_id, data, role):
    is_edit = bool(data.get("edit_id"))
    record = {
        "type":     data.get("type", "poem"),
        "title":    data.get("title"),
        "content":  data.get("content"),
        "author":   data.get("author") or PEN_ALEFBA,
        "category": data.get("category"),
        "composed_at_text": data.get("composed_at_text"),
        "status":   "published",
    }
    if data.get("audio_url"):
        record["audio_url"] = data["audio_url"]
    try:
        if is_edit:
            supabase.table("artworks").update(record).eq("id", data["edit_id"]).execute()
        else:
            record["persian_date"] = jdatetime.date.today().strftime("%Y/%m/%d")
            record["submitted_by_chat_id"] = chat_id
            supabase.table("artworks").insert(record).execute()
    except Exception as e:
        print("publish error:", e)
        bot.send_message(
            chat_id,
            "متأسفانه در ثبت اثر خطایی رخ داد. لطفاً کمی بعد دوباره تلاش کنید.",
            reply_markup=main_keyboard(role),
        )
        return

    STATE.pop(chat_id, None)
    if is_edit:
        msg = "✅ اصلاحات با موفقیت ذخیره شد."
    else:
        msg = "✅ اثر شما با موفقیت در دیوان ثبت و منتشر شد. سپاس از شما جناب بخت‌زاده. 🌹"
    bot.send_message(chat_id, msg, reply_markup=main_keyboard(role))

    if not is_edit and role == "poet":
        notify_admins(data)


def notify_admins(data):
    """به مدیر(ها) خبر می‌دهد که اثر تازه‌ای منتشر شده است."""
    try:
        res = supabase.table("allowed_users").select("chat_id").eq("role", "admin").execute()
        for row in res.data or []:
            try:
                bot.send_message(
                    row["chat_id"],
                    f"🔔 اثر جدیدی منتشر شد:\n«{data.get('title') or '—'}» — {data.get('author') or '—'}",
                )
            except Exception:
                pass
    except Exception as e:
        print("notify_admins error:", e)


def handle_poem_wizard(chat_id, text, st, role):
    step = st["step"]
    data = st["data"]

    if step == "poem_text":
        data["content"] = text
        st["step"] = "poem_title"
        bot.send_message(
            chat_id,
            "بسیار زیبا 🌸\nاکنون «عنوان یا سرآغاز» شعر را بنویسید.\n(اگر عنوانی ندارد، بنویسید: بدون عنوان)",
            reply_markup=back_keyboard(),
        )

    elif step == "poem_title":
        data["title"] = text
        st["step"] = "poem_pen"
        bot.send_message(chat_id, "تخلص پای این شعر چه باشد؟", reply_markup=pen_keyboard())

    elif step == "poem_pen":
        if text == PEN_OTHER:
            st["step"] = "poem_pen_custom"
            bot.send_message(chat_id, "نام سرایندهٔ این اثر را بنویسید:", reply_markup=back_keyboard())
            return
        data["author"] = text
        st["step"] = "poem_date"
        ask_date(chat_id)

    elif step == "poem_pen_custom":
        data["author"] = text
        st["step"] = "poem_date"
        ask_date(chat_id)

    elif step == "poem_date":
        data["composed_at_text"] = text
        st["step"] = "poem_category"
        bot.send_message(chat_id, "این شعر در کدام دفتر قرار گیرد؟", reply_markup=category_keyboard())

    elif step == "poem_category":
        if text not in CATEGORIES:
            bot.send_message(chat_id, "لطفاً یکی از دفترهای زیر را انتخاب کنید:", reply_markup=category_keyboard())
            return
        data["category"] = text
        st["step"] = "poem_preview"
        show_preview(chat_id, data)

    elif step == "poem_preview":
        if text == BTN_CONFIRM:
            if data.get("audio_url"):
                st["step"] = "poem_ask_voice"
                bot.send_message(chat_id, "صدای خوانشِ شما هم زیرِ شعر در سایت منتشر شود؟", reply_markup=ask_voice_keyboard())
            else:
                publish_poem(chat_id, data, role)
        elif text == BTN_EDIT:
            st["step"] = "poem_edit_menu"
            bot.send_message(chat_id, "کدام بخش را می‌خواهید اصلاح کنید؟", reply_markup=edit_keyboard())
        elif text == BTN_RESTART:
            start_poem_wizard(chat_id)
        else:
            show_preview(chat_id, data)

    elif step == "poem_ask_voice":
        if text == VOICE_YES:
            publish_poem(chat_id, data, role)
        elif text == VOICE_NO:
            data.pop("audio_url", None)
            publish_poem(chat_id, data, role)
        else:
            bot.send_message(chat_id, "یکی از گزینه‌ها را انتخاب کنید:", reply_markup=ask_voice_keyboard())

    elif step == "poem_edit_menu":
        if text == EDIT_BACK:
            st["step"] = "poem_preview"
            show_preview(chat_id, data)
        elif text == EDIT_TEXT:
            st["step"] = "edit_field_text"
            bot.send_message(chat_id, "متن جدید شعر را بنویسید:", reply_markup=back_keyboard())
        elif text == EDIT_TITLE:
            st["step"] = "edit_field_title"
            bot.send_message(chat_id, "عنوان جدید را بنویسید:", reply_markup=back_keyboard())
        elif text == EDIT_PEN:
            st["step"] = "edit_field_pen"
            bot.send_message(chat_id, "تخلص جدید را انتخاب کنید:", reply_markup=pen_keyboard())
        elif text == EDIT_DATE:
            st["step"] = "edit_field_date"
            ask_date(chat_id)
        elif text == EDIT_CAT:
            st["step"] = "edit_field_cat"
            bot.send_message(chat_id, "دفتر جدید را انتخاب کنید:", reply_markup=category_keyboard())
        else:
            bot.send_message(chat_id, "لطفاً یکی از گزینه‌ها را انتخاب کنید.", reply_markup=edit_keyboard())

    elif step == "edit_field_text":
        data["content"] = text
        st["step"] = "poem_preview"
        show_preview(chat_id, data)

    elif step == "edit_field_title":
        data["title"] = text
        st["step"] = "poem_preview"
        show_preview(chat_id, data)

    elif step == "edit_field_pen":
        if text == PEN_OTHER:
            st["step"] = "edit_field_pen_custom"
            bot.send_message(chat_id, "نام سراینده را بنویسید:", reply_markup=back_keyboard())
            return
        data["author"] = text
        st["step"] = "poem_preview"
        show_preview(chat_id, data)

    elif step == "edit_field_pen_custom":
        data["author"] = text
        st["step"] = "poem_preview"
        show_preview(chat_id, data)

    elif step == "edit_field_date":
        data["composed_at_text"] = text
        st["step"] = "poem_preview"
        show_preview(chat_id, data)

    elif step == "edit_field_cat":
        if text not in CATEGORIES:
            bot.send_message(chat_id, "لطفاً یکی از دفترها را انتخاب کنید:", reply_markup=category_keyboard())
            return
        data["category"] = text
        st["step"] = "poem_preview"
        show_preview(chat_id, data)


# ---------------------------------------------------------------------------
#  پنل مدیر
# ---------------------------------------------------------------------------
def send_admin_item(chat_id, r):
    status_fa = "منتشرشده 🌐" if r.get("status") == "published" else "پیش‌نویس 📝"
    snippet = (r.get("content") or "")[:80]
    txt = (
        f"#{r['id']} — نوع: {r.get('type') or '—'}\n"
        f"«{r.get('title') or '—'}» — {r.get('author') or '—'}\n"
        f"دفتر: {r.get('category') or '—'} | وضعیت: {status_fa}\n"
        f"{snippet}"
    )
    kb = types.InlineKeyboardMarkup()
    if r.get("status") == "published":
        kb.add(types.InlineKeyboardButton("👁 پنهان‌کردن", callback_data=f"unpub:{r['id']}"))
    else:
        kb.add(types.InlineKeyboardButton("🌐 انتشار", callback_data=f"pub:{r['id']}"))
    kb.add(types.InlineKeyboardButton("✏️ ویرایش", callback_data=f"edit:{r['id']}"))
    kb.add(types.InlineKeyboardButton("🗑 حذف", callback_data=f"del:{r['id']}"))
    bot.send_message(chat_id, txt, reply_markup=kb)


def admin_recent(chat_id, role):
    try:
        res = (supabase.table("artworks")
               .select("id,title,author,type,status,category,content")
               .eq("is_deleted", False)
               .order("created_at", desc=True)
               .limit(10).execute())
    except Exception as e:
        print("admin_recent error:", e)
        bot.send_message(chat_id, "خطا در دریافت آثار.", reply_markup=main_keyboard(role))
        return
    rows = res.data or []
    if not rows:
        bot.send_message(chat_id, "هنوز اثری ثبت نشده است.", reply_markup=main_keyboard(role))
        return
    bot.send_message(chat_id, f"📋 {len(rows)} اثر اخیر:", reply_markup=main_keyboard(role))
    for r in rows:
        send_admin_item(chat_id, r)


def admin_do_search(chat_id, term, role):
    STATE.pop(chat_id, None)
    try:
        res = (supabase.table("artworks")
               .select("id,title,author,type,status,category,content")
               .eq("is_deleted", False)
               .or_(f"title.ilike.%{term}%,content.ilike.%{term}%")
               .limit(10).execute())
    except Exception as e:
        print("search error:", e)
        bot.send_message(chat_id, "خطا در جستجو.", reply_markup=main_keyboard(role))
        return
    rows = res.data or []
    if not rows:
        bot.send_message(chat_id, "نتیجه‌ای یافت نشد.", reply_markup=main_keyboard(role))
        return
    bot.send_message(chat_id, f"🔍 {len(rows)} نتیجه یافت شد:", reply_markup=main_keyboard(role))
    for r in rows:
        send_admin_item(chat_id, r)


# ---------------------------------------------------------------------------
#  ورود با رمز
# ---------------------------------------------------------------------------
def handle_password(chat_id, text):
    if ADMIN_PASSWORD and text == ADMIN_PASSWORD:
        set_role(chat_id, "admin")
        STATE.pop(chat_id, None)
        bot.send_message(chat_id, "🔓 خوش آمدید جناب مدیر. دسترسی کامل فعال شد.")
        send_welcome(chat_id, "admin")
    elif POET_PASSWORD and text == POET_PASSWORD:
        set_role(chat_id, "poet")
        STATE.pop(chat_id, None)
        send_welcome(chat_id, "poet")
    else:
        bot.send_message(chat_id, "رمز عبور نادرست است. لطفاً دوباره تلاش کنید:")


# ---------------------------------------------------------------------------
#  هندلرها
# ---------------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def cmd_start(m):
    chat_id = m.chat.id
    role = get_role(chat_id)
    if role:
        STATE.pop(chat_id, None)
        send_welcome(chat_id, role)
    else:
        STATE[chat_id] = {"step": "await_password", "data": {}}
        bot.send_message(
            chat_id,
            "برای ورود، لطفاً رمز عبور خود را وارد کنید:",
            reply_markup=types.ReplyKeyboardRemove(),
        )


# ---------------------------------------------------------------------------
#  بخش رسانه: خطاطی (عکس) و آوا (صدا)
# ---------------------------------------------------------------------------
VOICE_OK = "✅ تأیید صدا"
VOICE_REDO = "🎙 ضبط مجدد"


def media_confirm_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(BTN_CONFIRM)
    kb.row(BTN_RESTART)
    kb.row(BTN_HOME)
    return kb


def voice_review_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(VOICE_OK, VOICE_REDO)
    kb.row(BTN_HOME)
    return kb


def download_bale_file(file_id):
    """فایل را از سرور بله دانلود می‌کند و بایت‌هایش را برمی‌گرداند."""
    info = bot.get_file(file_id)
    url = "https://tapi.bale.ai/file/bot{0}/{1}".format(BOT_TOKEN, info.file_path)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def process_and_upload_image(data_bytes):
    """اصلاح خودکار زاویه (EXIF)، تشخیص افقی/عمودی، بهینه‌سازی WebP و آپلود."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data_bytes))).convert("RGB")
    w, h = img.size
    orientation = "landscape" if w >= h else "portrait"
    maxd = 1600
    if max(w, h) > maxd:
        s = maxd / float(max(w, h))
        img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=85, method=6)
    path = "calligraphy/{0}.webp".format(uuid.uuid4().hex)
    supabase.storage.from_("images").upload(path, buf.getvalue(), {"content-type": "image/webp"})
    return supabase.storage.from_("images").get_public_url(path), orientation


def upload_voice(data_bytes, ext, ctype):
    path = "voice/{0}.{1}".format(uuid.uuid4().hex, ext)
    supabase.storage.from_("audio").upload(path, data_bytes, {"content-type": ctype})
    return supabase.storage.from_("audio").get_public_url(path)


def start_image_wizard(chat_id):
    STATE[chat_id] = {"step": "img_wait_photo", "data": {"type": "calligraphy", "author": PEN_ALEFBA}}
    bot.send_message(
        chat_id,
        "🖼 لطفاً عکس خطاطی یا دست‌نوشته را بفرستید.\n(زاویه و کیفیت را خودم خودکار اصلاح می‌کنم.)",
        reply_markup=back_keyboard(),
    )


def start_voice_wizard(chat_id):
    STATE[chat_id] = {"step": "voice_wait_audio", "data": {"type": "voice", "author": PEN_ALEFBA}}
    bot.send_message(
        chat_id,
        "🎤 لطفاً دکلمه را بفرستید — می‌توانید همین‌جا در بله مستقیم ضبط کنید و بفرستید.",
        reply_markup=back_keyboard(),
    )


def show_media_preview(chat_id, data):
    if data.get("type") == "calligraphy":
        cap = "🖼 پیش‌نمایش خطاطی\nعنوان: " + (data.get("title") or "—")
        if data.get("content"):
            cap += "\nتوضیح: " + data["content"]
        fid = data.get("photo_file_id")
        try:
            if fid:
                bot.send_photo(chat_id, fid, caption=cap)
            else:
                bot.send_message(chat_id, cap)
        except Exception:
            bot.send_message(chat_id, cap)
        bot.send_message(chat_id, "اگر درست است «✅ تأیید و انتشار» را بزنید.", reply_markup=media_confirm_keyboard())
    else:
        cap = "🎤 پیش‌نمایش آوا\nعنوان: " + (data.get("title") or "—")
        if data.get("content"):
            cap += "\nتوضیح: " + data["content"]
        fid = data.get("voice_file_id")
        try:
            if fid:
                bot.send_voice(chat_id, fid)
        except Exception:
            pass
        bot.send_message(chat_id, cap + "\n\nاگر درست است «✅ تأیید و انتشار» را بزنید.", reply_markup=media_confirm_keyboard())


def publish_media(chat_id, data, role):
    record = {
        "type": data.get("type"),
        "title": data.get("title"),
        "content": data.get("content"),
        "author": data.get("author") or PEN_ALEFBA,
        "image_url": data.get("image_url"),
        "image_orientation": data.get("image_orientation"),
        "audio_url": data.get("audio_url"),
        "persian_date": jdatetime.date.today().strftime("%Y/%m/%d"),
        "status": "published",
        "submitted_by_chat_id": chat_id,
    }
    try:
        supabase.table("artworks").insert(record).execute()
    except Exception as e:
        print("publish media error:", e)
        bot.send_message(chat_id, "متأسفانه در ثبت خطایی رخ داد. کمی بعد دوباره تلاش کنید.", reply_markup=main_keyboard(role))
        return
    STATE.pop(chat_id, None)
    kind = "خطاطی" if data.get("type") == "calligraphy" else "آوا"
    bot.send_message(chat_id, "✅ {0} شما با موفقیت در سایت منتشر شد. سپاس از شما جناب بخت‌زاده. 🌹".format(kind), reply_markup=main_keyboard(role))
    if role == "poet":
        notify_admins(data)


def handle_image_photo(chat_id, m, st, role):
    bot.send_message(chat_id, "در حال پردازش عکس… لحظه‌ای صبر کنید 🌿")
    try:
        file_id = m.photo[-1].file_id
        data_bytes = download_bale_file(file_id)
        url, orientation = process_and_upload_image(data_bytes)
    except Exception as e:
        print("image process error:", e)
        bot.send_message(chat_id, "متأسفانه در دریافت عکس خطایی رخ داد. دوباره بفرستید یا «🏠 بازگشت به منو».", reply_markup=back_keyboard())
        return
    st["data"]["image_url"] = url
    st["data"]["image_orientation"] = orientation
    st["data"]["photo_file_id"] = file_id
    st["step"] = "img_wait_title"
    bot.send_message(chat_id, "عکس دریافت و بهینه شد ✅\nعنوان این خطاطی را بنویسید (اگر ندارد: بدون عنوان):", reply_markup=back_keyboard())


def handle_voice_audio(chat_id, m, st, role):
    bot.send_message(chat_id, "در حال دریافت صدا… 🌿")
    try:
        if m.content_type == "voice":
            file_id, ext, ctype = m.voice.file_id, "ogg", "audio/ogg"
        else:
            file_id, ext, ctype = m.audio.file_id, "mp3", "audio/mpeg"
        data_bytes = download_bale_file(file_id)
        url = upload_voice(data_bytes, ext, ctype)
    except Exception as e:
        print("voice process error:", e)
        bot.send_message(chat_id, "متأسفانه در دریافت صدا خطایی رخ داد. دوباره بفرستید یا «🏠 بازگشت به منو».", reply_markup=back_keyboard())
        return
    st["data"]["audio_url"] = url
    st["data"]["voice_file_id"] = file_id
    st["step"] = "voice_review"
    try:
        bot.send_voice(chat_id, file_id)
    except Exception:
        pass
    bot.send_message(chat_id, "صدا دریافت شد. یک‌بار گوش کنید:\nاگر خوب است «✅ تأیید صدا»، وگرنه «🎙 ضبط مجدد».", reply_markup=voice_review_keyboard())


def handle_media_wizard(chat_id, text, st, role):
    step = st["step"]
    data = st["data"]

    if step == "img_wait_photo":
        bot.send_message(chat_id, "لطفاً یک «عکس» خطاطی بفرستید.", reply_markup=back_keyboard())
    elif step == "img_wait_title":
        data["title"] = text
        st["step"] = "img_wait_desc"
        bot.send_message(chat_id, "توضیح کوتاه (اختیاری). اگر نمی‌خواهید، بنویسید «ندارد».", reply_markup=back_keyboard())
    elif step == "img_wait_desc":
        data["content"] = None if text in ("ندارد", "-", "نه") else text
        st["step"] = "img_preview"
        show_media_preview(chat_id, data)
    elif step == "img_preview":
        if text == BTN_CONFIRM:
            publish_media(chat_id, data, role)
        elif text == BTN_RESTART:
            start_image_wizard(chat_id)
        else:
            show_media_preview(chat_id, data)

    elif step == "voice_wait_audio":
        bot.send_message(chat_id, "لطفاً یک «فایل صوتی» یا ویس بفرستید.", reply_markup=back_keyboard())
    elif step == "voice_review":
        if text == VOICE_OK:
            st["step"] = "voice_wait_title"
            bot.send_message(chat_id, "عنوان این آوا را بنویسید:", reply_markup=back_keyboard())
        elif text == VOICE_REDO:
            start_voice_wizard(chat_id)
        else:
            bot.send_message(chat_id, "«✅ تأیید صدا» یا «🎙 ضبط مجدد» را انتخاب کنید.", reply_markup=voice_review_keyboard())
    elif step == "voice_wait_title":
        data["title"] = text
        st["step"] = "voice_wait_desc"
        bot.send_message(chat_id, "چند خط توضیح برای این آوا بنویسید (اختیاری). اگر نمی‌خواهید، «ندارد».", reply_markup=back_keyboard())
    elif step == "voice_wait_desc":
        data["content"] = None if text in ("ندارد", "-", "نه") else text
        st["step"] = "voice_preview"
        show_media_preview(chat_id, data)
    elif step == "voice_preview":
        if text == BTN_CONFIRM:
            publish_media(chat_id, data, role)
        elif text == BTN_RESTART:
            start_voice_wizard(chat_id)
        else:
            show_media_preview(chat_id, data)


# ---------------------------------------------------------------------------
#  خواندنِ شعر با صدا (صدا → متن) با چند سرویسِ پشتیبان و تورِ نجات
# ---------------------------------------------------------------------------
def ask_voice_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(VOICE_YES)
    kb.row(VOICE_NO)
    kb.row(BTN_HOME)
    return kb


def read_review_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(READ_OK)
    kb.row(READ_REDO)
    kb.row(BTN_HOME)
    return kb


def _stt_groq(data_bytes, ext):
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": "Bearer " + key},
            files={"file": ("audio." + ext, data_bytes)},
            data={"model": "whisper-large-v3-turbo", "language": "fa",
                  "response_format": "text", "prompt": "این یک شعرِ فارسی است."},
            timeout=90,
        )
        if r.status_code == 200:
            return (r.text or "").strip()
        print("groq stt:", r.status_code, r.text[:200])
    except Exception as e:
        print("groq stt exc:", e)
    return None


def _stt_gemini(data_bytes, ext):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    try:
        import base64
        mime = {"ogg": "audio/ogg", "mp3": "audio/mpeg", "m4a": "audio/mp4"}.get(ext, "audio/ogg")
        body = {"contents": [{"parts": [
            {"text": "این فایلِ صوتی خوانشِ یک شعرِ فارسی است. فقط متنِ دقیقِ شعر را خط‌به‌خط بنویس؛ بدون هیچ توضیحِ اضافه."},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(data_bytes).decode()}}]}]}
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + key,
            json=body, timeout=90)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        print("gemini stt:", r.status_code, r.text[:200])
    except Exception as e:
        print("gemini stt exc:", e)
    return None


def transcribe_poem(data_bytes, ext):
    """چند سرویس پشتِ هم؛ متنِ شعر یا None برمی‌گرداند."""
    return _stt_groq(data_bytes, ext) or _stt_gemini(data_bytes, ext) or None


def start_read_wizard(chat_id):
    STATE[chat_id] = {"step": "read_wait_voice", "data": {"type": "poem", "author": PEN_ALEFBA}}
    bot.send_message(
        chat_id,
        "🎙 جناب بخت‌زاده عزیز، شعرتان را با صدای خودتان بخوانید و همین‌جا در بله ضبط کرده و بفرستید.\n"
        "من گوش می‌دهم و آن را برایتان می‌نویسم. 🌿",
        reply_markup=back_keyboard(),
    )


def handle_read_voice(chat_id, m, st, role):
    # اول صدا را نگه می‌داریم تا هرگز گم نشود
    try:
        if m.content_type == "voice":
            file_id, ext, ctype = m.voice.file_id, "ogg", "audio/ogg"
        else:
            file_id, ext, ctype = m.audio.file_id, "mp3", "audio/mpeg"
        data_bytes = download_bale_file(file_id)
        st["data"]["audio_url"] = upload_voice(data_bytes, ext, ctype)
        st["data"]["voice_file_id"] = file_id
    except Exception as e:
        print("read voice download error:", e)
        bot.send_message(chat_id, "دریافتِ صدا این‌بار نشد. لطفاً دوباره بخوانید و بفرستید. 🌿", reply_markup=back_keyboard())
        return

    bot.send_message(chat_id, "در حال شنیدن و نوشتنِ شعرِ شما… لطفاً چند لحظه صبر کنید. 🌿")
    text = None
    try:
        text = transcribe_poem(data_bytes, ext)
    except Exception as e:
        print("transcribe error:", e)

    if text:
        st["data"]["content"] = text
        st["step"] = "read_review"
        bot.send_message(chat_id, "📜 شعرِ شما را این‌طور شنیدم:\n\n" + text + "\n\n———\nآیا درست است؟", reply_markup=read_review_keyboard())
    else:
        # تورِ نجات: متن درنیامد، ولی صدا محفوظ است → به‌صورت «آوا» ثبت می‌شود
        st["data"]["type"] = "voice"
        st["step"] = "voice_wait_title"
        bot.send_message(
            chat_id,
            "متنِ شعر این‌بار درنیامد، ولی نگران نباشید؛ صدای شما محفوظ است. 🌿\n"
            "می‌توانید همین صدا را به‌عنوان «آوا» ثبت کنیم. لطفاً یک «عنوان» برایش بنویسید\n"
            "(یا برای خواندنِ دوباره، «🏠 بازگشت به منو» را بزنید):",
            reply_markup=back_keyboard(),
        )


def handle_read_wizard(chat_id, text, st, role):
    step = st["step"]
    if step == "read_wait_voice":
        bot.send_message(chat_id, "لطفاً شعر را با صدای خودتان بخوانید و به‌صورت «ویس» بفرستید. 🎙", reply_markup=back_keyboard())
    elif step == "read_review":
        if text == READ_OK:
            st["step"] = "poem_title"
            bot.send_message(chat_id, "بسیار خوب 🌸\nاکنون «عنوان یا سرآغاز» شعر را بنویسید.\n(اگر عنوان ندارد، بنویسید: بدون عنوان)", reply_markup=back_keyboard())
        elif text == READ_REDO:
            start_read_wizard(chat_id)
        else:
            bot.send_message(chat_id, "«✅ بله، درست است» یا «🔁 دوباره می‌خوانم» را انتخاب کنید.", reply_markup=read_review_keyboard())


@bot.message_handler(content_types=["photo", "voice", "audio", "document", "video"])
def on_media(m):
    chat_id = m.chat.id
    role = get_role(chat_id)
    if role is None:
        bot.send_message(chat_id, "ابتدا با زدن /start و وارد کردن رمز، وارد شوید.")
        return
    st = STATE.get(chat_id)
    step = st.get("step", "") if st else ""

    if m.content_type in ("voice", "audio") and step == "read_wait_voice":
        handle_read_voice(chat_id, m, st, role)
        return
    if m.content_type == "photo" and step == "img_wait_photo":
        handle_image_photo(chat_id, m, st, role)
        return
    if m.content_type in ("voice", "audio") and step == "voice_wait_audio":
        handle_voice_audio(chat_id, m, st, role)
        return

    if step == "img_wait_photo":
        bot.send_message(chat_id, "لطفاً یک «عکس» خطاطی بفرستید.", reply_markup=back_keyboard())
        return
    if step == "voice_wait_audio":
        bot.send_message(chat_id, "لطفاً یک «فایل صوتی» یا ویس بفرستید.", reply_markup=back_keyboard())
        return

    bot.send_message(
        chat_id,
        "برای ارسال خطاطی یا دکلمه، اول از منوی پایین دکمهٔ مربوطه را بزنید. 🌸",
        reply_markup=main_keyboard(role),
    )


@bot.message_handler(content_types=["text"])
def on_text(m):
    chat_id = m.chat.id
    text = (m.text or "").strip()
    role = get_role(chat_id)

    # کاربر هنوز وارد نشده → هر پیام یک تلاش برای رمز است
    if role is None:
        handle_password(chat_id, text)
        return

    # دکمه‌های سراسری
    if text == BTN_HOME:
        STATE.pop(chat_id, None)
        send_welcome(chat_id, role)
        return
    if text == BTN_HELP:
        send_help(chat_id, role)
        return

    # اگر در میانهٔ یک گفت‌وگو هستیم
    st = STATE.get(chat_id)
    if st:
        step = st.get("step", "")
        if step == "admin_search":
            admin_do_search(chat_id, text, role)
            return
        if step.startswith("poem_") or step.startswith("edit_"):
            handle_poem_wizard(chat_id, text, st, role)
            return
        if step.startswith("img_") or step.startswith("voice_"):
            handle_media_wizard(chat_id, text, st, role)
            return
        if step.startswith("read_"):
            handle_read_wizard(chat_id, text, st, role)
            return

    # انتخاب از منوی اصلی
    if text == BTN_READ:
        start_read_wizard(chat_id)
        return
    if text == BTN_POEM:
        start_poem_wizard(chat_id)
        return
    if text == BTN_IMAGE:
        start_image_wizard(chat_id)
        return
    if text == BTN_VOICE:
        start_voice_wizard(chat_id)
        return
    if role == "admin" and text == BTN_ADMIN_RECENT:
        admin_recent(chat_id, role)
        return
    if role == "admin" and text == BTN_ADMIN_SEARCH:
        STATE[chat_id] = {"step": "admin_search", "data": {}}
        bot.send_message(chat_id, "🔍 کلمه یا عنوان مورد جستجو را بنویسید:", reply_markup=back_keyboard())
        return

    bot.send_message(chat_id, "لطفاً از دکمه‌های پایین صفحه استفاده کنید. 🌸", reply_markup=main_keyboard(role))


@bot.callback_query_handler(func=lambda c: True)
def on_callback(c):
    chat_id = c.message.chat.id
    role = get_role(chat_id)
    if role != "admin":
        bot.answer_callback_query(c.id, "شما به این بخش دسترسی ندارید.")
        return

    action, _, id_ = c.data.partition(":")
    try:
        if action == "del":
            supabase.table("artworks").update({"is_deleted": True}).eq("id", id_).execute()
            bot.answer_callback_query(c.id, "حذف شد ✅")
            bot.edit_message_text(f"🗑 اثر #{id_} حذف شد.", chat_id, c.message.message_id)
        elif action == "unpub":
            supabase.table("artworks").update({"status": "draft"}).eq("id", id_).execute()
            bot.answer_callback_query(c.id, "پنهان شد")
            bot.edit_message_text(f"👁 اثر #{id_} از سایت پنهان شد (پیش‌نویس).", chat_id, c.message.message_id)
        elif action == "pub":
            supabase.table("artworks").update({"status": "published"}).eq("id", id_).execute()
            bot.answer_callback_query(c.id, "منتشر شد")
            bot.edit_message_text(f"🌐 اثر #{id_} منتشر شد.", chat_id, c.message.message_id)
        elif action == "edit":
            res = supabase.table("artworks").select("*").eq("id", id_).limit(1).execute()
            if res.data:
                r = res.data[0]
                STATE[chat_id] = {
                    "step": "poem_preview",
                    "data": {
                        "type": r.get("type", "poem"),
                        "title": r.get("title"),
                        "content": r.get("content"),
                        "author": r.get("author"),
                        "composed_at_text": r.get("composed_at_text"),
                        "category": r.get("category"),
                        "edit_id": r.get("id"),
                    },
                }
                bot.answer_callback_query(c.id)
                show_preview(chat_id, STATE[chat_id]["data"])
            else:
                bot.answer_callback_query(c.id, "اثر یافت نشد.")
        else:
            bot.answer_callback_query(c.id)
    except Exception as e:
        print("callback error:", e)
        bot.answer_callback_query(c.id, "خطایی رخ داد.")


# ---------------------------------------------------------------------------
#  اجرای ربات + سرور بیدارباش
# ---------------------------------------------------------------------------
def run_bot():
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)


threading.Thread(target=run_bot, daemon=True).start()


def self_heartbeat():
    """ضربانِ داخلی: تا وقتی ربات روشن است، هر ۱۰ دقیقه خودش را صدا می‌زند
    تا سرور بیدار بماند (بیمهٔ مضاعف در کنار پینگ بیرونی)."""
    url = os.getenv("SELF_URL", "https://alefba-bot.onrender.com/keepalive")
    while True:
        time.sleep(600)
        try:
            requests.get(url, timeout=20)
        except Exception as e:
            print("self-heartbeat error:", e)


threading.Thread(target=self_heartbeat, daemon=True).start()


@app.route("/")
def index():
    return "سرور بیدارباشِ ربات دیوان الف ب فعال است."


@app.route("/health")
def health():
    return "ok", 200


@app.route("/keepalive")
def keepalive():
    """با یک پینگ بیرونی هر چند دقیقه، هم رندر بیدار می‌ماند و هم
    با یک خواندنِ سبک، دیتابیس ساببیس به خواب (Pause) نمی‌رود."""
    try:
        supabase.table("artworks").select("id").limit(1).execute()
    except Exception as e:
        print("keepalive db touch error:", e)
    return "alive", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
