import os
import time
import threading

import telebot
from telebot import apihelper, types
from flask import Flask
import jdatetime
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
    kb.row(BTN_POEM)
    kb.row(BTN_VOICE)
    kb.row(BTN_IMAGE)
    if role == "admin":
        kb.row(BTN_ADMIN_RECENT, BTN_ADMIN_SEARCH)
    kb.row(BTN_HELP)
    return kb


def back_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(BTN_HOME)
    return kb


def pen_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(PEN_ALEFBA, PEN_SABA)
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
    kb.row(CATEGORIES[0], CATEGORIES[1])
    kb.row(CATEGORIES[2], CATEGORIES[3])
    kb.row(BTN_HOME)
    return kb


def confirm_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(BTN_CONFIRM)
    kb.row(BTN_EDIT, BTN_RESTART)
    kb.row(BTN_HOME)
    return kb


def edit_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(EDIT_TEXT, EDIT_TITLE)
    kb.row(EDIT_PEN, EDIT_DATE)
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
            publish_poem(chat_id, data, role)
        elif text == BTN_EDIT:
            st["step"] = "poem_edit_menu"
            bot.send_message(chat_id, "کدام بخش را می‌خواهید اصلاح کنید؟", reply_markup=edit_keyboard())
        elif text == BTN_RESTART:
            start_poem_wizard(chat_id)
        else:
            show_preview(chat_id, data)

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


@bot.message_handler(content_types=["photo", "voice", "audio", "document", "video"])
def on_media(m):
    chat_id = m.chat.id
    role = get_role(chat_id)
    if role is None:
        bot.send_message(chat_id, "ابتدا با زدن /start و وارد کردن رمز، وارد شوید.")
        return
    bot.send_message(
        chat_id,
        "🌱 بخش «خطاطی» و «دکلمه» در گام بعدی به‌زودی فعال می‌شود.\n"
        "فعلاً می‌توانید شعر خود را از طریق «✍️ ارسال شعر جدید» ثبت کنید.",
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

    # انتخاب از منوی اصلی
    if text == BTN_POEM:
        start_poem_wizard(chat_id)
        return
    if text in (BTN_VOICE, BTN_IMAGE):
        bot.send_message(
            chat_id,
            "🌱 این بخش در گام بعدی به‌زودی فعال می‌شود.",
            reply_markup=main_keyboard(role),
        )
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
