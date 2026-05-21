# ================================================================
#  bot.py — البوت المساعد لطالب الشريعة
#  جامعة البشير الإبراهيمي — بناء متكامل ومتناسق
# ================================================================

import os
import json
import copy
import random
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import Forbidden, BadRequest


# ════════════════════════════════════════════════════════════════
#  الإعدادات
# ════════════════════════════════════════════════════════════════

ADMIN_CHAT_ID  = -5286458958       # معرّف مجموعة المشرفين
ADMIN_IDS      = {1490829295}      # معرّفات المشرفين

FILE_MAP       = "msg_map.json"        # ربط رسائل الطلاب بالمشرفين
FILE_USERS     = "users.json"          # قائمة الطلاب
FILE_POINTS    = "points.json"         # نقاط وإنجازات الطلاب
FILE_CALENDAR  = "calendar.json"       # التقويم الجامعي
FILE_LESSONS   = "lessons_data.json"   # الدروس الديناميكية
FILE_QUIZ      = "quiz_data.json"      # أسئلة الكويز الديناميكية
FILE_SCHED     = "schedule_state.json" # حالة الجدولة اليومية

TZ = ZoneInfo("Africa/Algiers")


# ════════════════════════════════════════════════════════════════
#  أسئلة الكويز الافتراضية
# ════════════════════════════════════════════════════════════════

DEFAULT_QUIZ = [
    {"q": "عدد أركان الإسلام؟",
     "choices": ["3", "4", "5", "6"],
     "answer": 2, "points": 2},
    {"q": "النية محلها؟",
     "choices": ["اللسان", "القلب", "اليد", "العين"],
     "answer": 1, "points": 2},
    {"q": "وقت صلاة الفجر ينتهي بـ؟",
     "choices": ["طلوع الشمس", "الزوال", "غروب الشمس", "منتصف الليل"],
     "answer": 0, "points": 2},
    {"q": "حكم الوضوء للصلاة؟",
     "choices": ["سنة", "واجب", "مكروه", "مباح"],
     "answer": 1, "points": 2},
    {"q": "كم عدد سور القرآن الكريم؟",
     "choices": ["110", "114", "120", "100"],
     "answer": 1, "points": 2},
    {"q": "أول سورة نزلت من القرآن الكريم؟",
     "choices": ["الفاتحة", "البقرة", "العلق", "المدثر"],
     "answer": 2, "points": 3},
]

ACHIEVEMENTS = [
    (10,  "🥉 مجتهد — 10 نقاط"),
    (25,  "🥈 متفوق — 25 نقطة"),
    (50,  "🥇 نجم الشريعة — 50 نقطة"),
    (100, "🏅 حافظ — 100 نقطة"),
]


# ════════════════════════════════════════════════════════════════
#  أدوات JSON المساعدة
# ════════════════════════════════════════════════════════════════

def _clean(s: str) -> str:
    """تنظيف النص من المسافات الزائدة"""
    return "".join(str(s).strip().split()) if s else ""


def _load(path: str, default):
    """تحميل ملف JSON بأمان"""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save(path: str, data):
    """حفظ بيانات في ملف JSON"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_url(s: str) -> bool:
    """التحقق من أن النص رابط URL"""
    return isinstance(s, str) and (s.startswith("http://") or s.startswith("https://"))


def is_admin(user_id: int, chat_id: int = None) -> bool:
    """التحقق من صلاحيات المشرف"""
    return user_id in ADMIN_IDS or (chat_id is not None and chat_id == ADMIN_CHAT_ID)


# ════════════════════════════════════════════════════════════════
#  إدارة الدروس
# ════════════════════════════════════════════════════════════════

def load_lessons() -> dict:
    """
    تحميل الدروس بالأولوية التالية:
    1. من lessons_data.json إذا كان موجوداً وغير فارغ
    2. من lessons.py للتهيئة الأولى
    """
    # محاولة التحميل من الملف الديناميكي
    if os.path.exists(FILE_LESSONS):
        data = _load(FILE_LESSONS, None)
        if isinstance(data, dict) and len(data) > 0:
            return data

    # تهيئة من lessons.py عند أول تشغيل
    try:
        from lessons import LESSONS as _default
        data = copy.deepcopy(_default)
        _save(FILE_LESSONS, data)
        print("✅ تم تهيئة lessons_data.json من lessons.py")
        return data
    except ImportError:
        print("❌ خطأ: ملف lessons.py غير موجود!")
        return {}
    except Exception as e:
        print(f"❌ خطأ في تحميل الدروس: {e}")
        return {}


def save_lessons(data: dict):
    _save(FILE_LESSONS, data)


def count_lessons(data: dict) -> int:
    """حساب إجمالي عدد الدروس"""
    return sum(
        len(items)
        for yr in data.values()
        for sp in yr.values()
        for sm in sp.values()
        for items in sm.values()
    )


# ════════════════════════════════════════════════════════════════
#  إدارة الكويز
# ════════════════════════════════════════════════════════════════

def load_quiz() -> list:
    data = _load(FILE_QUIZ, None)
    if isinstance(data, list) and len(data) > 0:
        return data
    _save(FILE_QUIZ, DEFAULT_QUIZ)
    return copy.deepcopy(DEFAULT_QUIZ)


def save_quiz(data: list):
    _save(FILE_QUIZ, data)


# ════════════════════════════════════════════════════════════════
#  إدارة المستخدمين
# ════════════════════════════════════════════════════════════════

def load_users() -> set:
    data = _load(FILE_USERS, [])
    try:
        return set(int(x) for x in data)
    except Exception:
        return set()


def save_users(users: set):
    _save(FILE_USERS, sorted(list(users)))


def register_user(chat_id: int):
    """تسجيل مستخدم جديد إن لم يكن مسجلاً"""
    users = load_users()
    if int(chat_id) not in users:
        users.add(int(chat_id))
        save_users(users)


# ════════════════════════════════════════════════════════════════
#  إدارة النقاط والإنجازات
# ════════════════════════════════════════════════════════════════

def load_points() -> dict:
    return _load(FILE_POINTS, {})


def save_points(data: dict):
    _save(FILE_POINTS, data)


def get_profile(user_id: int) -> dict:
    p   = load_points()
    key = str(user_id)
    if key not in p:
        p[key] = {"points": 0, "badges": [], "last_quiz": None}
        save_points(p)
    return p[key]


def save_profile(user_id: int, profile: dict):
    p = load_points()
    p[str(user_id)] = profile
    save_points(p)


def check_achievements(profile: dict) -> list:
    """التحقق من الإنجازات الجديدة وإضافتها"""
    badges     = set(profile.get("badges", []))
    new_badges = []
    for threshold, badge in ACHIEVEMENTS:
        if profile["points"] >= threshold and badge not in badges:
            badges.add(badge)
            new_badges.append(badge)
    profile["badges"] = sorted(badges)
    return new_badges


# ════════════════════════════════════════════════════════════════
#  إدارة التقويم الجامعي
# ════════════════════════════════════════════════════════════════

DEFAULT_CALENDAR = {
    "📌 مواعيد الامتحانات": "لم يتم تحديد المواعيد بعد.",
    "🏖️ العطل الرسمية":    "لم يتم تحديد العطل بعد.",
    "⏳ آخر الآجال":        "لم يتم تحديد الآجال بعد.",
    "📖 ورد اليوم":         "لم يتم ضبط ورد اليوم بعد.",
    "📜 حديث اليوم":        "لم يتم ضبط حديث اليوم بعد.",
}


def load_calendar() -> dict:
    cal = _load(FILE_CALENDAR, None)
    if not isinstance(cal, dict) or not cal:
        cal = DEFAULT_CALENDAR.copy()
        _save(FILE_CALENDAR, cal)
    return cal


def save_calendar(cal: dict):
    _save(FILE_CALENDAR, cal)


# ════════════════════════════════════════════════════════════════
#  إدارة الجدولة اليومية
# ════════════════════════════════════════════════════════════════

def load_sched() -> dict:
    data = _load(FILE_SCHED, {})
    return data if isinstance(data, dict) else {}


def save_sched(data: dict):
    _save(FILE_SCHED, data)


def load_map() -> dict:
    return _load(FILE_MAP, {})


def save_map(data: dict):
    _save(FILE_MAP, data)


# ════════════════════════════════════════════════════════════════
#  البث للجميع
# ════════════════════════════════════════════════════════════════

async def send_to_all(bot, text: str, parse_mode: str = None):
    """إرسال رسالة لجميع الطلاب المسجلين"""
    users   = load_users()
    blocked = set()
    for uid in list(users):
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode=parse_mode)
        except Forbidden:
            blocked.add(uid)
        except Exception:
            pass
    if blocked:
        save_users(users - blocked)


# ════════════════════════════════════════════════════════════════
#  الجدولة اليومية التلقائية
# ════════════════════════════════════════════════════════════════

DAILY_MSGS = [
    (7,  0,  "morning",
     "🌿 *أذكار الصباح*\n\n"
     "اللهم بك أصبحنا وبك أمسينا وبك نحيا وبك نموت وإليك النشور.\n\n"
     "أصبحنا وأصبح الملك لله والحمد لله لا شريك له، له الملك وله الحمد وهو على كل شيء قدير."),
    (17, 0,  "evening",
     "🌙 *أذكار المساء*\n\n"
     "اللهم بك أمسينا وبك أصبحنا وبك نحيا وبك نموت وإليك المصير.\n\n"
     "أمسينا وأمسى الملك لله والحمد لله لا شريك له، له الملك وله الحمد وهو على كل شيء قدير."),
]

DAILY_CAL = [
    (10, 0,  "wird",   "📖 ورد اليوم"),
    (20, 0,  "hadith", "📜 حديث اليوم"),
]


async def scheduler_loop(app: Application):
    """حلقة الجدولة — تفحص كل 30 ثانية"""
    while True:
        try:
            now   = datetime.now(TZ)
            today = now.date().isoformat()
            st    = load_sched()

            if today not in st:
                st[today] = {}
            sent = st[today]

            # رسائل ثابتة (أذكار)
            for hour, minute, key, text in DAILY_MSGS:
                if now.hour == hour and now.minute == minute and not sent.get(key):
                    await send_to_all(app.bot, text, parse_mode="Markdown")
                    sent[key] = True
                    save_sched(st)

            # رسائل من التقويم (ورد + حديث)
            for hour, minute, key, cal_key in DAILY_CAL:
                if now.hour == hour and now.minute == minute and not sent.get(key):
                    cal  = load_calendar()
                    body = cal.get(cal_key, "لم يتم الضبط بعد.")
                    text = f"{cal_key}\n\n{body}"
                    await send_to_all(app.bot, text)
                    sent[key] = True
                    save_sched(st)

        except Exception as e:
            print(f"⚠️ scheduler error: {e}")

        await asyncio.sleep(30)


async def on_startup(app: Application):
    """تُنفَّذ عند بدء تشغيل البوت"""
    app.create_task(scheduler_loop(app))
    print("✅ البوت يعمل — الجدولة اليومية نشطة")


# ════════════════════════════════════════════════════════════════
#  لوحات المفاتيح (Keyboards)
# ════════════════════════════════════════════════════════════════

def kb_main():
    """لوحة مفاتيح الصفحة الرئيسية"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 الدروس",           callback_data="go:years")],
        [InlineKeyboardButton("📝 اختبار قصير",      callback_data="quiz:start"),
         InlineKeyboardButton("🏆 نقاطي",            callback_data="points:show")],
        [InlineKeyboardButton("🗓️ التقويم الجامعي",  callback_data="cal:home")],
        [InlineKeyboardButton("❓ مساعدة",            callback_data="help:show")],
    ])


def kb_years():
    """لوحة اختيار السنة"""
    lessons = load_lessons()
    if not lessons:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ لا توجد دروس مضافة بعد", callback_data="home")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
        ])
    kb = [
        [InlineKeyboardButton(year, callback_data=f"year:{i}")]
        for i, year in enumerate(lessons.keys())
    ]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def kb_specs(year: str):
    """لوحة اختيار التخصص"""
    lessons = load_lessons()
    kb = [
        [InlineKeyboardButton(spec, callback_data=f"spec:{i}")]
        for i, spec in enumerate(lessons[year].keys())
    ]
    kb += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="go:years")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


def kb_sems(year: str, spec: str):
    """لوحة اختيار السداسي"""
    lessons = load_lessons()
    kb = [
        [InlineKeyboardButton(sem, callback_data=f"sem:{i}")]
        for i, sem in enumerate(lessons[year][spec].keys())
    ]
    kb += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="go:specs")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


def kb_subjects(year: str, spec: str, sem: str):
    """لوحة اختيار المادة مع عدد الدروس"""
    lessons  = load_lessons()
    subjects = lessons[year][spec][sem]
    kb = []
    for i, (name, items) in enumerate(subjects.items()):
        # إظهار عدد الدروس إن وُجدت
        label = f"{name}  ·  {len(items)} 📄" if items else name
        kb.append([InlineKeyboardButton(label, callback_data=f"subj:{i}")])
    kb += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="go:sems")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


def kb_files(items: list):
    """لوحة قائمة الدروس (ملفات أو روابط)"""
    kb = []
    for i, (title, value) in enumerate(items):
        if is_url(value):
            kb.append([InlineKeyboardButton(f"🔗 {title}", url=value)])
        else:
            kb.append([InlineKeyboardButton(f"📄 {title}", callback_data=f"file:{i}")])
    kb += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="go:subjects")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


def kb_back(target: str):
    """لوحة رجوع بسيطة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ رجوع",     callback_data=target)],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])


# ════════════════════════════════════════════════════════════════
#  النصوص الثابتة
# ════════════════════════════════════════════════════════════════

TEXT_WELCOME = (
    "السلام عليكم ورحمة الله وبركاته 🌿\n\n"
    "أهلاً بك في *البوت المساعد لطالب الشريعة*\n"
    "جامعة البشير الإبراهيمي 🕌\n\n"
    "📚 تصفّح الدروس بسهولة\n"
    "📝 اختبارات قصيرة مع نقاط وإنجازات\n"
    "🗓️ تقويم جامعي محدَّث\n"
    "✍️ أرسل سؤالك وسيجيبك المشرفون"
)

TEXT_HELP = (
    "❓ *دليل الاستخدام*\n\n"
    "📚 *الدروس*\n"
    "اضغط «الدروس» ثم تنقّل:\n"
    "السنة ← التخصص ← السداسي ← المادة ← الدرس\n\n"
    "📝 *الاختبار القصير*\n"
    "أسئلة عشوائية — كل إجابة صحيحة تمنحك نقاطاً\n\n"
    "🏆 *نقاطي*\n"
    "اعرض نقاطك وإنجازاتك وترتيبك بين الطلاب\n\n"
    "🗓️ *التقويم الجامعي*\n"
    "مواعيد الامتحانات، العطل، وآخر الآجال\n\n"
    "✍️ *سؤال للمشرفين*\n"
    "أرسل أي رسالة هنا في الخاص\n\n"
    "⏰ *رسائل يومية تلقائية*\n"
    "   07:00 — أذكار الصباح\n"
    "   10:00 — ورد اليوم\n"
    "   17:00 — أذكار المساء\n"
    "   20:00 — حديث اليوم"
)

TEXT_ADMIN_HELP = (
    "🛠️ *أوامر المشرف*\n\n"

    "━━━ 📚 إدارة الدروس ━━━\n"
    "➕ *إضافة PDF* (اعمل Reply على الملف):\n"
    "`/adddars السنة | التخصص | السداسي | المادة | العنوان`\n\n"
    "➕ *إضافة رابط:*\n"
    "`/adddars السنة | التخصص | السداسي | المادة | العنوان | https://...`\n\n"
    "📋 *عرض دروس مادة:*\n"
    "`/listdars السنة | التخصص | السداسي | المادة`\n\n"
    "🗑️ *حذف درس:*\n"
    "`/deldars السنة | التخصص | السداسي | المادة | رقم`\n\n"

    "━━━ 📝 إدارة الكويز ━━━\n"
    "➕ *إضافة سؤال:*\n"
    "`/addquiz السؤال | خ1 | خ2 | خ3 | خ4 | رقم_الصحيح | نقاط`\n"
    "_(رقم_الصحيح من 1 إلى 4)_\n\n"
    "📋 *عرض الأسئلة:* `/listquiz`\n"
    "🗑️ *حذف سؤال:* `/delquiz رقم`\n\n"

    "━━━ 📢 إدارة عامة ━━━\n"
    "📊 *إحصائيات:* `/stats`\n"
    "📢 *بث رسالة:*\n"
    "   `/broadcast النص`\n"
    "   أو Reply على رسالة + `/broadcast`\n"
    "🗓️ *تحديث التقويم:*\n"
    "   `/setcal القسم | النص`\n\n"

    "━━━ 🔧 متنوعة ━━━\n"
    "🏓 `/ping` — اختبار البوت\n"
    "📎 أرسل PDF في الخاص للحصول على file\\_id"
)


# ════════════════════════════════════════════════════════════════
#  أوامر المستخدم
# ════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — الصفحة الرئيسية"""
    if update.effective_chat.type == "private":
        register_user(update.effective_chat.id)
    _nav_reset(context)
    await update.message.reply_text(
        TEXT_WELCOME,
        reply_markup=kb_main(),
        parse_mode="Markdown"
    )


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ping — اختبار البوت"""
    now = datetime.now(TZ).strftime("%H:%M:%S")
    await update.message.reply_text(
        f"🏓 البوت يعمل بشكل طبيعي ✅\n"
        f"🕐 {now} (توقيت الجزائر)"
    )


async def cmd_adminhelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/adminhelp — أوامر المشرف"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text(TEXT_ADMIN_HELP, parse_mode="Markdown")


# ════════════════════════════════════════════════════════════════
#  إحصائيات المشرف
# ════════════════════════════════════════════════════════════════

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats — إحصائيات البوت (للمشرفين)"""
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        return

    users   = load_users()
    lessons = load_lessons()
    quiz    = load_quiz()
    points  = load_points()

    # أعلى 3 طلاب نقاطاً
    top3 = sorted(
        [(uid, d.get("points", 0)) for uid, d in points.items()],
        key=lambda x: x[1],
        reverse=True
    )[:3]
    top_text = "\n".join(
        f"  {r + 1}. `{uid}` — {pts} نقطة"
        for r, (uid, pts) in enumerate(top3)
    ) or "  لا توجد بيانات بعد"

    await update.message.reply_text(
        "📊 *إحصائيات البوت*\n\n"
        f"👥 الطلاب المسجلون : *{len(users)}*\n"
        f"📚 إجمالي الدروس   : *{count_lessons(lessons)}*\n"
        f"📝 أسئلة الكويز    : *{len(quiz)}*\n"
        f"🏆 الطلاب النشطون  : *{len(points)}*\n\n"
        f"🥇 *أعلى الطلاب:*\n{top_text}",
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════
#  إدارة الدروس — الأوامر
# ════════════════════════════════════════════════════════════════

async def cmd_adddars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/adddars — إضافة درس جديد"""
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        if msg:
            await msg.reply_text("❌ ليس لديك صلاحية.")
        return

    raw   = (msg.text or "").replace("/adddars", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]

    # البحث عن ملف PDF في الرسالة المردود عليها
    doc = getattr(msg.reply_to_message, "document", None) if msg.reply_to_message else None

    if len(parts) == 5:
        # إضافة PDF
        year, spec, sem, subject, title = parts
        if not doc:
            await msg.reply_text(
                "⚠️ *لم أجد ملف PDF!*\n\n"
                "الطريقة الصحيحة:\n"
                "١. أرسل ملف PDF للبوت\n"
                "٢. اعمل *Reply* على الملف\n"
                "٣. اكتب الأمر:\n"
                "`/adddars السنة | التخصص | السداسي | المادة | العنوان`",
                parse_mode="Markdown"
            )
            return
        value = doc.file_id

    elif len(parts) == 6:
        # إضافة رابط
        year, spec, sem, subject, title, url = parts
        if not is_url(url):
            await msg.reply_text("⚠️ الرابط يجب أن يبدأ بـ https://")
            return
        value = url

    else:
        await msg.reply_text(
            "⚠️ *صيغة خاطئة!*\n"
            "اكتب /adminhelp للتعليمات الكاملة.",
            parse_mode="Markdown"
        )
        return

    # الإضافة للبيانات
    lessons = load_lessons()
    (lessons
     .setdefault(year, {})
     .setdefault(spec, {})
     .setdefault(sem, {})
     .setdefault(subject, [])
     .append([title, value]))
    save_lessons(lessons)

    kind = "🔗 رابط" if is_url(value) else "📄 PDF"
    await msg.reply_text(
        f"✅ *تمت الإضافة بنجاح!*\n\n"
        f"📚 {year} ← {spec}\n"
        f"📅 {sem} ← {subject}\n"
        f"{kind}: *{title}*",
        parse_mode="Markdown"
    )


async def cmd_listdars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/listdars — عرض دروس مادة معينة"""
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        return

    raw   = (msg.text or "").replace("/listdars", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) != 4:
        await msg.reply_text(
            "الصيغة:\n`/listdars السنة | التخصص | السداسي | المادة`",
            parse_mode="Markdown"
        )
        return

    year, spec, sem, subject = parts
    try:
        items = load_lessons()[year][spec][sem][subject]
    except KeyError:
        await msg.reply_text("⚠️ المسار غير موجود. تحقق من الأسماء.")
        return

    if not items:
        await msg.reply_text(
            f"📭 لا توجد دروس في مادة *{subject}* بعد.",
            parse_mode="Markdown"
        )
        return

    lines = [f"📚 *دروس {subject} ({len(items)}):*\n"]
    for i, item in enumerate(items, 1):
        icon = "🔗" if is_url(item[1]) else "📄"
        lines.append(f"{i}. {icon} {item[0]}")
    lines.append(f"\n🗑️ لحذف درس:\n`/deldars {year} | {spec} | {sem} | {subject} | رقم`")

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_deldars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deldars — حذف درس"""
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        return

    raw   = (msg.text or "").replace("/deldars", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) != 5:
        await msg.reply_text(
            "الصيغة:\n`/deldars السنة | التخصص | السداسي | المادة | رقم`",
            parse_mode="Markdown"
        )
        return

    year, spec, sem, subject, idx_s = parts
    try:
        idx = int(idx_s) - 1
        assert idx >= 0
    except (ValueError, AssertionError):
        await msg.reply_text("⚠️ الرقم يجب أن يكون رقماً صحيحاً موجباً.")
        return

    lessons = load_lessons()
    try:
        items = lessons[year][spec][sem][subject]
    except KeyError:
        await msg.reply_text("⚠️ المسار غير موجود.")
        return

    if idx >= len(items):
        await msg.reply_text(f"⚠️ رقم خارج النطاق. المادة تحتوي على {len(items)} درس.")
        return

    removed = items.pop(idx)
    save_lessons(lessons)
    await msg.reply_text(
        f"✅ تم حذف الدرس:\n*{removed[0]}*",
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════
#  إدارة الكويز — الأوامر
# ════════════════════════════════════════════════════════════════

async def cmd_addquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/addquiz — إضافة سؤال جديد"""
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        return

    raw   = (msg.text or "").replace("/addquiz", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) != 7:
        await msg.reply_text(
            "الصيغة:\n"
            "`/addquiz السؤال | خ1 | خ2 | خ3 | خ4 | رقم_الصحيح | نقاط`\n\n"
            "مثال:\n"
            "`/addquiz ما ركن الإسلام الأول؟ | الصلاة | الشهادة | الزكاة | الصوم | 2 | 3`\n\n"
            "_رقم الإجابة الصحيحة: من 1 إلى 4_",
            parse_mode="Markdown"
        )
        return

    q_text, c1, c2, c3, c4, ans_s, pts_s = parts
    try:
        ans = int(ans_s) - 1  # تحويل إلى 0-based
        pts = int(pts_s)
        assert 0 <= ans <= 3 and pts > 0
    except Exception:
        await msg.reply_text("⚠️ رقم الإجابة بين 1 و4، والنقاط رقم موجب.")
        return

    quiz = load_quiz()
    quiz.append({
        "q":       q_text,
        "choices": [c1, c2, c3, c4],
        "answer":  ans,
        "points":  pts,
    })
    save_quiz(quiz)

    await msg.reply_text(
        f"✅ *تمت الإضافة!*\n\n"
        f"❓ {q_text}\n"
        f"✅ الإجابة الصحيحة: *{[c1, c2, c3, c4][ans]}*\n"
        f"⭐ النقاط: {pts}",
        parse_mode="Markdown"
    )


async def cmd_listquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/listquiz — عرض أسئلة الكويز"""
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        return

    quiz = load_quiz()
    if not quiz:
        await msg.reply_text("لا توجد أسئلة بعد.")
        return

    lines = [f"📝 *أسئلة الكويز ({len(quiz)}):*\n"]
    for i, q in enumerate(quiz, 1):
        correct = q["choices"][q["answer"]]
        lines.append(f"{i}. {q['q']}\n   ✅ {correct}  ·  ⭐{q['points']}")
    lines.append("\n🗑️ `/delquiz رقم` لحذف سؤال")

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_delquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/delquiz — حذف سؤال"""
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        return

    raw = (msg.text or "").replace("/delquiz", "", 1).strip()
    try:
        idx = int(raw) - 1
        assert idx >= 0
    except Exception:
        await msg.reply_text("الصيغة: `/delquiz رقم`", parse_mode="Markdown")
        return

    quiz = load_quiz()
    if idx >= len(quiz):
        await msg.reply_text(f"⚠️ رقم خارج النطاق. يوجد {len(quiz)} سؤال.")
        return

    removed = quiz.pop(idx)
    save_quiz(quiz)
    await msg.reply_text(
        f"✅ تم حذف السؤال:\n*{removed['q']}*",
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════
#  إدارة التقويم
# ════════════════════════════════════════════════════════════════

async def cmd_setcal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setcal — تحديث قسم في التقويم"""
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    txt = (update.message.text or "").replace("/setcal", "", 1).strip()
    if "|" not in txt:
        await update.message.reply_text(
            "الصيغة:\n`/setcal القسم | النص`\n\n"
            "مثال:\n`/setcal 📖 ورد اليوم | سورة الكهف الآيات 1-10`",
            parse_mode="Markdown"
        )
        return

    section, value = [x.strip() for x in txt.split("|", 1)]
    cal = load_calendar()
    cal[section] = value
    save_calendar(cal)
    await update.message.reply_text(
        f"✅ تم تحديث: *{section}*",
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════
#  البث للجميع
# ════════════════════════════════════════════════════════════════

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/broadcast — بث رسالة لجميع الطلاب"""
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    try:
        member = await context.bot.get_chat_member(ADMIN_CHAT_ID, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
            return
    except Exception:
        await update.message.reply_text("❌ تعذّر التحقق من الصلاحيات.")
        return

    users = load_users()
    if not users:
        await update.message.reply_text("⚠️ لا يوجد طلاب مسجلون بعد.")
        return

    ok = bad = 0
    dead = set()

    if context.args:
        # بث نص مكتوب
        text = " ".join(context.args)
        for uid in list(users):
            try:
                await context.bot.send_message(
                    uid, f"📢 *إعلان:*\n\n{text}", parse_mode="Markdown"
                )
                ok += 1
            except Forbidden:
                dead.add(uid); bad += 1
            except Exception:
                bad += 1

    elif update.message.reply_to_message:
        # بث رسالة موجودة
        src = update.message.reply_to_message
        for uid in list(users):
            try:
                await context.bot.copy_message(uid, ADMIN_CHAT_ID, src.message_id)
                ok += 1
            except Forbidden:
                dead.add(uid); bad += 1
            except Exception:
                bad += 1
    else:
        await update.message.reply_text(
            "اكتب: `/broadcast النص`\n"
            "أو اعمل Reply على رسالة ثم `/broadcast`",
            parse_mode="Markdown"
        )
        return

    if dead:
        save_users(users - dead)

    await update.message.reply_text(
        f"✅ أُرسلت إلى: *{ok}* طالب\n"
        f"⚠️ فشل/محظور: *{bad}*",
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════
#  الكويز — Callbacks
# ════════════════════════════════════════════════════════════════

async def _show_quiz(q, context: ContextTypes.DEFAULT_TYPE):
    """عرض سؤال كويز جديد"""
    quiz = load_quiz()
    if not quiz:
        await q.message.edit_text(
            "⚠️ لا توجد أسئلة في بنك الكويز بعد.",
            reply_markup=kb_back("home")
        )
        return

    qid  = random.randint(0, len(quiz) - 1)
    item = quiz[qid]
    context.user_data["quiz_qid"] = qid

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(c, callback_data=f"quiz:ans:{qid}:{i}")]
         for i, c in enumerate(item["choices"])]
        + [[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
    )
    await q.message.edit_text(
        f"📝 *اختبار قصير*\n\n{item['q']}",
        reply_markup=kb,
        parse_mode="Markdown"
    )


async def _answer_quiz(q, data: str, update: Update):
    """معالجة إجابة الكويز"""
    parts  = data.split(":")          # quiz:ans:qid:choice
    qid    = int(parts[2])
    choice = int(parts[3])

    quiz = load_quiz()
    if qid >= len(quiz):
        await q.message.edit_text("⚠️ هذا السؤال لم يعد موجوداً.")
        return

    item     = quiz[qid]
    correct  = item["answer"]
    pts      = item.get("points", 1)
    is_right = (choice == correct)

    # تحديث النقاط
    profile             = get_profile(update.effective_user.id)
    profile["points"]   = profile.get("points", 0) + (pts if is_right else 0)
    profile["last_quiz"] = datetime.utcnow().isoformat()
    new_badges          = check_achievements(profile)
    save_profile(update.effective_user.id, profile)

    result = (
        f"✅ إجابة صحيحة! +{pts} نقطة"
        if is_right else
        f"❌ إجابة خاطئة.\n✅ الصحيح: *{item['choices'][correct]}*"
    )
    badge_text = ("\n\n🏆 " + " | ".join(new_badges)) if new_badges else ""

    await q.message.edit_text(
        f"📝 *اختبار قصير*\n\n"
        f"{item['q']}\n\n"
        f"{result}\n"
        f"⭐ نقاطك الآن: *{profile['points']}*"
        f"{badge_text}\n\n"
        "اضغط لسؤال جديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 سؤال جديد", callback_data="quiz:start")],
            [InlineKeyboardButton("🏆 نقاطي",      callback_data="points:show")],
            [InlineKeyboardButton("🏠 الرئيسية",   callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def _show_points(q, update: Update):
    """عرض نقاط وإنجازات الطالب"""
    profile = get_profile(update.effective_user.id)
    badges  = profile.get("badges", [])
    b_text  = "\n".join(f"  {b}" for b in badges) if badges else "  لا توجد إنجازات بعد"

    # حساب الترتيب
    all_pts = sorted(
        load_points().values(),
        key=lambda x: x.get("points", 0),
        reverse=True
    )
    rank = next(
        (i + 1 for i, p in enumerate(all_pts)
         if p.get("points", 0) == profile.get("points", 0)),
        "—"
    )

    await q.message.edit_text(
        f"🏆 *نقاطي وإنجازاتي*\n\n"
        f"⭐ النقاط  : *{profile.get('points', 0)}*\n"
        f"🏅 الترتيب : *{rank}*\n\n"
        f"🎖️ الإنجازات:\n{b_text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 سؤال جديد", callback_data="quiz:start")],
            [InlineKeyboardButton("🏠 الرئيسية",  callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════
#  التقويم — Callbacks
# ════════════════════════════════════════════════════════════════

async def _show_calendar(q):
    """عرض قائمة أقسام التقويم"""
    cal = load_calendar()
    kb  = [[InlineKeyboardButton(k, callback_data=f"cal:item:{k}")] for k in cal]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    await q.message.edit_text(
        "🗓️ *التقويم الجامعي*\nاختر القسم:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )


async def _show_cal_item(q, key: str):
    """عرض محتوى قسم من التقويم"""
    cal = load_calendar()
    await q.message.edit_text(
        f"🗓️ *{key}*\n\n{cal.get(key, 'لا توجد معلومات.')}",
        reply_markup=kb_back("cal:home"),
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════
#  تنقل الدروس — أدوات مساعدة
# ════════════════════════════════════════════════════════════════

def _nav_reset(context: ContextTypes.DEFAULT_TYPE):
    """مسح حالة التنقل في الدروس"""
    for key in ("nav_year", "nav_spec", "nav_sem", "nav_subject", "nav_items"):
        context.user_data.pop(key, None)


async def _show_home(q, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للصفحة الرئيسية"""
    if update.effective_chat.type == "private":
        register_user(update.effective_chat.id)
    _nav_reset(context)
    await q.message.edit_text(
        TEXT_WELCOME,
        reply_markup=kb_main(),
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════
#  الكولباك الرئيسي
# ════════════════════════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع ضغطات الأزرار"""
    q    = update.callback_query
    await q.answer()
    data = q.data

    # ── الرئيسية ──────────────────────────────────────────────
    if data == "home":
        return await _show_home(q, update, context)

    # ── المساعدة ──────────────────────────────────────────────
    if data == "help:show":
        return await q.message.edit_text(
            TEXT_HELP,
            reply_markup=kb_back("home"),
            parse_mode="Markdown"
        )

    # ── الكويز ────────────────────────────────────────────────
    if data == "quiz:start":
        return await _show_quiz(q, context)
    if data.startswith("quiz:ans:"):
        return await _answer_quiz(q, data, update)

    # ── النقاط ────────────────────────────────────────────────
    if data == "points:show":
        return await _show_points(q, update)

    # ── التقويم ───────────────────────────────────────────────
    if data == "cal:home":
        return await _show_calendar(q)
    if data.startswith("cal:item:"):
        return await _show_cal_item(q, data[9:])

    # ── تنقل الدروس ───────────────────────────────────────────
    lessons = load_lessons()

    # -- السنة --
    if data == "go:years":
        _nav_reset(context)
        return await q.message.edit_text(
            "📘 اختر السنة الدراسية:",
            reply_markup=kb_years()
        )

    if data.startswith("year:"):
        idx  = int(data[5:])
        keys = list(lessons.keys())
        if idx >= len(keys):
            return
        year = keys[idx]
        context.user_data["nav_year"] = year
        return await q.message.edit_text(
            f"📙 *{year}*\nاختر التخصص:",
            reply_markup=kb_specs(year),
            parse_mode="Markdown"
        )

    # -- التخصص --
    if data == "go:specs":
        year = context.user_data.get("nav_year")
        if not year:
            return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
        for k in ("nav_spec", "nav_sem", "nav_subject", "nav_items"):
            context.user_data.pop(k, None)
        return await q.message.edit_text(
            f"📙 *{year}*\nاختر التخصص:",
            reply_markup=kb_specs(year),
            parse_mode="Markdown"
        )

    if data.startswith("spec:"):
        idx  = int(data[5:])
        year = context.user_data.get("nav_year")
        if not year:
            return
        keys = list(lessons[year].keys())
        if idx >= len(keys):
            return
        spec = keys[idx]
        context.user_data["nav_spec"] = spec
        return await q.message.edit_text(
            f"📗 *{year} — {spec}*\nاختر السداسي:",
            reply_markup=kb_sems(year, spec),
            parse_mode="Markdown"
        )

    # -- السداسي --
    if data == "go:sems":
        year = context.user_data.get("nav_year")
        spec = context.user_data.get("nav_spec")
        if not (year and spec):
            return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
        for k in ("nav_sem", "nav_subject", "nav_items"):
            context.user_data.pop(k, None)
        return await q.message.edit_text(
            f"📗 *{year} — {spec}*\nاختر السداسي:",
            reply_markup=kb_sems(year, spec),
            parse_mode="Markdown"
        )

    if data.startswith("sem:"):
        idx  = int(data[4:])
        year = context.user_data.get("nav_year")
        spec = context.user_data.get("nav_spec")
        if not (year and spec):
            return
        keys = list(lessons[year][spec].keys())
        if idx >= len(keys):
            return
        sem = keys[idx]
        context.user_data["nav_sem"] = sem
        return await q.message.edit_text(
            f"📚 *{sem}*\nاختر المادة:",
            reply_markup=kb_subjects(year, spec, sem),
            parse_mode="Markdown"
        )

    # -- المادة --
    if data == "go:subjects":
        year = context.user_data.get("nav_year")
        spec = context.user_data.get("nav_spec")
        sem  = context.user_data.get("nav_sem")
        if not (year and spec and sem):
            return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
        for k in ("nav_subject", "nav_items"):
            context.user_data.pop(k, None)
        return await q.message.edit_text(
            f"📚 *{sem}*\nاختر المادة:",
            reply_markup=kb_subjects(year, spec, sem),
            parse_mode="Markdown"
        )

    if data.startswith("subj:"):
        idx  = int(data[5:])
        year = context.user_data.get("nav_year")
        spec = context.user_data.get("nav_spec")
        sem  = context.user_data.get("nav_sem")
        if not (year and spec and sem):
            return
        keys = list(lessons[year][spec][sem].keys())
        if idx >= len(keys):
            return
        subject = keys[idx]
        items   = lessons[year][spec][sem][subject]
        context.user_data["nav_subject"] = subject
        context.user_data["nav_items"]   = items

        if not items:
            return await q.message.edit_text(
                f"📭 لا توجد دروس بعد في مادة *{subject}*",
                reply_markup=kb_back("go:subjects"),
                parse_mode="Markdown"
            )
        return await q.message.edit_text(
            f"📖 *{subject}*\nاختر الدرس:",
            reply_markup=kb_files(items),
            parse_mode="Markdown"
        )

    # -- تحميل ملف --
    if data.startswith("file:"):
        i     = int(data[5:])
        items = context.user_data.get("nav_items", [])
        if not items or not (0 <= i < len(items)):
            return await q.message.reply_text("⚠️ حدث خطأ، أعد فتح المادة من جديد.")
        title, file_id = items[i]
        if is_url(file_id):
            return await q.message.reply_text(f"🔗 {file_id}")
        try:
            await q.message.reply_document(document=file_id, caption=f"📄 {title}")
        except BadRequest:
            await q.message.reply_text(
                "⚠️ لم أستطع إرسال الملف.\n"
                "قد يكون الـ file_id منتهي الصلاحية."
            )
        except Exception:
            await q.message.reply_text("⚠️ حدث خطأ غير متوقع أثناء الإرسال.")


# ════════════════════════════════════════════════════════════════
#  رسائل المحادثات الخاصة
# ════════════════════════════════════════════════════════════════

async def handle_private_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل الواردة في المحادثات الخاصة"""
    if update.effective_chat.type != "private":
        return

    msg  = update.message
    user = update.effective_user

    # ── المشرف: عرض file_id تلقائياً عند إرسال PDF ──
    if user.id in ADMIN_IDS:
        if msg and msg.document:
            fid = msg.document.file_id
            await msg.reply_text(
                f"📎 *file\_id للملف:*\n`{fid}`\n\n"
                "لإضافته كدرس، اعمل *Reply* على الملف واكتب:\n"
                "`/adddars السنة | التخصص | السداسي | المادة | العنوان`\n\n"
                "💡 /adminhelp لقائمة جميع الأوامر",
                parse_mode="Markdown"
            )
        return

    # ── الطالب: توجيه السؤال للمشرفين ──
    register_user(update.effective_chat.id)

    try:
        meta = await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"📩 *سؤال جديد من طالب*\n\n"
            f"👤 الاسم : {user.full_name}\n"
            f"🆔 ID    : `{user.id}`\n\n"
            "↩️ اعمل *Reply* على هذه الرسالة للرد على الطالب",
            parse_mode="Markdown"
        )
        copied = await context.bot.copy_message(
            chat_id=ADMIN_CHAT_ID,
            from_chat_id=update.effective_chat.id,
            message_id=msg.message_id,
            reply_to_message_id=meta.message_id
        )
        m = load_map()
        m[str(meta.message_id)]   = update.effective_chat.id
        m[str(copied.message_id)] = update.effective_chat.id
        save_map(m)
        await msg.reply_text(
            "✅ وصلت رسالتك للمشرفين.\n"
            "سيردّون عليك بإذن الله 🌿"
        )
    except Exception as e:
        print(f"⚠️ خطأ في توجيه رسالة الطالب: {e}")
        await msg.reply_text("⚠️ حدث خطأ في الإرسال، حاول مجدداً.")


# ════════════════════════════════════════════════════════════════
#  ردود المشرفين على الطلاب
# ════════════════════════════════════════════════════════════════

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """توجيه ردود المشرفين إلى الطلاب"""
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    msg = update.message
    if not msg or not msg.reply_to_message:
        return

    m   = load_map()
    sid = m.get(str(msg.reply_to_message.message_id))
    if not sid:
        return

    try:
        if msg.text:
            await context.bot.send_message(
                sid,
                f"📩 *رد من المشرفين:*\n\n{msg.text}",
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(sid, "📩 *رد من المشرفين:*", parse_mode="Markdown")
            await context.bot.copy_message(
                chat_id=sid,
                from_chat_id=ADMIN_CHAT_ID,
                message_id=msg.message_id
            )
    except Exception as e:
        print(f"⚠️ خطأ في إرسال الرد للطالب: {e}")


# ════════════════════════════════════════════════════════════════
#  بناء التطبيق
# ════════════════════════════════════════════════════════════════

def build_app() -> Application:
    """بناء وإعداد تطبيق البوت"""
    token = _clean(os.environ.get("BOT_TOKEN", ""))
    if not token:
        raise RuntimeError(
            "❌ BOT_TOKEN غير موجود!\n"
            "أضفه في متغيرات البيئة على Render."
        )

    app = (
        Application.builder()
        .token(token)
        .post_init(on_startup)
        .build()
    )

    # ── أوامر عامة ──
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ping",      cmd_ping))
    app.add_handler(CommandHandler("adminhelp", cmd_adminhelp))

    # ── أوامر إدارة الدروس ──
    app.add_handler(CommandHandler("adddars",  cmd_adddars))
    app.add_handler(CommandHandler("listdars", cmd_listdars))
    app.add_handler(CommandHandler("deldars",  cmd_deldars))

    # ── أوامر إدارة الكويز ──
    app.add_handler(CommandHandler("addquiz",  cmd_addquiz))
    app.add_handler(CommandHandler("listquiz", cmd_listquiz))
    app.add_handler(CommandHandler("delquiz",  cmd_delquiz))

    # ── أوامر مجموعة المشرفين فقط ──
    app.add_handler(CommandHandler("stats",     cmd_stats,     filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("setcal",    cmd_setcal,    filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast, filters=filters.Chat(ADMIN_CHAT_ID)))

    # ── معالجات الأحداث ──
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(
        filters.Chat(ADMIN_CHAT_ID) & ~filters.COMMAND,
        handle_admin_reply
    ))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_private_msg
    ))

    return app


if __name__ == "__main__":
    build_app().run_polling()
