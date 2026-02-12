import os
import json
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import Forbidden, BadRequest

from lessons import LESSONS

# ====== إعدادات ======
ADMIN_CHAT_ID = -5286458958          # مجموعة المشرفين
MAP_FILE = "msg_map.json"            # ربط رسائل المجموعة بالطالب للرد
USERS_FILE = "users.json"            # قائمة الطلاب (للبث الجماعي)


# ====== أدوات مساعدة ======
def _clean(s: str) -> str:
    """إزالة أي مسافات/أسطر جديدة من النص (مهم للتوكن وغيره)."""
    if not s:
        return ""
    return "".join(str(s).strip().split())


def _load_json(path: str, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def load_map() -> dict:
    return _load_json(MAP_FILE, {})


def save_map(m: dict):
    _save_json(MAP_FILE, m)


def load_users() -> set[int]:
    data = _load_json(USERS_FILE, [])
    try:
        return set(int(x) for x in data)
    except Exception:
        return set()


def save_users(users: set[int]):
    _save_json(USERS_FILE, sorted(list(users)))


def add_user(chat_id: int):
    users = load_users()
    users.add(int(chat_id))
    save_users(users)


# ====== لوحات المفاتيح (Back/Home) ======
def kb_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 الدروس", callback_data="years")]
    ])


def kb_years():
    years = list(LESSONS.keys())
    keyboard = [[InlineKeyboardButton(y, callback_data=f"y:{i}")] for i, y in enumerate(years)]
    keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(keyboard)


def kb_specs(year: str):
    specs = list(LESSONS[year].keys())
    keyboard = [[InlineKeyboardButton(s, callback_data=f"sp:{i}")] for i, s in enumerate(specs)]
    keyboard += [
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back:years")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(keyboard)


def kb_sems(year: str, spec: str):
    sems = list(LESSONS[year][spec].keys())
    keyboard = [[InlineKeyboardButton(s, callback_data=f"se:{i}")] for i, s in enumerate(sems)]
    keyboard += [
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back:specs")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(keyboard)


def kb_subjects(year: str, spec: str, sem: str):
    subjects = list(LESSONS[year][spec][sem].keys())
    keyboard = [[InlineKeyboardButton(sub, callback_data=f"su:{i}")] for i, sub in enumerate(subjects)]
    keyboard += [
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back:sems")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(keyboard)


def kb_lessons(year: str, spec: str, sem: str, subject: str):
    items = LESSONS[year][spec][sem][subject]  # [(title, url), ...]
    keyboard = []

    # روابط الدروس (URL buttons)
    for title, url in items:
        keyboard.append([InlineKeyboardButton(title, url=url)])

    keyboard += [
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back:subjects")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ====== الشاشات ======
WELCOME_TEXT = (
    "السلام عليكم ورحمة الله تعالى وبركاته 🌿\n"
    "مرحباً بك في البوت المساعد لطالب الشريعة\n"
    "في جامعة البشير الإبراهيمي 🕌\n\n"
    "📚 الدروس عبر الأزرار\n"
    "✍️ لإرسال سؤال (نص/صورة/ملف): أرسل رسالتك هنا في الخاص\n"
    "وسيتم الرد عليك من طرف المشرفين بإذن الله"
)


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # تسجيل الطالب (للبث)
    if update.effective_chat and update.effective_chat.type == "private":
        add_user(update.effective_chat.id)

    if update.message:
        await update.message.reply_text(WELCOME_TEXT, reply_markup=kb_home())
    else:
        await update.callback_query.message.edit_text(WELCOME_TEXT, reply_markup=kb_home())


# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_home(update, context)


# ====== الأزرار ======
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    # Home
    if data == "home":
        context.user_data.clear()
        return await show_home(update, context)

    # Years list
    if data == "years":
        context.user_data.clear()
        return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())

    # Back buttons
    if data.startswith("back:"):
        where = data.split(":", 1)[1]

        if where == "years":
            context.user_data.pop("year", None)
            context.user_data.pop("spec", None)
            context.user_data.pop("sem", None)
            context.user_data.pop("subject", None)
            return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())

        if where == "specs":
            year = context.user_data.get("year")
            if not year:
                return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
            context.user_data.pop("spec", None)
            context.user_data.pop("sem", None)
            context.user_data.pop("subject", None)
            return await q.message.edit_text("📙 اختر التخصص:", reply_markup=kb_specs(year))

        if where == "sems":
            year = context.user_data.get("year")
            spec = context.user_data.get("spec")
            if not (year and spec):
                return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
            context.user_data.pop("sem", None)
            context.user_data.pop("subject", None)
            return await q.message.edit_text("📗 اختر السداسي:", reply_markup=kb_sems(year, spec))

        if where == "subjects":
            year = context.user_data.get("year")
            spec = context.user_data.get("spec")
            sem = context.user_data.get("sem")
            if not (year and spec and sem):
                return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
            context.user_data.pop("subject", None)
            return await q.message.edit_text("📚 اختر المادة:", reply_markup=kb_subjects(year, spec, sem))

    # Select year by index
    if data.startswith("y:"):
        idx = int(data.split(":", 1)[1])
        years = list(LESSONS.keys())
        year = years[idx]
        context.user_data["year"] = year
        return await q.message.edit_text("📙 اختر التخصص:", reply_markup=kb_specs(year))

    # Select spec
    if data.startswith("sp:"):
        idx = int(data.split(":", 1)[1])
        year = context.user_data.get("year")
        specs = list(LESSONS[year].keys())
        spec = specs[idx]
        context.user_data["spec"] = spec
        return await q.message.edit_text("📗 اختر السداسي:", reply_markup=kb_sems(year, spec))

    # Select sem
    if data.startswith("se:"):
        idx = int(data.split(":", 1)[1])
        year = context.user_data.get("year")
        spec = context.user_data.get("spec")
        sems = list(LESSONS[year][spec].keys())
        sem = sems[idx]
        context.user_data["sem"] = sem
        return await q.message.edit_text("📚 اختر المادة:", reply_markup=kb_subjects(year, spec, sem))

    # Select subject
    if data.startswith("su:"):
        idx = int(data.split(":", 1)[1])
        year = context.user_data.get("year")
        spec = context.user_data.get("spec")
        sem = context.user_data.get("sem")
        subjects = list(LESSONS[year][spec][sem].keys())
        subject = subjects[idx]
        context.user_data["subject"] = subject

        lessons = LESSONS[year][spec][sem][subject]
        if not lessons:
            return await q.message.edit_text(
                f"⚠️ لا توجد دروس مضافة بعد لمادة:\n{subject}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="back:subjects")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ])
            )

        return await q.message.edit_text(
            f"📖 {subject}\nاختر الدرس:",
            reply_markup=kb_lessons(year, spec, sem, subject)
        )


# ====== (3) استقبال أسئلة الطلاب نص/صورة/ملف وإرسالها للمشرفين ======
async def student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فقط الخاص
    if update.effective_chat.type != "private":
        return

    add_user(update.effective_chat.id)

    user = update.effective_user
    student_chat_id = update.effective_chat.id
    msg = update.message

    # رسالة معلومات للمشرفين (يردون عليها Reply)
    meta = await context.bot.send_message(
        ADMIN_CHAT_ID,
        "📩 سؤال جديد من طالب\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"🆔 user_id: {user.id}\n\n"
        "↩️ للرد: اعمل Reply على هذه الرسالة أو على الرسالة التي تحتها."
    )

    # نسخ رسالة الطالب (نص/صورة/ملف...) إلى مجموعة المشرفين كـ Reply على meta
    copied = await context.bot.copy_message(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=student_chat_id,
        message_id=msg.message_id,
        reply_to_message_id=meta.message_id
    )

    # حفظ الربط: (رسالة meta) و (رسالة الطالب المنسوخة) -> chat_id للطالب
    m = load_map()
    m[str(meta.message_id)] = student_chat_id
    m[str(copied.message_id)] = student_chat_id
    save_map(m)

    await msg.reply_text("✅ تم استلام رسالتك وإرسالها للمشرفين.\nسيتم الرد عليك بإذن الله.")


# ====== ردود المشرفين (Reply في المجموعة) ======
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    msg = update.message
    if not msg or not msg.reply_to_message:
        return

    m = load_map()
    key = str(msg.reply_to_message.message_id)
    student_chat_id = m.get(key)
    if not student_chat_id:
        return

    # لو رد نصي: نرسل بصيغة جميلة
    if msg.text:
        await context.bot.send_message(student_chat_id, f"📩 رد من المشرفين:\n\n{msg.text}")
        return

    # لو رد بملف/صورة/صوت...: نرسل عنوان ثم ننسخ الرسالة كما هي
    await context.bot.send_message(student_chat_id, "📩 رد من المشرفين:")
    await context.bot.copy_message(
        chat_id=student_chat_id,
        from_chat_id=ADMIN_CHAT_ID,
        message_id=msg.message_id
    )


# ====== (6) Broadcast إعلان جماعي للطلاب ======
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فقط داخل مجموعة المشرفين
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    # تحقق أن المرسل Admin/Creator في المجموعة
    try:
        member = await context.bot.get_chat_member(ADMIN_CHAT_ID, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
            return
    except Exception:
        await update.message.reply_text("❌ لم أستطع التحقق من صلاحياتك.")
        return

    users = load_users()
    if not users:
        await update.message.reply_text("لا يوجد طلاب مسجلين بعد.")
        return

    # محتوى الإعلان:
    # 1) إذا كتب نص بعد /broadcast
    if context.args:
        text = " ".join(context.args).strip()
        if not text:
            await update.message.reply_text("اكتب الإعلان بعد الأمر:\n/broadcast نص الإعلان")
            return

        ok = 0
        bad = 0
        removed = set()

        for chat_id in list(users):
            try:
                await context.bot.send_message(chat_id, f"📢 إعلان:\n\n{text}")
                ok += 1
            except Forbidden:
                removed.add(chat_id)
                bad += 1
            except Exception:
                bad += 1

        if removed:
            users -= removed
            save_users(users)

        await update.message.reply_text(f"✅ تم الإرسال إلى: {ok}\n⚠️ فشل/محظور: {bad}")
        return

    # 2) أو يرسل /broadcast بالرد على رسالة (نص/صورة/ملف) لبثّها
    if update.message.reply_to_message:
        src = update.message.reply_to_message

        ok = 0
        bad = 0
        removed = set()

        for chat_id in list(users):
            try:
                # ننسخ الرسالة كما هي (يدعم نص/صورة/ملف...)
                await context.bot.copy_message(chat_id=chat_id, from_chat_id=ADMIN_CHAT_ID, message_id=src.message_id)
                ok += 1
            except Forbidden:
                removed.add(chat_id)
                bad += 1
            except BadRequest:
                bad += 1
            except Exception:
                bad += 1

        if removed:
            users -= removed
            save_users(users)

        await update.message.reply_text(f"✅ تم بث الرسالة إلى: {ok}\n⚠️ فشل/محظور: {bad}")
        return

    await update.message.reply_text(
        "طريقة الاستعمال:\n"
        "1) /broadcast نص الإعلان\n"
        "أو\n"
        "2) اعمل Reply على رسالة/صورة/ملف ثم اكتب /broadcast"
    )


# ====== بناء التطبيق ======
def build_app():
    token = _clean(os.environ.get("BOT_TOKEN", ""))
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Set it in Render Environment Variables.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast, filters=filters.Chat(ADMIN_CHAT_ID)))

    app.add_handler(CallbackQueryHandler(buttons))

    # ردود المشرفين (أي رسالة في مجموعة المشرفين) - داخل الدالة نتحقق أنه Reply
    app.add_handler(MessageHandler(filters.Chat(ADMIN_CHAT_ID) & ~filters.COMMAND, admin_reply))

    # رسائل الطلاب في الخاص (نص + صور + ملفات + صوت + فيديو...)
    student_filter = (
        filters.ChatType.PRIVATE
        & ~filters.COMMAND
        & (filters.TEXT | filters.PHOTO | filters.DOCUMENT | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.ANIMATION | filters.STICKER)
    )
    app.add_handler(MessageHandler(student_filter, student_message))

    return app
