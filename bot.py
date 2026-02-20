import os
import json
import random
from datetime import datetime

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
ADMIN_USER_IDS = {1490829295}        # IDs للمشرفين المسموح لهم بـ /getid
MAP_FILE = "msg_map.json"            # ربط رسائل المجموعة بالطالب للرد
USERS_FILE = "users.json"            # قائمة الطلاب (للبث)

POINTS_FILE = "points.json"          # نقاط الطلاب
CAL_FILE = "calendar.json"           # التقويم الجامعي


# ====== بنك أسئلة (Quiz) ======
QUIZ_QUESTIONS = [
    {
        "q": "عدد أركان الإسلام؟",
        "choices": ["3", "4", "5", "6"],
        "answer": 2,
        "points": 2,
    },
    {
        "q": "النية محلها؟",
        "choices": ["اللسان", "القلب", "اليد", "العين"],
        "answer": 1,
        "points": 2,
    },
    {
        "q": "وقت صلاة الفجر ينتهي بـ؟",
        "choices": ["طلوع الشمس", "الزوال", "غروب الشمس", "منتصف الليل"],
        "answer": 0,
        "points": 2,
    },
    {
        "q": "حكم الوضوء للصلاة؟",
        "choices": ["سنة", "واجب", "مكروه", "مباح"],
        "answer": 1,
        "points": 2,
    },
]

ACHIEVEMENTS = [
    (10, "🥉 إنجاز: مجتهد (10 نقاط)"),
    (25, "🥈 إنجاز: متفوق (25 نقطة)"),
    (50, "🥇 إنجاز: نجم الشريعة (50 نقطة)"),
]


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
        json.dump(data, f, ensure_ascii=False)


def load_map():
    return _load_json(MAP_FILE, {})


def save_map(m):
    _save_json(MAP_FILE, m)


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


def load_points():
    # {"123": {"points": 12, "badges": ["..."], "last_quiz": "..."}} 
    return _load_json(POINTS_FILE, {})


def save_points(p):
    _save_json(POINTS_FILE, p)


def get_profile(user_id: int):
    p = load_points()
    key = str(user_id)
    if key not in p:
        p[key] = {"points": 0, "badges": [], "last_quiz": None}
        save_points(p)
    return p[key]


def set_profile(user_id: int, profile: dict):
    p = load_points()
    p[str(user_id)] = profile
    save_points(p)


def default_calendar():
    return {
        "📌 مواعيد الامتحانات": "لم يتم تحديد المواعيد بعد.",
        "🏖️ العطل": "لم يتم تحديد العطل بعد.",
        "⏳ آخر الآجال": "لم يتم تحديد الآجال بعد.",
    }


def load_calendar():
    cal = _load_json(CAL_FILE, None)
    if not isinstance(cal, dict) or not cal:
        cal = default_calendar()
        _save_json(CAL_FILE, cal)
    return cal


def save_calendar(cal: dict):
    _save_json(CAL_FILE, cal)


def is_http(s: str) -> bool:
    return isinstance(s, str) and (s.startswith("http://") or s.startswith("https://"))


# ====== لوحات المفاتيح ======
def kb_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 الدروس", callback_data="years")],
        [InlineKeyboardButton("📝 اختبار قصير", callback_data="quiz:start")],
        [InlineKeyboardButton("🏆 نقاطي/إنجازاتي", callback_data="me:points")],
        [InlineKeyboardButton("🗓️ التقويم الجامعي", callback_data="cal:home")],
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
    """
    items: list of tuples (title, value)
      - if value is http(s) => open link
      - else => treat as Telegram file_id and send by callback
    """
    kb = []
    for i, (title, value) in enumerate(items):
        if is_http(value):
            kb.append([InlineKeyboardButton(title, url=value)])
        else:
            kb.append([InlineKeyboardButton(title, callback_data=f"file:{i}")])

    kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back:subjects")])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


WELCOME_TEXT = (
    "السلام عليكم ورحمة الله تعالى وبركاته 🌿\n"
    "مرحباً بك في البوت المساعد لطالب الشريعة\n"
    "في جامعة البشير الإبراهيمي 🕌\n\n"
    "📚 الدروس عبر الأزرار\n"
    "📝 اختبارات قصيرة + نقاط وإنجازات\n"
    "🗓️ تقويم جامعي (امتحانات/عطل/آجال)\n\n"
    "✍️ لإرسال سؤال (نص/صورة/ملف): أرسل رسالتك هنا في الخاص\n"
    "وسيتم الرد عليك من طرف المشرفين بإذن الله"
)


# ====== شاشات ======
async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type == "private":
        add_user(update.effective_chat.id)

    # تنظيف حالة التصفح
    context.user_data.pop("year", None)
    context.user_data.pop("spec", None)
    context.user_data.pop("sem", None)
    context.user_data.pop("subject", None)
    context.user_data.pop("lesson_items", None)

    if update.message:
        await update.message.reply_text(WELCOME_TEXT, reply_markup=kb_home())
    else:
        await update.callback_query.message.edit_text(WELCOME_TEXT, reply_markup=kb_home())


# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_home(update, context)


# ====== /getid (استخراج file_id للـ PDF) ======
async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # فقط المشرفين أو داخل مجموعة المشرفين
    if update.effective_user.id not in ADMIN_USER_IDS and update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if not msg.reply_to_message:
        await msg.reply_text("✅ ارسل ملف PDF ثم اعمل عليه Reply واكتب /getid")
        return

    # لازم يكون PDF كـ document
    if msg.reply_to_message.document:
        doc = msg.reply_to_message.document
        await msg.reply_text(
            "✅ هذا هو file_id (انسخه وضعه في lessons.py):\n\n"
            f"`{doc.file_id}`",
            parse_mode="Markdown"
        )
        return

    await msg.reply_text("⚠️ الرسالة التي رددت عليها ليست ملف PDF (Document). أرسل الـ PDF كـ ملف ثم أعد المحاولة.")


# ====== التقويم: /setcal (للمشرف) ======
# الصيغة:
# /setcal 📌 مواعيد الامتحانات | امتحان السداسي الأول: 20/03 ...
async def setcal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    txt = update.message.text.replace("/setcal", "", 1).strip()
    if "|" not in txt:
        await update.message.reply_text("الصيغة:\n/setcal اسم_القسم | النص")
        return

    section, value = [x.strip() for x in txt.split("|", 1)]
    cal = load_calendar()
    cal[section] = value
    save_calendar(cal)
    await update.message.reply_text("✅ تم تحديث التقويم.")


# ====== Quiz ======
def kb_quiz_choices(qid: int, choices):
    kb = [[InlineKeyboardButton(c, callback_data=f"quiz:ans|{qid}|{i}")] for i, c in enumerate(choices)]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(kb)


async def quiz_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    qid = random.randint(0, len(QUIZ_QUESTIONS) - 1)
    item = QUIZ_QUESTIONS[qid]
    context.user_data["quiz_qid"] = qid

    text = "📝 **اختبار قصير**\n\n" + item["q"]
    await q.message.edit_text(text, reply_markup=kb_quiz_choices(qid, item["choices"]), parse_mode="Markdown")


async def quiz_answer_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    # quiz:ans|qid|choice
    payload = q.data.split(":", 1)[1]
    _, qid_s, choice_s = payload.split("|")
    qid = int(qid_s)
    choice = int(choice_s)

    item = QUIZ_QUESTIONS[qid]
    correct = int(item["answer"])
    pts = int(item.get("points", 1))

    user_id = update.effective_user.id
    profile = get_profile(user_id)

    is_right = (choice == correct)
    gained = pts if is_right else 0

    before = int(profile.get("points", 0))
    profile["points"] = before + gained
    profile["last_quiz"] = datetime.utcnow().isoformat()

    badges = set(profile.get("badges", []))
    new_badges = []
    for threshold, badge in ACHIEVEMENTS:
        if profile["points"] >= threshold and badge not in badges:
            badges.add(badge)
            new_badges.append(badge)

    profile["badges"] = sorted(list(badges))
    set_profile(user_id, profile)

    if is_right:
        result = f"✅ إجابة صحيحة! +{gained} نقطة"
    else:
        result = f"❌ إجابة خاطئة.\n✅ الصحيح هو: **{item['choices'][correct]}**"

    extra = ""
    if new_badges:
        extra = "\n\n🏆 " + "\n🏆 ".join(new_badges)

    text = (
        f"📝 **اختبار قصير**\n\n"
        f"{item['q']}\n\n"
        f"النتيجة: {result}\n"
        f"⭐ نقاطك الآن: **{profile['points']}**"
        f"{extra}\n\n"
        "اضغط لبدء اختبار جديد:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 اختبار جديد", callback_data="quiz:start")],
        [InlineKeyboardButton("🏆 نقاطي/إنجازاتي", callback_data="me:points")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])

    await q.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


async def my_points_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    profile = get_profile(update.effective_user.id)
    badges = profile.get("badges", [])
    badges_text = "\n".join(badges) if badges else "لا توجد إنجازات بعد."

    text = (
        "🏆 **نقاطي/إنجازاتي**\n\n"
        f"⭐ النقاط: **{profile.get('points', 0)}**\n\n"
        f"🎖️ الإنجازات:\n{badges_text}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 اختبار قصير", callback_data="quiz:start")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])
    await q.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


# ====== التقويم بالأزرار ======
async def cal_home_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    cal = load_calendar()
    kb = [[InlineKeyboardButton(k, callback_data=f"cal:item|{k}")] for k in cal.keys()]
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    await q.message.edit_text("🗓️ **التقويم الجامعي**\nاختر القسم:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cal_item_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    payload = q.data.split(":", 1)[1]   # item|KEY
    _, key = payload.split("|", 1)

    cal = load_calendar()
    text = cal.get(key, "لا توجد معلومات بعد.")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ رجوع", callback_data="cal:home")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])
    await q.message.edit_text(f"🗓️ **{key}**\n\n{text}", reply_markup=kb, parse_mode="Markdown")


# ====== الأزرار (الدروس + المزايا) ======
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    # ===== الرئيسية =====
    if data == "home":
        return await show_home(update, context)

    # ===== Quiz =====
    if data == "quiz:start":
        return await quiz_start_cb(update, context)
    if data.startswith("quiz:ans|"):
        return await quiz_answer_cb(update, context)
    if data == "me:points":
        return await my_points_cb(update, context)

    # ===== Calendar =====
    if data == "cal:home":
        return await cal_home_cb(update, context)
    if data.startswith("cal:item|"):
        return await cal_item_cb(update, context)

    # ===== الدروس (كما هو عندك) =====
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

    # إرسال PDF عند الضغط على زر file:<i>
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

    m = load_map()
    m[str(meta.message_id)] = student_chat_id
    m[str(copied.message_id)] = student_chat_id
    save_map(m)

    await msg.reply_text("✅ تم إرسال رسالتك للمشرفين.\nسيتم الرد عليك بإذن الله.")


# ====== رد المشرفين بالـ Reply ======
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

    if msg.text:
        await context.bot.send_message(student_chat_id, f"📩 رد من المشرفين:\n\n{msg.text}")
        return

    await context.bot.send_message(student_chat_id, "📩 رد من المشرفين:")
    await context.bot.copy_message(
        chat_id=student_chat_id,
        from_chat_id=ADMIN_CHAT_ID,
        message_id=msg.message_id
    )


# ====== Broadcast ======
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

    # بث نص
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

    # بث Reply (صورة/ملف...)
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


# ====== بناء التطبيق ======
def build_app():
    token = _clean(os.environ.get("BOT_TOKEN", ""))
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Set it in Render Environment Variables.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast, filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(CommandHandler("setcal", setcal, filters=filters.Chat(ADMIN_CHAT_ID)))

    app.add_handler(CallbackQueryHandler(buttons))

    # ردود المشرفين في المجموعة (بالـ Reply)
    app.add_handler(MessageHandler(filters.Chat(ADMIN_CHAT_ID) & ~filters.COMMAND, admin_reply))

    # أي شيء في الخاص (نص/صورة/ملف...) يروح للمشرفين
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, student_message))

    return app


if __name__ == "__main__":
    app = build_app()
    app.run_polling()
