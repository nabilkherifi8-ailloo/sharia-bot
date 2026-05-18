# =============================================================
#  bot.py  —  البوت المساعد لطالب الشريعة
#  جامعة البشير الإبراهيمي
# =============================================================

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


# =============================================================
#  الإعدادات الأساسية
# =============================================================
ADMIN_CHAT_ID   = -5286458958
ADMIN_USER_IDS  = {1490829295}

MAP_FILE        = "msg_map.json"
USERS_FILE      = "users.json"
POINTS_FILE     = "points.json"
CAL_FILE        = "calendar.json"
LESSONS_FILE    = "lessons_data.json"
QUIZ_FILE       = "quiz_data.json"
SCHED_FILE      = "schedule_state.json"

TZ = ZoneInfo("Africa/Algiers")


# =============================================================
#  أسئلة الكويز الافتراضية
# =============================================================
DEFAULT_QUIZ = [
    {"q": "عدد أركان الإسلام؟",
     "choices": ["3", "4", "5", "6"], "answer": 2, "points": 2},
    {"q": "النية محلها؟",
     "choices": ["اللسان", "القلب", "اليد", "العين"], "answer": 1, "points": 2},
    {"q": "وقت صلاة الفجر ينتهي بـ؟",
     "choices": ["طلوع الشمس", "الزوال", "غروب الشمس", "منتصف الليل"], "answer": 0, "points": 2},
    {"q": "حكم الوضوء للصلاة؟",
     "choices": ["سنة", "واجب", "مكروه", "مباح"], "answer": 1, "points": 2},
    {"q": "كم عدد سور القرآن الكريم؟",
     "choices": ["110", "114", "120", "100"], "answer": 1, "points": 2},
    {"q": "أول سورة نزلت من القرآن الكريم؟",
     "choices": ["الفاتحة", "البقرة", "العلق", "المدثر"], "answer": 2, "points": 3},
]

ACHIEVEMENTS = [
    (10,  "🥉 مجتهد — 10 نقاط"),
    (25,  "🥈 متفوق — 25 نقاط"),
    (50,  "🥇 نجم الشريعة — 50 نقطة"),
    (100, "🏅 حافظ — 100 نقطة"),
]


# =============================================================
#  أدوات JSON
# =============================================================
def _clean(s: str) -> str:
    return "".join(str(s).strip().split()) if s else ""

def _load(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _save(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_url(s: str) -> bool:
    return isinstance(s, str) and (s.startswith("http://") or s.startswith("https://"))


# =============================================================
#  الدروس
# =============================================================
def load_lessons() -> dict:
    if os.path.exists(LESSONS_FILE):
        data = _load(LESSONS_FILE, None)
        if isinstance(data, dict) and data:
            return data
    try:
        from lessons import LESSONS as _DEF
        data = copy.deepcopy(_DEF)
        _save(LESSONS_FILE, data)
        return data
    except Exception as e:
        print(f"⚠️ load_lessons error: {e}")
        return {}

def save_lessons(data: dict):
    _save(LESSONS_FILE, data)

def lessons_count(data: dict) -> int:
    total = 0
    for yr in data.values():
        for sp in yr.values():
            for sm in sp.values():
                for items in sm.values():
                    total += len(items)
    return total


# =============================================================
#  الكويز
# =============================================================
def load_quiz() -> list:
    data = _load(QUIZ_FILE, None)
    if isinstance(data, list) and data:
        return data
    _save(QUIZ_FILE, DEFAULT_QUIZ)
    return copy.deepcopy(DEFAULT_QUIZ)

def save_quiz(data: list):
    _save(QUIZ_FILE, data)


# =============================================================
#  المستخدمون
# =============================================================
def load_users() -> set:
    data = _load(USERS_FILE, [])
    try:
        return set(int(x) for x in data)
    except Exception:
        return set()

def save_users(users: set):
    _save(USERS_FILE, sorted(list(users)))

def add_user(chat_id: int):
    users = load_users()
    if int(chat_id) not in users:
        users.add(int(chat_id))
        save_users(users)


# =============================================================
#  النقاط
# =============================================================
def load_points() -> dict:
    return _load(POINTS_FILE, {})

def save_points(p: dict):
    _save(POINTS_FILE, p)

def get_profile(user_id: int) -> dict:
    p   = load_points()
    key = str(user_id)
    if key not in p:
        p[key] = {"points": 0, "badges": [], "last_quiz": None}
        save_points(p)
    return p[key]

def set_profile(user_id: int, profile: dict):
    p = load_points()
    p[str(user_id)] = profile
    save_points(p)


# =============================================================
#  التقويم
# =============================================================
def _default_calendar() -> dict:
    return {
        "📌 مواعيد الامتحانات": "لم يتم تحديد المواعيد بعد.",
        "🏖️ العطل الرسمية":    "لم يتم تحديد العطل بعد.",
        "⏳ آخر الآجال":        "لم يتم تحديد الآجال بعد.",
    }

def load_calendar() -> dict:
    cal = _load(CAL_FILE, None)
    if not isinstance(cal, dict) or not cal:
        cal = _default_calendar()
        _save(CAL_FILE, cal)
    return cal

def save_calendar(cal: dict):
    _save(CAL_FILE, cal)


# =============================================================
#  الجدولة
# =============================================================
def load_sched() -> dict:
    st = _load(SCHED_FILE, {})
    return st if isinstance(st, dict) else {}

def save_sched(st: dict):
    _save(SCHED_FILE, st)

def load_map() -> dict:
    return _load(MAP_FILE, {})

def save_map(m: dict):
    _save(MAP_FILE, m)


# =============================================================
#  البث للجميع
# =============================================================
async def broadcast_all(bot, text: str):
    users = load_users()
    dead  = set()
    for uid in list(users):
        try:
            await bot.send_message(chat_id=uid, text=text)
        except Forbidden:
            dead.add(uid)
        except Exception:
            pass
    if dead:
        save_users(users - dead)


# =============================================================
#  الجدولة اليومية
# =============================================================
async def scheduler_loop(app: Application):
    FIXED = [
        (7,  0,  "morning", "🌿 *أذكار الصباح*\n\nاللهم بك أصبحنا وبك أمسينا وبك نحيا وبك نموت وإليك النشور.\nأصبحنا وأصبح الملك لله والحمد لله لا شريك له."),
        (17, 0,  "evening", "🌙 *أذكار المساء*\n\nاللهم بك أمسينا وبك أصبحنا وبك نحيا وبك نموت وإليك المصير.\nأمسينا وأمسى الملك لله والحمد لله لا شريك له."),
    ]
    CAL_MSGS = [
        (10, 0, "wird",   "📖 ورد اليوم"),
        (20, 0, "hadith", "📜 حديث اليوم"),
    ]
    while True:
        try:
            now   = datetime.now(TZ)
            today = now.date().isoformat()
            st    = load_sched()
            if today not in st:
                st[today] = {}
            sent = st[today]

            for hour, minute, key, text in FIXED:
                if now.hour == hour and now.minute == minute and not sent.get(key):
                    await broadcast_all(app.bot, text)
                    sent[key] = True
                    save_sched(st)

            for hour, minute, key, cal_key in CAL_MSGS:
                if now.hour == hour and now.minute == minute and not sent.get(key):
                    cal  = load_calendar()
                    body = cal.get(cal_key)
                    text = f"{cal_key}\n\n{body}" if body else f"{cal_key}\n\nلم يتم الضبط بعد."
                    await broadcast_all(app.bot, text)
                    sent[key] = True
                    save_sched(st)

        except Exception:
            pass
        await asyncio.sleep(30)


async def post_init(app: Application):
    app.create_task(scheduler_loop(app))


# =============================================================
#  لوحات المفاتيح
# =============================================================
def kb_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 الدروس",           callback_data="nav:years")],
        [InlineKeyboardButton("📝 اختبار قصير",      callback_data="quiz:start"),
         InlineKeyboardButton("🏆 نقاطي",            callback_data="me:points")],
        [InlineKeyboardButton("🗓️ التقويم الجامعي",  callback_data="cal:home")],
        [InlineKeyboardButton("❓ مساعدة",            callback_data="help:show")],
    ])


def kb_years():
    lessons = load_lessons()
    if not lessons:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ لا توجد بيانات بعد", callback_data="home")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
        ])
    kb = [
        [InlineKeyboardButton(y, callback_data=f"y:{i}")]
        for i, y in enumerate(lessons.keys())
    ]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def kb_specs(year: str):
    lessons = load_lessons()
    kb = [
        [InlineKeyboardButton(s, callback_data=f"sp:{i}")]
        for i, s in enumerate(lessons[year].keys())
    ]
    kb += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="nav:years")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


def kb_sems(year: str, spec: str):
    lessons = load_lessons()
    kb = [
        [InlineKeyboardButton(s, callback_data=f"se:{i}")]
        for i, s in enumerate(lessons[year][spec].keys())
    ]
    kb += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="nav:specs")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


def kb_subjects(year: str, spec: str, sem: str):
    lessons  = load_lessons()
    subjects = lessons[year][spec][sem]
    kb = []
    for i, (name, items) in enumerate(subjects.items()):
        label = f"{name}  ({len(items)} 📄)" if items else name
        kb.append([InlineKeyboardButton(label, callback_data=f"su:{i}")])
    kb += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="nav:sems")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


def kb_lessons(items: list):
    kb = []
    for i, (title, value) in enumerate(items):
        icon = "🔗" if is_url(value) else "📄"
        if is_url(value):
            kb.append([InlineKeyboardButton(f"{icon} {title}", url=value)])
        else:
            kb.append([InlineKeyboardButton(f"{icon} {title}", callback_data=f"file:{i}")])
    kb += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="nav:subjects")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


# =============================================================
#  النصوص الثابتة
# =============================================================
WELCOME = (
    "السلام عليكم ورحمة الله وبركاته 🌿\n\n"
    "مرحباً بك في *البوت المساعد لطالب الشريعة*\n"
    "جامعة البشير الإبراهيمي 🕌\n\n"
    "📚 تصفّح الدروس عبر الأزرار\n"
    "📝 اختبارات قصيرة مع نقاط وإنجازات\n"
    "🗓️ التقويم الجامعي محدّث دائماً\n"
    "✍️ أرسل سؤالك وسيردّ عليك المشرفون"
)

HELP_TEXT = (
    "❓ *كيف أستخدم البوت؟*\n\n"
    "📚 *الدروس* — اضغط «الدروس» ثم اختر:\n"
    "   السنة ← التخصص ← السداسي ← المادة\n\n"
    "📝 *الاختبار* — أسئلة عشوائية تكسب نقاطاً\n\n"
    "🏆 *نقاطي* — عرض نقاطك وإنجازاتك وترتيبك\n\n"
    "🗓️ *التقويم* — مواعيد الامتحانات والعطل\n\n"
    "✍️ *سؤال للمشرفين* — أرسل أي رسالة في الخاص\n\n"
    "⏰ *رسائل يومية تلقائية:*\n"
    "   07:00 أذكار الصباح\n"
    "   10:00 ورد اليوم\n"
    "   17:00 أذكار المساء\n"
    "   20:00 حديث اليوم"
)

ADMIN_HELP = (
    "🛠️ *أوامر المشرف*\n\n"
    "━━━ 📚 الدروس ━━━\n"
    "➕ إضافة PDF *(Reply على الملف)*:\n"
    "`/adddars السنة | التخصص | السداسي | المادة | العنوان`\n\n"
    "➕ إضافة رابط:\n"
    "`/adddars السنة | التخصص | السداسي | المادة | العنوان | https://...`\n\n"
    "📋 عرض دروس مادة:\n"
    "`/listdars السنة | التخصص | السداسي | المادة`\n\n"
    "🗑️ حذف درس:\n"
    "`/deldars السنة | التخصص | السداسي | المادة | رقم`\n\n"
    "━━━ 📝 الكويز ━━━\n"
    "➕ إضافة سؤال:\n"
    "`/addquiz السؤال | خ1 | خ2 | خ3 | خ4 | رقم_الصحيح | نقاط`\n\n"
    "📋 عرض الأسئلة: `/listquiz`\n"
    "🗑️ حذف سؤال: `/delquiz رقم`\n\n"
    "━━━ 📢 عام ━━━\n"
    "📊 إحصائيات: `/stats`\n"
    "📢 بث: `/broadcast النص` أو Reply + `/broadcast`\n"
    "🗓️ تحديث التقويم: `/setcal القسم | النص`\n"
    "🏓 اختبار: `/ping`\n"
    "📎 file\\_id: أرسل PDF في الخاص"
)


# =============================================================
#  /start
# =============================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        add_user(update.effective_chat.id)
    _reset_nav(context)
    await update.message.reply_text(WELCOME, reply_markup=kb_home(), parse_mode="Markdown")


# =============================================================
#  /ping
# =============================================================
async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ).strftime("%H:%M:%S")
    await update.message.reply_text(f"🏓 البوت يعمل ✅\n🕐 {now} (توقيت الجزائر)")


# =============================================================
#  /adminhelp
# =============================================================
async def cmd_adminhelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USER_IDS:
        return
    await update.message.reply_text(ADMIN_HELP, parse_mode="Markdown")


# =============================================================
#  /stats
# =============================================================
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USER_IDS and update.effective_chat.id != ADMIN_CHAT_ID:
        return
    users   = load_users()
    lessons = load_lessons()
    quiz    = load_quiz()
    points  = load_points()
    top = sorted(
        [(uid, p.get("points", 0)) for uid, p in points.items()],
        key=lambda x: x[1], reverse=True
    )[:3]
    top_text = "\n".join(f"  {r+1}. ID `{uid}` — {pts} نقطة" for r, (uid, pts) in enumerate(top))
    await update.message.reply_text(
        "📊 *إحصائيات البوت*\n\n"
        f"👥 الطلاب المسجلون: *{len(users)}*\n"
        f"📚 إجمالي الدروس: *{lessons_count(lessons)}*\n"
        f"📝 أسئلة الكويز: *{len(quiz)}*\n"
        f"🏆 الطلاب النشطون: *{len(points)}*\n\n"
        f"🥇 *أعلى الطلاب:*\n{top_text or '  لا توجد بيانات بعد'}",
        parse_mode="Markdown"
    )


# =============================================================
#  /adddars
# =============================================================
async def cmd_adddars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if update.effective_user.id not in ADMIN_USER_IDS and update.effective_chat.id != ADMIN_CHAT_ID:
        await msg.reply_text("❌ ليس لديك صلاحية.")
        return

    raw   = (msg.text or "").replace("/adddars", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]

    doc = None
    if msg.reply_to_message and msg.reply_to_message.document:
        doc = msg.reply_to_message.document

    if len(parts) == 5:
        year, spec, sem, subject, title = parts
        if not doc:
            await msg.reply_text(
                "⚠️ لم أجد ملف PDF!\n\n"
                "الطريقة:\n"
                "١. أرسل PDF للبوت\n"
                "٢. اعمل *Reply* على الملف\n"
                "٣. اكتب:\n"
                "`/adddars السنة | التخصص | السداسي | المادة | العنوان`",
                parse_mode="Markdown"
            )
            return
        value = doc.file_id

    elif len(parts) == 6:
        year, spec, sem, subject, title, url = parts
        if not is_url(url):
            await msg.reply_text("⚠️ الرابط يجب أن يبدأ بـ https://")
            return
        value = url

    else:
        await msg.reply_text("⚠️ صيغة غير صحيحة.\nاكتب /adminhelp للتعليمات.")
        return

    lessons = load_lessons()
    lessons.setdefault(year, {}).setdefault(spec, {}).setdefault(sem, {}).setdefault(subject, [])
    lessons[year][spec][sem][subject].append([title, value])
    save_lessons(lessons)

    kind = "🔗 رابط" if is_url(value) else "📄 PDF"
    await msg.reply_text(
        f"✅ *تمت الإضافة!*\n\n"
        f"📚 {year} ← {spec}\n"
        f"📅 {sem} ← {subject}\n"
        f"{kind}: *{title}*",
        parse_mode="Markdown"
    )


# =============================================================
#  /listdars
# =============================================================
async def cmd_listdars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if update.effective_user.id not in ADMIN_USER_IDS and update.effective_chat.id != ADMIN_CHAT_ID:
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
        await msg.reply_text("⚠️ المسار غير موجود.")
        return

    if not items:
        await msg.reply_text(f"📭 لا توجد دروس في *{subject}*", parse_mode="Markdown")
        return

    lines = [f"📚 *دروس {subject}:*\n"]
    for i, item in enumerate(items, 1):
        icon = "🔗" if is_url(item[1]) else "📄"
        lines.append(f"{i}. {icon} {item[0]}")
    lines.append(f"\n🗑️ `/deldars {year} | {spec} | {sem} | {subject} | رقم`")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


# =============================================================
#  /deldars
# =============================================================
async def cmd_deldars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if update.effective_user.id not in ADMIN_USER_IDS and update.effective_chat.id != ADMIN_CHAT_ID:
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
    except ValueError:
        await msg.reply_text("⚠️ الرقم يجب أن يكون رقماً صحيحاً.")
        return

    lessons = load_lessons()
    try:
        items = lessons[year][spec][sem][subject]
    except KeyError:
        await msg.reply_text("⚠️ المسار غير موجود.")
        return

    if idx < 0 or idx >= len(items):
        await msg.reply_text(f"⚠️ رقم غير صحيح. يوجد {len(items)} درس.")
        return

    removed = items.pop(idx)
    save_lessons(lessons)
    await msg.reply_text(f"✅ تم حذف: *{removed[0]}*", parse_mode="Markdown")


# =============================================================
#  /addquiz
# =============================================================
async def cmd_addquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if update.effective_user.id not in ADMIN_USER_IDS and update.effective_chat.id != ADMIN_CHAT_ID:
        return

    raw   = (msg.text or "").replace("/addquiz", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) != 7:
        await msg.reply_text(
            "الصيغة:\n"
            "`/addquiz السؤال | خ1 | خ2 | خ3 | خ4 | رقم_الصحيح | نقاط`\n\n"
            "مثال:\n"
            "`/addquiz ما ركن الإسلام الأول؟ | الصلاة | الشهادة | الزكاة | الصوم | 2 | 3`",
            parse_mode="Markdown"
        )
        return

    q_text, c1, c2, c3, c4, ans_s, pts_s = parts
    try:
        ans = int(ans_s) - 1
        pts = int(pts_s)
        assert 0 <= ans <= 3 and pts > 0
    except Exception:
        await msg.reply_text("⚠️ رقم الإجابة بين 1 و4، والنقاط رقم موجب.")
        return

    quiz = load_quiz()
    quiz.append({"q": q_text, "choices": [c1, c2, c3, c4], "answer": ans, "points": pts})
    save_quiz(quiz)
    await msg.reply_text(
        f"✅ *تمت الإضافة!*\n\n❓ {q_text}\n✅ *{[c1,c2,c3,c4][ans]}*\n⭐ {pts} نقاط",
        parse_mode="Markdown"
    )


# =============================================================
#  /listquiz
# =============================================================
async def cmd_listquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if update.effective_user.id not in ADMIN_USER_IDS and update.effective_chat.id != ADMIN_CHAT_ID:
        return

    quiz = load_quiz()
    if not quiz:
        await msg.reply_text("لا توجد أسئلة بعد.")
        return

    lines = [f"📝 *أسئلة الكويز ({len(quiz)}):*\n"]
    for i, q in enumerate(quiz, 1):
        lines.append(f"{i}. {q['q']}\n   ✅ {q['choices'][q['answer']]} | ⭐{q['points']}")
    lines.append("\n🗑️ `/delquiz رقم` لحذف سؤال")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


# =============================================================
#  /delquiz
# =============================================================
async def cmd_delquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if update.effective_user.id not in ADMIN_USER_IDS and update.effective_chat.id != ADMIN_CHAT_ID:
        return

    raw = (msg.text or "").replace("/delquiz", "", 1).strip()
    try:
        idx = int(raw) - 1
    except ValueError:
        await msg.reply_text("الصيغة: `/delquiz رقم`", parse_mode="Markdown")
        return

    quiz = load_quiz()
    if idx < 0 or idx >= len(quiz):
        await msg.reply_text(f"⚠️ رقم غير صحيح. يوجد {len(quiz)} سؤال.")
        return

    removed = quiz.pop(idx)
    save_quiz(quiz)
    await msg.reply_text(f"✅ تم حذف: *{removed['q']}*", parse_mode="Markdown")


# =============================================================
#  /setcal
# =============================================================
async def cmd_setcal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return
    txt = update.message.text.replace("/setcal", "", 1).strip()
    if "|" not in txt:
        await update.message.reply_text("الصيغة:\n`/setcal القسم | النص`", parse_mode="Markdown")
        return
    section, value = [x.strip() for x in txt.split("|", 1)]
    cal = load_calendar()
    cal[section] = value
    save_calendar(cal)
    await update.message.reply_text(f"✅ تم تحديث *{section}*", parse_mode="Markdown")


# =============================================================
#  /broadcast
# =============================================================
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return
    try:
        member = await context.bot.get_chat_member(ADMIN_CHAT_ID, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ للمشرفين فقط.")
            return
    except Exception:
        await update.message.reply_text("❌ تعذّر التحقق من الصلاحيات.")
        return

    users = load_users()
    if not users:
        await update.message.reply_text("لا يوجد طلاب مسجلون بعد.")
        return

    ok = bad = 0
    dead = set()

    if context.args:
        text = " ".join(context.args)
        for uid in list(users):
            try:
                await context.bot.send_message(uid, f"📢 *إعلان:*\n\n{text}", parse_mode="Markdown")
                ok += 1
            except Forbidden:
                dead.add(uid); bad += 1
            except Exception:
                bad += 1
    elif update.message.reply_to_message:
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
            "اكتب `/broadcast النص`\nأو اعمل Reply على رسالة ثم `/broadcast`",
            parse_mode="Markdown"
        )
        return

    if dead:
        save_users(users - dead)
    await update.message.reply_text(
        f"✅ أُرسل إلى: *{ok}*\n⚠️ فشل: *{bad}*",
        parse_mode="Markdown"
    )


# =============================================================
#  كولباك الكويز
# =============================================================
def _kb_quiz(qid: int, choices: list):
    kb = [[InlineKeyboardButton(c, callback_data=f"quiz:ans|{qid}|{i}")] for i, c in enumerate(choices)]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


async def _quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    quiz = load_quiz()
    if not quiz:
        await q.message.edit_text(
            "⚠️ لا توجد أسئلة بعد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]])
        )
        return
    qid  = random.randint(0, len(quiz) - 1)
    item = quiz[qid]
    context.user_data["quiz_qid"] = qid
    await q.message.edit_text(
        f"📝 *اختبار قصير*\n\n{item['q']}",
        reply_markup=_kb_quiz(qid, item["choices"]),
        parse_mode="Markdown"
    )


async def _quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q              = update.callback_query
    _, qid_s, ch_s = q.data.split("|")
    qid            = int(qid_s)
    choice         = int(ch_s)

    quiz = load_quiz()
    if qid >= len(quiz):
        await q.message.edit_text("⚠️ هذا السؤال لم يعد موجوداً.")
        return

    item     = quiz[qid]
    correct  = item["answer"]
    pts      = item.get("points", 1)
    is_right = (choice == correct)
    gained   = pts if is_right else 0

    profile          = get_profile(update.effective_user.id)
    profile["points"] = profile.get("points", 0) + gained
    profile["last_quiz"] = datetime.utcnow().isoformat()

    badges     = set(profile.get("badges", []))
    new_badges = []
    for threshold, badge in ACHIEVEMENTS:
        if profile["points"] >= threshold and badge not in badges:
            badges.add(badge)
            new_badges.append(badge)
    profile["badges"] = sorted(badges)
    set_profile(update.effective_user.id, profile)

    result = (
        f"✅ إجابة صحيحة! +{gained} نقطة"
        if is_right else
        f"❌ إجابة خاطئة.\n✅ الصحيح: *{item['choices'][correct]}*"
    )
    extra = ("\n\n🏆 " + " | ".join(new_badges)) if new_badges else ""

    await q.message.edit_text(
        f"📝 *اختبار قصير*\n\n{item['q']}\n\n"
        f"{result}\n⭐ نقاطك: *{profile['points']}*{extra}\n\n"
        "اضغط لسؤال جديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 سؤال جديد", callback_data="quiz:start")],
            [InlineKeyboardButton("🏆 نقاطي",      callback_data="me:points")],
            [InlineKeyboardButton("🏠 الرئيسية",   callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def _my_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    profile = get_profile(update.effective_user.id)
    badges  = profile.get("badges", [])
    b_text  = "\n".join(f"  {b}" for b in badges) if badges else "  لا توجد إنجازات بعد"

    all_pts = sorted(load_points().values(), key=lambda x: x.get("points", 0), reverse=True)
    rank    = next(
        (i + 1 for i, p in enumerate(all_pts) if p.get("points", 0) == profile.get("points", 0)),
        "—"
    )
    await q.message.edit_text(
        f"🏆 *نقاطي وإنجازاتي*\n\n"
        f"⭐ النقاط: *{profile.get('points', 0)}*\n"
        f"🏅 الترتيب: *{rank}*\n\n"
        f"🎖️ الإنجازات:\n{b_text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 سؤال جديد", callback_data="quiz:start")],
            [InlineKeyboardButton("🏠 الرئيسية",  callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


# =============================================================
#  كولباك التقويم
# =============================================================
async def _cal_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    cal = load_calendar()
    kb  = [[InlineKeyboardButton(k, callback_data=f"cal:item|{k}")] for k in cal]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    await q.message.edit_text(
        "🗓️ *التقويم الجامعي*\nاختر القسم:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )


async def _cal_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    key = q.data.split("|", 1)[1]
    cal = load_calendar()
    await q.message.edit_text(
        f"🗓️ *{key}*\n\n{cal.get(key, 'لا توجد معلومات.')}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع",     callback_data="cal:home")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


# =============================================================
#  تنقل الدروس
# =============================================================
def _reset_nav(context: ContextTypes.DEFAULT_TYPE):
    for k in ("year", "spec", "sem", "subject", "lesson_items"):
        context.user_data.pop(k, None)


async def _show_home_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_chat.type == "private":
        add_user(update.effective_chat.id)
    _reset_nav(context)
    await q.message.edit_text(WELCOME, reply_markup=kb_home(), parse_mode="Markdown")


# =============================================================
#  الكولباك الرئيسي
# =============================================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data

    lessons = load_lessons()

    # ── الرئيسية ──
    if data == "home":
        return await _show_home_cb(update, context)

    # ── مساعدة ──
    if data == "help:show":
        return await q.message.edit_text(
            HELP_TEXT,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]),
            parse_mode="Markdown"
        )

    # ── كويز ──
    if data == "quiz:start":
        return await _quiz_start(update, context)
    if data.startswith("quiz:ans|"):
        return await _quiz_answer(update, context)
    if data == "me:points":
        return await _my_points(update, context)

    # ── تقويم ──
    if data == "cal:home":
        return await _cal_home(update, context)
    if data.startswith("cal:item|"):
        return await _cal_item(update, context)

    # ── تنقل الدروس ──
    if data in ("nav:years", "years"):
        _reset_nav(context)
        return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())

    if data in ("nav:specs", "back:specs"):
        year = context.user_data.get("year")
        if not year:
            return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
        for k in ("spec", "sem", "subject", "lesson_items"):
            context.user_data.pop(k, None)
        return await q.message.edit_text("📙 اختر التخصص:", reply_markup=kb_specs(year))

    if data in ("nav:sems", "back:sems"):
        year = context.user_data.get("year")
        spec = context.user_data.get("spec")
        if not (year and spec):
            return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
        for k in ("sem", "subject", "lesson_items"):
            context.user_data.pop(k, None)
        return await q.message.edit_text("📗 اختر السداسي:", reply_markup=kb_sems(year, spec))

    if data in ("nav:subjects", "back:subjects"):
        year = context.user_data.get("year")
        spec = context.user_data.get("spec")
        sem  = context.user_data.get("sem")
        if not (year and spec and sem):
            return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
        for k in ("subject", "lesson_items"):
            context.user_data.pop(k, None)
        return await q.message.edit_text("📚 اختر المادة:", reply_markup=kb_subjects(year, spec, sem))

    # ── اختيارات الدروس ──
    if data.startswith("y:"):
        idx  = int(data[2:])
        keys = list(lessons.keys())
        if idx >= len(keys):
            return
        year = keys[idx]
        context.user_data["year"] = year
        return await q.message.edit_text("📙 اختر التخصص:", reply_markup=kb_specs(year))

    if data.startswith("sp:"):
        idx  = int(data[3:])
        year = context.user_data.get("year")
        if not year:
            return
        keys = list(lessons[year].keys())
        if idx >= len(keys):
            return
        spec = keys[idx]
        context.user_data["spec"] = spec
        return await q.message.edit_text("📗 اختر السداسي:", reply_markup=kb_sems(year, spec))

    if data.startswith("se:"):
        idx  = int(data[3:])
        year = context.user_data.get("year")
        spec = context.user_data.get("spec")
        if not (year and spec):
            return
        keys = list(lessons[year][spec].keys())
        if idx >= len(keys):
            return
        sem = keys[idx]
        context.user_data["sem"] = sem
        return await q.message.edit_text("📚 اختر المادة:", reply_markup=kb_subjects(year, spec, sem))

    if data.startswith("su:"):
        idx     = int(data[3:])
        year    = context.user_data.get("year")
        spec    = context.user_data.get("spec")
        sem     = context.user_data.get("sem")
        if not (year and spec and sem):
            return
        keys = list(lessons[year][spec][sem].keys())
        if idx >= len(keys):
            return
        subject = keys[idx]
        items   = lessons[year][spec][sem][subject]
        context.user_data["subject"]      = subject
        context.user_data["lesson_items"] = items

        if not items:
            return await q.message.edit_text(
                f"📭 لا توجد دروس بعد في مادة *{subject}*",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ رجوع",     callback_data="nav:subjects")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ]),
                parse_mode="Markdown"
            )
        return await q.message.edit_text(
            f"📖 *{subject}*\nاختر الدرس:",
            reply_markup=kb_lessons(items),
            parse_mode="Markdown"
        )

    # ── تحميل ملف ──
    if data.startswith("file:"):
        i     = int(data[5:])
        items = context.user_data.get("lesson_items", [])
        if not items or not (0 <= i < len(items)):
            return await q.message.reply_text("⚠️ حدث خطأ، أعد فتح المادة.")
        title, file_id = items[i]
        if is_url(file_id):
            return await q.message.reply_text(f"🔗 {file_id}")
        try:
            await q.message.reply_document(document=file_id, caption=f"📄 {title}")
        except BadRequest:
            await q.message.reply_text("⚠️ الملف غير متاح (file_id منتهي الصلاحية).")
        except Exception:
            await q.message.reply_text("⚠️ حدث خطأ أثناء الإرسال.")


# =============================================================
#  رسائل الخاص
# =============================================================
async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    msg  = update.message
    user = update.effective_user

    # ── المشرف: أعطه file_id تلقائياً ──
    if user.id in ADMIN_USER_IDS:
        if msg and msg.document:
            fid = msg.document.file_id
            await msg.reply_text(
                f"📎 *file\_id:*\n`{fid}`\n\n"
                "لإضافته درساً اعمل *Reply* على الملف واكتب:\n"
                "`/adddars السنة | التخصص | السداسي | المادة | العنوان`",
                parse_mode="Markdown"
            )
        return

    # ── الطالب: أرسل للمشرفين ──
    add_user(update.effective_chat.id)

    meta = await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"📩 *سؤال جديد*\n\n"
        f"👤 {user.full_name}\n"
        f"🆔 `{user.id}`\n\n"
        "↩️ اعمل Reply للرد على الطالب",
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
    await msg.reply_text("✅ وصلت رسالتك للمشرفين.\nسيردّون عليك بإذن الله 🌿")


# =============================================================
#  ردود المشرفين
# =============================================================
async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return
    msg = update.message
    if not msg or not msg.reply_to_message:
        return

    m   = load_map()
    sid = m.get(str(msg.reply_to_message.message_id))
    if not sid:
        return

    if msg.text:
        await context.bot.send_message(sid, f"📩 *رد من المشرفين:*\n\n{msg.text}", parse_mode="Markdown")
    else:
        await context.bot.send_message(sid, "📩 *رد من المشرفين:*", parse_mode="Markdown")
        await context.bot.copy_message(
            chat_id=sid,
            from_chat_id=ADMIN_CHAT_ID,
            message_id=msg.message_id
        )


# =============================================================
#  بناء التطبيق
# =============================================================
def build_app() -> Application:
    token = _clean(os.environ.get("BOT_TOKEN", ""))
    if not token:
        raise RuntimeError("BOT_TOKEN غير موجود في متغيرات البيئة.")

    app = Application.builder().token(token).post_init(post_init).build()

    # أوامر عامة
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ping",      cmd_ping))
    app.add_handler(CommandHandler("adminhelp", cmd_adminhelp))

    # إدارة الدروس
    app.add_handler(CommandHandler("adddars",   cmd_adddars))
    app.add_handler(CommandHandler("listdars",  cmd_listdars))
    app.add_handler(CommandHandler("deldars",   cmd_deldars))

    # إدارة الكويز
    app.add_handler(CommandHandler("addquiz",   cmd_addquiz))
    app.add_handler(CommandHandler("listquiz",  cmd_listquiz))
    app.add_handler(CommandHandler("delquiz",   cmd_delquiz))

    # أوامر المجموعة فقط
    app.add_handler(CommandHandler("stats",     cmd_stats,     filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("setcal",    cmd_setcal,    filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast, filters=filters.Chat(ADMIN_CHAT_ID)))

    # كولباك وRسائل
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Chat(ADMIN_CHAT_ID) & ~filters.COMMAND, handle_admin_reply))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE    & ~filters.COMMAND, handle_private))

    return app


if __name__ == "__main__":
    build_app().run_polling()
