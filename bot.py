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
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📚 الدروس", callback_data="years")]]
    )


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
    query = update.callback_query
    await query.answer()

    if query.data == "years":
        keyboard = [
            [InlineKeyboardButton(year, callback_data=f"year|{year}")]
            for year in LESSONS
        ]
        await query.message.edit_text(
            "📘 اختر السنة:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("year|"):
        year = query.data.split("|", 1)[1]
        context.user_data["year"] = year

        specs = LESSONS[year]
        keyboard = [
            [InlineKeyboardButton(spec, callback_data=f"spec|{spec}")]
            for spec in specs
        ]

        await query.message.edit_text(
            "📙 اختر التخصص:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("spec|"):
        spec = query.data.split("|", 1)[1]
        context.user_data["spec"] = spec

        year = context.user_data["year"]
        sems = LESSONS[year][spec]

        keyboard = [
            [InlineKeyboardButton(sem, callback_data=f"sem|{sem}")]
            for sem in sems
        ]

        await query.message.edit_text(
            "📗 اختر السداسي:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("sem|"):
        sem = query.data.split("|", 1)[1]
        context.user_data["sem"] = sem

        year = context.user_data["year"]
        spec = context.user_data["spec"]

        subjects = LESSONS[year][spec][sem]

        keyboard = [
            [InlineKeyboardButton(sub, callback_data=f"sub|{sub}")]
            for sub in subjects
        ]

        await query.message.edit_text(
            "📚 اختر المادة:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("sub|"):
        sub = query.data.split("|", 1)[1]

        await query.message.edit_text(
            f"📖 مادة: {sub}\n(سيتم إضافة الدروس لاحقاً)"
        )


async def student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    sent = await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"📩 سؤال جديد\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"🆔 ID: {user.id}\n\n"
        f"{update.message.text}\n\n"
        f"↩️ للرد استخدم Reply على هذه الرسالة"
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
        text=f"📩 رد المشرفين:\n\n{update.message.text}",
    )


def build_app():
    TOKEN = os.environ.get("BOT_TOKEN")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            student_message,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Chat(ADMIN_CHAT_ID) & filters.TEXT,
            admin_reply,
        )
    )

    return app
