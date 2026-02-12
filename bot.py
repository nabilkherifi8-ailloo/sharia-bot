import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from lessons import LESSONS

ADMIN_CHAT_ID = -5286458958
MAP_FILE = "msg_map.json"


def _clean(s: str) -> str:
    """إزالة كل الفراغات والأسطر الجديدة من البداية والنهاية + داخل النص."""
    if not s:
        return ""
    # split/join يزيل كل أنواع الـ whitespace بما فيها \n \r \t والمسافات
    return "".join(str(s).strip().split())


def load_map():
    if not os.path.exists(MAP_FILE):
        return {}
    try:
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_map(m):
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False)


def home_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("📚 الدروس", callback_data="years")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "السلام عليكم ورحمة الله تعالى وبركاته 🌿\n"
        "مرحباً بك في البوت المساعد لطالب الشريعة\n"
        "في جامعة البشير الإبراهيمي 🕌\n\n"
        "📚 الدروس متاحة عبر الأزرار\n"
        "✍️ أرسل سؤالك مباشرة وسيصل إلى المشرفين"
    )
    await update.message.reply_text(text, reply_markup=home_keyboard())


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "years":
        kb = [[InlineKeyboardButton(y, callback_data=f"year|{y}")] for y in LESSONS]
        await q.message.edit_text("📘 اختر السنة:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if q.data.startswith("year|"):
        year = q.data.split("|", 1)[1]
        context.user_data["year"] = year
        kb = [[InlineKeyboardButton(s, callback_data=f"spec|{s}")] for s in LESSONS[year]]
        await q.message.edit_text("📙 اختر التخصص:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if q.data.startswith("spec|"):
        spec = q.data.split("|", 1)[1]
        context.user_data["spec"] = spec
        year = context.user_data["year"]
        kb = [[InlineKeyboardButton(sem, callback_data=f"sem|{sem}")] for sem in LESSONS[year][spec]]
        await q.message.edit_text("📗 اختر السداسي:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if q.data.startswith("sem|"):
        sem = q.data.split("|", 1)[1]
        context.user_data["sem"] = sem
        year = context.user_data["year"]
        spec = context.user_data["spec"]
        kb = [[InlineKeyboardButton(sub, callback_data=f"sub|{sub}")] for sub in LESSONS[year][spec][sem]]
        await q.message.edit_text("📚 اختر المادة:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if q.data.startswith("sub|"):
        sub = q.data.split("|", 1)[1]
        year = context.user_data["year"]
        spec = context.user_data["spec"]
        sem = context.user_data["sem"]

        items = LESSONS[year][spec][sem][sub]  # قائمة [(عنوان, رابط), ...]

        if not items:
            await q.message.edit_text(f"⚠️ لا توجد دروس مضافة بعد لمادة: {sub}")
            return

        kb = [[InlineKeyboardButton(title, url=url)] for title, url in items]
        await q.message.edit_text(f"📖 {sub}\nاختر الدرس:", reply_markup=InlineKeyboardMarkup(kb))


async def student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    sent = await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"📩 سؤال جديد من طالب\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"🆔 ID: {user.id}\n\n"
        f"✉️ الرسالة:\n{update.message.text}\n\n"
        f"↩️ للرد: اعمل Reply على هذه الرسالة"
    )

    m = load_map()
    m[str(sent.message_id)] = update.effective_chat.id
    save_map(m)

    await update.message.reply_text("✅ تم إرسال سؤالك إلى المشرفين.")


async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return
    if not update.message.reply_to_message:
        return

    m = load_map()
    key = str(update.message.reply_to_message.message_id)
    if key not in m:
        return

    await context.bot.send_message(
        chat_id=m[key],
        text=f"📩 رد المشرفين:\n\n{update.message.text}"
    )


def build_app():
    # ✅ هنا الإصلاح الحقيقي: تنظيف التوكن من \n والمسافات
    token = _clean(os.environ.get("BOT_TOKEN", ""))
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Set it in Render Environment Variables.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))

    # رسائل الطلاب في الخاص فقط
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, student_message))

    # ردود المشرفين داخل مجموعة المشرفين فقط
    app.add_handler(MessageHandler(filters.Chat(ADMIN_CHAT_ID) & filters.TEXT, admin_reply))

    return app
