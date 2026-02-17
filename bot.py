import os
import json
import random
from datetime import datetime, date, time

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

from lessons import LESSONS

# ====== إعدادات ======
ADMIN_CHAT_ID = -5286458958          # مجموعة المشرفين
ADMIN_USER_IDS = {1490829295}        # IDs للمشرفين المسموح لهم بـ /getid و أدوات الإدارة

MAP_FILE = "msg_map.json"            # ربط رسائل المجموعة بالطالب للرد
USERS_FILE = "users.json"            # قائمة الطلاب (للبث + سؤال اليوم)
POINTS_FILE = "points.json"          # نقاط/إنجازات
WIRD_FILE = "wird.json"              # ورد/حديث اليوم
PROFILE_FILE = "profiles.json"       # ملف الطالب
QUIZ_FILE = "quiz_bank.json"         # بنك أسئلة الاختبار (قابل للاستيراد)
DAILY_FILE = "daily_question.json"   # حالة سؤال اليوم
STATS_FILE = "stats.json"            # إحصائيات بسيطة


# ====== أدوات مساعدة ======
def _clean(s: str) -> str:
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
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin_user(user_id: int) -> bool:
    return int(user_id) in set(int(x) for x in ADMIN_USER_IDS)


def is_http(s: str) -> bool:
    return isinstance(s, str) and (s.startswith("http://") or s.startswith("https://"))


# ====== تخزين المستخدمين ======
def load_users():
    data = _load_json(USERS_FILE, [])
    try:
        return set(int(x) for x in data)
    except Exception:
        return set()


def save_users(users):
    _save_json(USERS_FILE, sorted(list(users)))


def add_user(chat_id: int):
    users = load_users()
    users.add(int(chat_id))
    save_users(users)


# ====== نقاط/إنجازات ======
ACHIEVEMENTS = [
    (10, "🥉 إنجاز: مجتهد (10 نقاط)"),
    (25, "🥈 إنجاز: متفوق (25 نقطة)"),
    (50, "🥇 إنجاز: نجم الشريعة (50 نقطة)"),
]


def load_points():
    return _load_json(POINTS_FILE, {})  # {"user_id": {"points":0,"badges":[],"last_daily":"YYYY-MM-DD"}}


def save_points(p):
    _save_json(POINTS_FILE, p)


def get_profile_points(user_id: int):
    p = load_points()
    key = str(user_id)
    if key not in p:
        p[key] = {"points": 0, "badges": [], "last_daily": None}
        save_points(p)
    return p[key]


def set_profile_points(user_id: int, obj: dict):
    p = load_points()
    p[str(user_id)] = obj
    save_points(p)


def add_points(user_id: int, amount: int) -> list[str]:
    """يعيد قائمة إنجازات جديدة إن وجدت"""
    obj = get_profile_points(user_id)
    before = int(obj.get("points", 0))
    obj["points"] = before + int(amount)

    badges = set(obj.get("badges", []))
    new_badges = []
    for threshold, badge in ACHIEVEMENTS:
        if obj["points"] >= threshold and badge not in badges:
            badges.add(badge)
            new_badges.append(badge)
    obj["badges"] = sorted(list(badges))

    set_profile_points(user_id, obj)
    return new_badges


# ====== ملف الطالب ======
def load_student_profiles():
    return _load_json(PROFILE_FILE, {})  # {"user_id": {"year":"","spec":"","group":""}}


def save_student_profiles(d):
    _save_json(PROFILE_FILE, d)


def get_student_profile(user_id: int):
    d = load_student_profiles()
    key = str(user_id)
    if key not in d:
        d[key] = {"year": "", "spec": "", "group": ""}
        save_student_profiles(d)
    return d[key]


def set_student_profile(user_id: int, profile: dict):
    d = load_student_profiles()
    d[str(user_id)] = profile
    save_student_profiles(d)


# ====== ورد/حديث اليوم ======
def load_wird():
    # {"wird": "...", "hadith": "...", "updated":"..."}
    obj = _load_json(WIRD_FILE, None)
    if not isinstance(obj, dict):
        obj = {"wird": "لم يتم إضافة ورد اليوم بعد.", "hadith": "لم يتم إضافة حديث اليوم بعد.", "updated": None}
        _save_json(WIRD_FILE, obj)
    return obj


def save_wird(obj: dict):
    obj["updated"] = datetime.utcnow().isoformat()
    _save_json(WIRD_FILE, obj)


# ====== بنك الأسئلة (Quiz) ======
def default_quiz_bank():
    return [
        {
            "q": "عدد أركان الإسلام؟",
            "choices": ["3", "4", "5", "6"],
            "answer": 2,
            "points": 2
        },
        {
            "q": "النية محلها؟",
            "choices": ["اللسان", "القلب", "اليد", "العين"],
            "answer": 1,
            "points": 2
        },
        {
            "q": "وقت صلاة الفجر ينتهي بـ؟",
            "choices": ["طلوع الشمس", "الزوال", "غروب الشمس", "منتصف الليل"],
            "answer": 0,
            "points": 2
        },
    ]


def load_quiz_bank():
    bank = _load_json(QUIZ_FILE, None)
    if not isinstance(bank, list) or not bank:
        bank = default_quiz_bank()
        _save_json(QUIZ_FILE, bank)
    return bank


def save_quiz_bank(bank: list):
    _save_json(QUIZ_FILE, bank)


# ====== سؤال اليوم ======
def load_daily_state():
    # {"date":"YYYY-MM-DD","qid": int, "sent_to":[chat_ids], "answered":{"user_id": true}}
    st = _load_json(DAILY_FILE, None)
    if not isinstance(st, dict):
        st = {"date": None, "qid": None, "sent_to": [], "answered": {}}
        _save_json(DAILY_FILE, st)
    return st


def save_daily_state(st: dict):
    _save_json(DAILY_FILE, st)


# ====== إحصائيات ======
def load_stats():
    st = _load_json(STATS_FILE, None)
    if not isinstance(st, dict):
        st = {"student_messages": 0, "daily_answers": 0, "quiz_answers": 0}
        _save_json(STATS_FILE, st)
    return st


def save_stats(st: dict):
    _save_json(STATS_FILE, st)


# ====== لوحات المفاتيح ======
WELCOME_TEXT = (
    "السلام عليكم ورحمة الله تعالى وبركاته 🌿\n"
    "مرحباً بك في البوت المساعد لطالب الشريعة\n"
    "في جامعة البشير الإبراهيمي 🕌\n\n"
    "📚 الدروس عبر الأزرار\n"
    "🧠 سؤال اليوم + اختبارات + نقاط\n"
    "📖 ورد/حديث اليوم\n"
    "📌 ملف الطالب\n\n"
    "✍️ لإرسال سؤال للمشرفين: أرسل رسالتك هنا في الخاص"
)


def kb_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 الدروس", callback_data="years")],
        [InlineKeyboardButton("🧠 سؤال اليوم", callback_data="daily:show")],
        [InlineKeyboardButton("📝 اختبار سريع", callback_data="quiz:start")],
        [InlineKeyboardButton("📖 ورد/حديث اليوم", callback_data="wird:home")],
        [InlineKeyboardButton("🏆 نقاطي/إنجازاتي", callback_data="me:points")],
        [InlineKeyboardButton("📌 بياناتي", callback_data="me:profile")],
    ])


def kb_years():
    years = list(LESSONS.keys())
    kb = [[InlineKeyboardButton(y, callback_data=f"y:{i}")] for i, y in enumerate(years)]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def kb_specs(year: str):
    specs = list(LESSONS[year].keys())
    kb = [[InlineKeyboardButton(s, callback_data=f"sp:{i}")] for i, s in enumerate(specs)]
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back:years")])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def kb_sems(year: str, spec: str):
    sems = list(LESSONS[year][spec].keys())
    kb = [[InlineKeyboardButton(s, callback_data=f"se:{i}")] for i, s in enumerate(sems)]
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back:specs")])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def kb_subjects(year: str, spec: str, sem: str):
    subs = list(LESSONS[year][spec][sem].keys())
    kb = [[InlineKeyboardButton(s, callback_data=f"su:{i}")] for i, s in enumerate(subs)]
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back:sems")])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def kb_lessons(items):
    kb = []
    for i, (title, value) in enumerate(items):
        if is_http(value):
            kb.append([InlineKeyboardButton(title, url=value)])
        else:
            kb.append([InlineKeyboardButton(title, callback_data=f"file:{i}")])
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back:subjects")])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


# ====== الشاشة الرئيسية ======
async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type == "private":
        add_user(update.effective_chat.id)

    context.user_data.pop("year", None)
    context.user_data.pop("spec", None)
    context.user_data.pop("sem", None)
    context.user_data.pop("subject", None)
    context.user_data.pop("lesson_items", None)

    if update.message:
        await update.message.reply_text(WELCOME_TEXT, reply_markup=kb_home())
    else:
        await update.callback_query.message.edit_text(WELCOME_TEXT, reply_markup=kb_home())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_home(update, context)


# ====== /getid ======
async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    if (not is_admin_user(update.effective_user.id)) and update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if not msg.reply_to_message:
        await msg.reply_text("✅ ارسل ملف PDF ثم اعمل عليه Reply واكتب /getid")
        return

    if msg.reply_to_message.document:
        doc = msg.reply_to_message.document
        await msg.reply_text(
            "✅ هذا هو file_id (انسخه وضعه في lessons.py):\n\n"
            f"`{doc.file_id}`",
            parse_mode="Markdown"
        )
        return

    await msg.reply_text("⚠️ الرسالة التي رددت عليها ليست ملف PDF (Document).")


# ====== لوحة تحكم المشرف ======
def kb_admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 نشر إعلان", callback_data="admin:broadcast_help")],
        [InlineKeyboardButton("🧪 إضافة سؤال اختبار", callback_data="admin:addquiz_help")],
        [InlineKeyboardButton("📦 استيراد أسئلة (JSON)", callback_data="admin:import_help")],
        [InlineKeyboardButton("📖 تحديث ورد/حديث", callback_data="admin:wird_help")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="admin:stats")],
    ])


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return
    await update.message.reply_text("🧱 لوحة تحكم المشرف:", reply_markup=kb_admin_panel())


# ====== ورد/حديث اليوم (زر للطلاب + أوامر للمشرف) ======
async def set_wird(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID and not is_admin_user(update.effective_user.id):
        return
    txt = update.message.text.replace("/setwird", "", 1).strip()
    if not txt:
        return await update.message.reply_text("الصيغة:\n/setwird نص ورد اليوم")
    obj = load_wird()
    obj["wird"] = txt
    save_wird(obj)
    await update.message.reply_text("✅ تم تحديث ورد اليوم.")


async def set_hadith(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID and not is_admin_user(update.effective_user.id):
        return
    txt = update.message.text.replace("/sethadith", "", 1).strip()
    if not txt:
        return await update.message.reply_text("الصيغة:\n/sethadith نص حديث اليوم")
    obj = load_wird()
    obj["hadith"] = txt
    save_wird(obj)
    await update.message.reply_text("✅ تم تحديث حديث اليوم.")


async def wird_home_cb(q):
    obj = load_wird()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 ورد اليوم", callback_data="wird:wird")],
        [InlineKeyboardButton("📜 حديث اليوم", callback_data="wird:hadith")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])
    await q.message.edit_text("📖 ورد/حديث اليوم\nاختر:", reply_markup=kb)


async def wird_show_cb(q, kind: str):
    obj = load_wird()
    text = obj["wird"] if kind == "wird" else obj["hadith"]
    title = "📖 ورد اليوم" if kind == "wird" else "📜 حديث اليوم"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ رجوع", callback_data="wird:home")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])
    await q.message.edit_text(f"{title}\n\n{text}", reply_markup=kb)


# ====== ملف الطالب (الأزرار) ======
def kb_profile_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ ضبط السنة", callback_data="prof:set_year")],
        [InlineKeyboardButton("✏️ ضبط التخصص", callback_data="prof:set_spec")],
        [InlineKeyboardButton("✏️ ضبط المجموعة", callback_data="prof:set_group")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])


async def profile_show_cb(q, user_id: int):
    pr = get_student_profile(user_id)
    year = pr.get("year") or "غير محدد"
    spec = pr.get("spec") or "غير محدد"
    group = pr.get("group") or "غير محدد"
    await q.message.edit_text(
        f"📌 بياناتي\n\n"
        f"📘 السنة: {year}\n"
        f"📙 التخصص: {spec}\n"
        f"👥 المجموعة: {group}\n\n"
        f"يمكنك تعديلها بالأزرار:",
        reply_markup=kb_profile_menu()
    )


def kb_choose_year():
    years = list(LESSONS.keys())
    kb = [[InlineKeyboardButton(y, callback_data=f"prof:year|{y}")] for y in years]
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="me:profile")])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def kb_choose_spec(year: str):
    specs = list(LESSONS.get(year, {}).keys())
    if not specs:
        specs = ["بدون تخصص"]
    kb = [[InlineKeyboardButton(s, callback_data=f"prof:spec|{s}")] for s in specs]
    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="me:profile")])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


# ضبط المجموعة يتم برسالة نصية: نضع Flag في user_data
async def profile_set_group_hint(q):
    q.message  # keep
    await q.message.edit_text(
        "👥 اكتب رقم/اسم مجموعتك الآن (مثال: 01 أو مجموعة A).",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]])
    )


# ====== اختبار سريع + نقاط ======
def kb_quiz_choices(qid: int, choices):
    kb = [[InlineKeyboardButton(c, callback_data=f"quiz:ans|{qid}|{i}")] for i, c in enumerate(choices)]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


async def quiz_start_cb(q, context: ContextTypes.DEFAULT_TYPE):
    bank = load_quiz_bank()
    qid = random.randint(0, len(bank) - 1)
    item = bank[qid]
    context.user_data["quiz_qid"] = qid
    text = "📝 **اختبار سريع**\n\n" + item["q"]
    await q.message.edit_text(text, reply_markup=kb_quiz_choices(qid, item["choices"]), parse_mode="Markdown")


async def quiz_answer_cb(q, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    bank = load_quiz_bank()
    payload = q.data.split(":", 1)[1]  # ans|qid|choice
    _, qid_s, choice_s = payload.split("|")
    qid = int(qid_s)
    choice = int(choice_s)

    if qid < 0 or qid >= len(bank):
        return await q.message.edit_text("⚠️ سؤال غير موجود، أعد المحاولة.")

    item = bank[qid]
    correct = int(item["answer"])
    pts = int(item.get("points", 2))

    stats = load_stats()
    stats["quiz_answers"] = int(stats.get("quiz_answers", 0)) + 1
    save_stats(stats)

    if choice == correct:
        new_badges = add_points(user_id, pts)
        result = f"✅ إجابة صحيحة! +{pts} نقطة"
        extra = ("\n\n🏆 " + "\n🏆 ".join(new_badges)) if new_badges else ""
    else:
        result = f"❌ إجابة خاطئة.\n✅ الصحيح هو: **{item['choices'][correct]}**"
        extra = ""

    me = get_profile_points(user_id)
    text = (
        f"📝 **اختبار سريع**\n\n"
        f"{item['q']}\n\n"
        f"النتيجة: {result}\n"
        f"⭐ نقاطك الآن: **{me.get('points', 0)}**"
        f"{extra}\n\n"
        "اضغط لاختبار جديد:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 اختبار جديد", callback_data="quiz:start")],
        [InlineKeyboardButton("🏆 نقاطي/إنجازاتي", callback_data="me:points")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])
    await q.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


async def my_points_cb(q, user_id: int):
    me = get_profile_points(user_id)
    badges = me.get("badges", [])
    badges_text = "\n".join(badges) if badges else "لا توجد إنجازات بعد."
    text = (
        "🏆 **نقاطي/إنجازاتي**\n\n"
        f"⭐ النقاط: **{me.get('points', 0)}**\n\n"
        f"🎖️ الإنجازات:\n{badges_text}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 اختبار سريع", callback_data="quiz:start")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])
    await q.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


# ====== سؤال اليوم (إرسال تلقائي + زر إجابة) ======
DAILY_POINTS = 3

def kb_daily(qid: int, choices):
    kb = [[InlineKeyboardButton(c, callback_data=f"daily:ans|{qid}|{i}")] for i, c in enumerate(choices)]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)

async def daily_send_job(context: ContextTypes.DEFAULT_TYPE):
    """يُرسل سؤال اليوم مرة واحدة يوميًا لكل الطلاب"""
    users = load_users()
    if not users:
        return

    bank = load_quiz_bank()
    if not bank:
        return

    today = date.today().isoformat()
    st = load_daily_state()

    # لو أرسلنا اليوم بالفعل، لا نكرر
    if st.get("date") == today and st.get("qid") is not None:
        return

    qid = random.randint(0, len(bank) - 1)
    item = bank[qid]

    st = {"date": today, "qid": qid, "sent_to": [], "answered": {}}
    save_daily_state(st)

    text = "🧠 **سؤال اليوم**\n\n" + item["q"]
    for chat_id in list(users):
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=kb_daily(qid, item["choices"]),
                parse_mode="Markdown"
            )
            st["sent_to"].append(int(chat_id))
        except Forbidden:
            # المستخدم حظر البوت
            pass
        except Exception:
            pass

    save_daily_state(st)

async def daily_show_cb(q, context: ContextTypes.DEFAULT_TYPE):
    """يعرض سؤال اليوم الحالي عند الضغط على زر 'سؤال اليوم'"""
    st = load_daily_state()
    bank = load_quiz_bank()
    if not st.get("qid") and st.get("qid") != 0:
        return await q.message.edit_text("لا يوجد سؤال اليوم بعد. انتظر الإرسال اليومي. ✅", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]))

    qid = int(st["qid"])
    if qid < 0 or qid >= len(bank):
        return await q.message.edit_text("⚠️ سؤال اليوم غير متوفر.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]))

    item = bank[qid]
    text = "🧠 **سؤال اليوم**\n\n" + item["q"]
    await q.message.edit_text(text, reply_markup=kb_daily(qid, item["choices"]), parse_mode="Markdown")

async def daily_answer_cb(q, user_id: int):
    bank = load_quiz_bank()
    st = load_daily_state()

    payload = q.data.split(":", 1)[1]  # ans|qid|choice
    _, qid_s, choice_s = payload.split("|")
    qid = int(qid_s)
    choice = int(choice_s)

    if qid < 0 or qid >= len(bank):
        return await q.message.edit_text("⚠️ سؤال غير موجود.")

    today = date.today().isoformat()
    if st.get("date") != today:
        return await q.message.edit_text("⚠️ هذا سؤال قديم. انتظر سؤال اليوم الجديد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]))

    # منع تكرار الإجابة في نفس اليوم
    answered = st.get("answered", {})
    if str(user_id) in answered:
        me = get_profile_points(user_id)
        return await q.message.edit_text(
            f"✅ لقد أجبت على سؤال اليوم بالفعل.\n⭐ نقاطك: {me.get('points', 0)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]])
        )

    item = bank[qid]
    correct = int(item["answer"])

    answered[str(user_id)] = True
    st["answered"] = answered
    save_daily_state(st)

    if choice == correct:
        new_badges = add_points(user_id, DAILY_POINTS)
        result = f"✅ صحيح! +{DAILY_POINTS} نقاط"
        extra = ("\n\n🏆 " + "\n🏆 ".join(new_badges)) if new_badges else ""
        stats = load_stats()
        stats["daily_answers"] = int(stats.get("daily_answers", 0)) + 1
        save_stats(stats)
    else:
        result = f"❌ خطأ.\n✅ الصحيح هو: **{item['choices'][correct]}**"
        extra = ""

    me = get_profile_points(user_id)
    text = f"🧠 **سؤال اليوم**\n\nالنتيجة: {result}\n⭐ نقاطك الآن: **{me.get('points', 0)}**{extra}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 نقاطي/إنجازاتي", callback_data="me:points")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])
    await q.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


# ====== استيراد أسئلة من ملف JSON ======
# المشرف يرسل ملف questions.json في مجموعة المشرفين ثم يعمل Reply عليه ويكتب /importquiz
async def import_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID and not is_admin_user(update.effective_user.id):
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        return await update.message.reply_text("✅ أرسل ملف JSON ثم اعمل Reply عليه واكتب /importquiz")

    doc = update.message.reply_to_message.document
    filename = (doc.file_name or "").lower()
    if not filename.endswith(".json"):
        return await update.message.reply_text("⚠️ الملف يجب أن يكون بصيغة .json")

    try:
        tg_file = await doc.get_file()
        data_bytes = await tg_file.download_as_bytearray()
        text = data_bytes.decode("utf-8", errors="ignore")
        parsed = json.loads(text)

        if not isinstance(parsed, list) or not parsed:
            return await update.message.reply_text("⚠️ محتوى JSON يجب أن يكون قائمة أسئلة.")

        # التحقق من بنية كل سؤال
        cleaned = []
        for it in parsed:
            if not isinstance(it, dict):
                continue
            qtxt = it.get("q")
            choices = it.get("choices")
            answer = it.get("answer")
            pts = it.get("points", 2)
            if not qtxt or not isinstance(choices, list) or len(choices) < 2:
                continue
            if not isinstance(answer, int) or answer < 0 or answer >= len(choices):
                continue
            cleaned.append({"q": qtxt, "choices": choices, "answer": answer, "points": int(pts)})

        if not cleaned:
            return await update.message.reply_text("⚠️ لم أجد أسئلة صحيحة داخل الملف.")

        bank = load_quiz_bank()
        bank.extend(cleaned)
        save_quiz_bank(bank)

        await update.message.reply_text(f"✅ تم استيراد {len(cleaned)} سؤال.\n📦 عدد الأسئلة الآن: {len(bank)}")

    except Exception:
        await update.message.reply_text("⚠️ فشل قراءة الملف. تأكد أنه JSON صحيح UTF-8.")


# ====== /addquiz (اختياري) ======
# صيغة بسيطة:
# /addquiz السؤال ؟ | خيار1 | خيار2 | خيار3 | خيار4 | رقم_الصحيح (0-3) | نقاط
async def add_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID and not is_admin_user(update.effective_user.id):
        return

    txt = update.message.text.replace("/addquiz", "", 1).strip()
    if "|" not in txt:
        return await update.message.reply_text("الصيغة:\n/addquiz السؤال | خيار1 | خيار2 | ... | رقم_الصحيح | نقاط")

    parts = [p.strip() for p in txt.split("|")]
    if len(parts) < 5:
        return await update.message.reply_text("⚠️ اكتب على الأقل: سؤال | خيار1 | خيار2 | رقم_الصحيح")

    qtxt = parts[0]
    # آخر جزءين: answer و points (points اختياري)
    try:
        answer = int(parts[-2])
        pts = int(parts[-1]) if parts[-1].isdigit() else 2
        choices = parts[1:-2]
    except Exception:
        # إذا لم يضع نقاط
        try:
            answer = int(parts[-1])
            pts = 2
            choices = parts[1:-1]
        except Exception:
            return await update.message.reply_text("⚠️ لم أفهم رقم الإجابة الصحيحة.")

    if len(choices) < 2:
        return await update.message.reply_text("⚠️ يجب خيارين على الأقل.")
    if answer < 0 or answer >= len(choices):
        return await update.message.reply_text("⚠️ رقم الإجابة خارج النطاق.")

    bank = load_quiz_bank()
    bank.append({"q": qtxt, "choices": choices, "answer": answer, "points": pts})
    save_quiz_bank(bank)
    await update.message.reply_text(f"✅ تمت إضافة السؤال. عدد الأسئلة الآن: {len(bank)}")


# ====== إحصائيات ======
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID and not is_admin_user(update.effective_user.id):
        return
    users = load_users()
    st = load_stats()
    await update.message.reply_text(
        "📊 إحصائيات البوت\n\n"
        f"👥 عدد الطلاب: {len(users)}\n"
        f"📩 رسائل الطلاب (تقريبًا): {st.get('student_messages', 0)}\n"
        f"🧠 إجابات سؤال اليوم: {st.get('daily_answers', 0)}\n"
        f"📝 إجابات الاختبار: {st.get('quiz_answers', 0)}\n"
    )


# ====== Broadcast (كما عندك) ======
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

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
        await update.message.reply_text("لا يوجد طلاب مسجلين بعد. اطلب منهم إرسال /start للبوت.")
        return

    if context.args:
        text = " ".join(context.args).strip()
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

    if update.message.reply_to_message:
        src = update.message.reply_to_message
        ok = 0
        bad = 0
        removed = set()

        for chat_id in list(users):
            try:
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=ADMIN_CHAT_ID,
                    message_id=src.message_id
                )
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

    await update.message.reply_text("اكتب:\n/broadcast نص الإعلان\nأو اعمل Reply على رسالة ثم /broadcast")


# ====== الدروس (كما كودك) ======
async def lessons_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, q):
    data = q.data

    if data == "years":
        context.user_data.clear()
        return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())

    if data.startswith("back:"):
        where = data.split(":", 1)[1]

        if where == "years":
            context.user_data.clear()
            return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())

        if where == "specs":
            year = context.user_data.get("year")
            if not year:
                return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
            context.user_data.pop("spec", None)
            context.user_data.pop("sem", None)
            context.user_data.pop("subject", None)
            context.user_data.pop("lesson_items", None)
            return await q.message.edit_text("📙 اختر التخصص:", reply_markup=kb_specs(year))

        if where == "sems":
            year = context.user_data.get("year")
            spec = context.user_data.get("spec")
            if not (year and spec):
                return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
            context.user_data.pop("sem", None)
            context.user_data.pop("subject", None)
            context.user_data.pop("lesson_items", None)
            return await q.message.edit_text("📗 اختر السداسي:", reply_markup=kb_sems(year, spec))

        if where == "subjects":
            year = context.user_data.get("year")
            spec = context.user_data.get("spec")
            sem = context.user_data.get("sem")
            if not (year and spec and sem):
                return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_years())
            context.user_data.pop("subject", None)
            context.user_data.pop("lesson_items", None)
            return await q.message.edit_text("📚 اختر المادة:", reply_markup=kb_subjects(year, spec, sem))

    if data.startswith("y:"):
        idx = int(data.split(":", 1)[1])
        year = list(LESSONS.keys())[idx]
        context.user_data["year"] = year
        return await q.message.edit_text("📙 اختر التخصص:", reply_markup=kb_specs(year))

    if data.startswith("sp:"):
        idx = int(data.split(":", 1)[1])
        year = context.user_data["year"]
        spec = list(LESSONS[year].keys())[idx]
        context.user_data["spec"] = spec
        return await q.message.edit_text("📗 اختر السداسي:", reply_markup=kb_sems(year, spec))

    if data.startswith("se:"):
        idx = int(data.split(":", 1)[1])
        year = context.user_data["year"]
        spec = context.user_data["spec"]
        sem = list(LESSONS[year][spec].keys())[idx]
        context.user_data["sem"] = sem
        return await q.message.edit_text("📚 اختر المادة:", reply_markup=kb_subjects(year, spec, sem))

    if data.startswith("su:"):
        idx = int(data.split(":", 1)[1])
        year = context.user_data["year"]
        spec = context.user_data["spec"]
        sem = context.user_data["sem"]
        subject = list(LESSONS[year][spec][sem].keys())[idx]
        context.user_data["subject"] = subject

        items = LESSONS[year][spec][sem][subject]
        context.user_data["lesson_items"] = items

        if not items:
            return await q.message.edit_text(
                f"⚠️ لا توجد دروس مضافة بعد لمادة:\n{subject}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="back:subjects")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ])
            )

        return await q.message.edit_text(
            f"📖 {subject}\nاختر الدرس:",
            reply_markup=kb_lessons(items)
        )

    if data.startswith("file:"):
        i = int(data.split(":", 1)[1])
        items = context.user_data.get("lesson_items", [])
        if not items or i < 0 or i >= len(items):
            return await q.message.reply_text("⚠️ حدث خطأ: الدرس غير موجود. أعد فتح المادة من جديد.")

        title, file_id = items[i]
        if is_http(file_id):
            return await q.message.reply_text(f"افتح الرابط:\n{file_id}")

        try:
            await q.message.reply_document(document=file_id, caption=title)
        except BadRequest:
            await q.message.reply_text("⚠️ لم أستطع إرسال الملف (file_id غير صالح).")
        except Exception:
            await q.message.reply_text("⚠️ حدث خطأ أثناء إرسال الملف.")
        return


# ====== أسئلة الطلاب: نسخ أي شيء من الخاص للمشرفين ======
async def student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    add_user(update.effective_chat.id)

    stats = load_stats()
    stats["student_messages"] = int(stats.get("student_messages", 0)) + 1
    save_stats(stats)

    user = update.effective_user
    student_chat_id = update.effective_chat.id
    msg = update.message

    meta = await context.bot.send_message(
        ADMIN_CHAT_ID,
        "📩 سؤال جديد من طالب\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"🆔 user_id: {user.id}\n\n"
        "↩️ للرد: اعمل Reply على هذه الرسالة أو على الرسالة التي تحتها."
    )

    copied = await context.bot.copy_message(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=student_chat_id,
        message_id=msg.message_id,
        reply_to_message_id=meta.message_id
    )

    m = _load_json(MAP_FILE, {})
    m[str(meta.message_id)] = student_chat_id
    m[str(copied.message_id)] = student_chat_id
    _save_json(MAP_FILE, m)

    await msg.reply_text("✅ تم إرسال رسالتك للمشرفين.\nسيتم الرد عليك بإذن الله.")


# ====== رد المشرفين بالـ Reply ======
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    msg = update.message
    if not msg or not msg.reply_to_message:
        return

    m = _load_json(MAP_FILE, {})
    key = str(msg.reply_to_message.message_id)
    student_chat_id = m.get(key)
    if not student_chat_id:
        return

    if msg.text:
        await context.bot.send_message(student_chat_id, f"📩 رد من المشرفين:\n\n{msg.text}")
        return

    await context.bot.send_message(student_chat_id, "📩 رد من المشرفين:")
    await context.bot.copy_message(
        chat_id=student_chat_id,
        from_chat_id=ADMIN_CHAT_ID,
        message_id=msg.message_id
    )


# ====== الراوتر للأزرار ======
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    user_id = update.effective_user.id

    # الرئيسية
    if data == "home":
        return await show_home(update, context)

    # الدروس
    if data == "years" or data.startswith(("back:", "y:", "sp:", "se:", "su:", "file:")):
        return await lessons_flow(update, context, q)

    # سؤال اليوم
    if data == "daily:show":
        return await daily_show_cb(q, context)
    if data.startswith("daily:ans|"):
        return await daily_answer_cb(q, user_id)

    # اختبار سريع
    if data == "quiz:start":
        return await quiz_start_cb(q, context)
    if data.startswith("quiz:ans|"):
        return await quiz_answer_cb(q, context, user_id)

    # نقاطي
    if data == "me:points":
        return await my_points_cb(q, user_id)

    # ورد/حديث
    if data == "wird:home":
        return await wird_home_cb(q)
    if data == "wird:wird":
        return await wird_show_cb(q, "wird")
    if data == "wird:hadith":
        return await wird_show_cb(q, "hadith")

    # ملف الطالب
    if data == "me:profile":
        return await profile_show_cb(q, user_id)
    if data == "prof:set_year":
        return await q.message.edit_text("📘 اختر السنة:", reply_markup=kb_choose_year())
    if data.startswith("prof:year|"):
        year = data.split("|", 1)[1]
        pr = get_student_profile(user_id)
        pr["year"] = year
        # بعد اختيار السنة نعرض تخصصات السنة
        set_student_profile(user_id, pr)
        return await q.message.edit_text("📙 اختر التخصص:", reply_markup=kb_choose_spec(year))
    if data.startswith("prof:spec|"):
        spec = data.split("|", 1)[1]
        pr = get_student_profile(user_id)
        pr["spec"] = spec
        set_student_profile(user_id, pr)
        return await profile_show_cb(q, user_id)
    if data == "prof:set_spec":
        pr = get_student_profile(user_id)
        year = pr.get("year")
        if not year:
            return await q.message.edit_text("اختر السنة أولاً.", reply_markup=kb_choose_year())
        return await q.message.edit_text("📙 اختر التخصص:", reply_markup=kb_choose_spec(year))
    if data == "prof:set_group":
        context.user_data["awaiting_group"] = True
        return await profile_set_group_hint(q)

    # لوحة تحكم المشرف (تلميحات)
    if data.startswith("admin:"):
        if update.effective_chat.id != ADMIN_CHAT_ID:
            return
        act = data.split(":", 1)[1]
        if act == "broadcast_help":
            return await q.message.edit_text(
                "📢 النشر:\n\n"
                "1) بث نص: اكتب في المجموعة:\n/broadcast نص الإعلان\n\n"
                "2) بث رسالة/ملف: اعمل Reply على الرسالة ثم اكتب:\n/broadcast",
                reply_markup=kb_admin_panel()
            )
        if act == "addquiz_help":
            return await q.message.edit_text(
                "🧪 إضافة سؤال بسرعة:\n\n"
                "/addquiz السؤال ؟ | خيار1 | خيار2 | خيار3 | خيار4 | رقم_الصحيح | نقاط\n\n"
                "مثال:\n/addquiz عدد أركان الإسلام؟ | 3 | 4 | 5 | 6 | 2 | 2",
                reply_markup=kb_admin_panel()
            )
        if act == "import_help":
            return await q.message.edit_text(
                "📦 استيراد أسئلة من JSON:\n\n"
                "1) ارفع ملف questions.json في المجموعة\n"
                "2) اعمل Reply على الملف\n"
                "3) اكتب: /importquiz\n\n"
                "صيغة كل سؤال داخل JSON:\n"
                '{"q":"...","choices":["...","..."],"answer":0,"points":2}',
                reply_markup=kb_admin_panel()
            )
        if act == "wird_help":
            return await q.message.edit_text(
                "📖 تحديث الورد/الحديث:\n\n"
                "/setwird نص ورد اليوم\n"
                "/sethadith نص حديث اليوم",
                reply_markup=kb_admin_panel()
            )
        if act == "stats":
            users = load_users()
            st = load_stats()
            return await q.message.edit_text(
                "📊 إحصائيات\n\n"
                f"👥 الطلاب: {len(users)}\n"
                f"📩 رسائل الطلاب: {st.get('student_messages',0)}\n"
                f"🧠 إجابات سؤال اليوم: {st.get('daily_answers',0)}\n"
                f"📝 إجابات الاختبار: {st.get('quiz_answers',0)}\n",
                reply_markup=kb_admin_panel()
            )


# ====== استقبال نص المجموعة للملف الشخصي (المجموعة) ======
async def profile_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فقط في الخاص
    if update.effective_chat.type != "private":
        return
    if not context.user_data.get("awaiting_group"):
        return

    context.user_data["awaiting_group"] = False
    txt = (update.message.text or "").strip()
    pr = get_student_profile(update.effective_user.id)
    pr["group"] = txt
    set_student_profile(update.effective_user.id, pr)
    await update.message.reply_text("✅ تم حفظ المجموعة. افتح (📌 بياناتي) لمراجعتها.", reply_markup=kb_home())


# ====== بناء التطبيق ======
def build_app():
    token = _clean(os.environ.get("BOT_TOKEN", ""))
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Set it in Render Environment Variables.")

    app = Application.builder().token(token).build()

    # أوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(CommandHandler("broadcast", broadcast, filters=filters.Chat(ADMIN_CHAT_ID)))

    app.add_handler(CommandHandler("admin", admin_panel, filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("stats", admin_stats, filters=filters.Chat(ADMIN_CHAT_ID)))

    app.add_handler(CommandHandler("setwird", set_wird))
    app.add_handler(CommandHandler("sethadith", set_hadith))

    app.add_handler(CommandHandler("importquiz", import_quiz, filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("addquiz", add_quiz, filters=filters.Chat(ADMIN_CHAT_ID)))

    # الأزرار
    app.add_handler(CallbackQueryHandler(buttons))

    # ردود المشرفين في المجموعة
    app.add_handler(MessageHandler(filters.Chat(ADMIN_CHAT_ID) & ~filters.COMMAND, admin_reply))

    # نص المجموعة في الخاص (ملف الطالب)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, profile_group_text))

    # أي شيء في الخاص (نص/صورة/ملف...) يروح للمشرفين (بعد حفظ المجموعة)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND & filters.ALL, student_message))

    # ====== جدولة سؤال اليوم ======
    # يرسل يوميًا الساعة 09:00 بتوقيت الخادم (عادة UTC على Render)
    # إذا أردته وقتًا آخر قلّي.
    app.job_queue.run_daily(daily_send_job, time=time(9, 0, 0))

    return app


if __name__ == "__main__":
    app = build_app()
    app.run_polling()
