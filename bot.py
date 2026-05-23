# ================================================================
#  bot.py — البوت المساعد لطالب الشريعة
#  جامعة البشير الإبراهيمي
#  النسخة النهائية
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


# ================================================================
#  ١. الإعدادات
# ================================================================

ADMIN_CHAT_ID = -5286458958      # معرّف مجموعة المشرفين
ADMIN_IDS     = {1490829295}     # معرّفات المشرفين

FILE_MAP      = "msg_map.json"
FILE_USERS    = "users.json"
FILE_POINTS   = "points.json"
FILE_CAL      = "calendar.json"
FILE_LESSONS  = "lessons_data.json"
FILE_QUIZ     = "quiz_data.json"
FILE_SCHED    = "schedule_state.json"

TZ = ZoneInfo("Africa/Algiers")


# ================================================================
#  ٢. بنك الأسئلة الافتراضي
# ================================================================

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
    (25,  "🥈 متفوق — 25 نقطة"),
    (50,  "🥇 نجم الشريعة — 50 نقطة"),
    (100, "🏅 حافظ — 100 نقطة"),
]


# ================================================================
#  ٣. أدوات JSON
# ================================================================

def _clean(s):
    return "".join(str(s).strip().split()) if s else ""

def _load(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_url(s):
    return isinstance(s, str) and (s.startswith("http://") or s.startswith("https://"))

def is_admin(uid, cid=None):
    return uid in ADMIN_IDS or cid == ADMIN_CHAT_ID


# ================================================================
#  ٤. إدارة الدروس
# ================================================================

def load_lessons():
    """تحميل الدروس — من JSON أو من lessons.py عند أول تشغيل"""
    if os.path.exists(FILE_LESSONS):
        data = _load(FILE_LESSONS, None)
        if isinstance(data, dict) and data:
            return data
    # تهيئة أول مرة
    try:
        from lessons import LESSONS as _D
        data = copy.deepcopy(_D)
        _save(FILE_LESSONS, data)
        print("✅ lessons_data.json تم إنشاؤه من lessons.py")
        return data
    except ImportError:
        print("❌ lessons.py غير موجود — تأكد من رفعه على GitHub")
    except Exception as e:
        print(f"❌ خطأ في تحميل الدروس: {e}")
    return {}

def save_lessons(data):
    _save(FILE_LESSONS, data)

def total_lessons(data):
    return sum(
        len(v)
        for y in data.values()
        for s in y.values()
        for sm in s.values()
        for v in sm.values()
    )


# ================================================================
#  ٥. إدارة الكويز
# ================================================================

def load_quiz():
    data = _load(FILE_QUIZ, None)
    if isinstance(data, list) and data:
        return data
    _save(FILE_QUIZ, DEFAULT_QUIZ)
    return copy.deepcopy(DEFAULT_QUIZ)

def save_quiz(data):
    _save(FILE_QUIZ, data)


# ================================================================
#  ٦. إدارة المستخدمين
# ================================================================

def load_users():
    data = _load(FILE_USERS, [])
    try:
        return set(int(x) for x in data)
    except Exception:
        return set()

def save_users(u):
    _save(FILE_USERS, sorted(list(u)))

def add_user(cid):
    u = load_users()
    if int(cid) not in u:
        u.add(int(cid))
        save_users(u)


# ================================================================
#  ٧. إدارة النقاط
# ================================================================

def load_points():
    return _load(FILE_POINTS, {})

def save_points(p):
    _save(FILE_POINTS, p)

def get_profile(uid):
    p, k = load_points(), str(uid)
    if k not in p:
        p[k] = {"points": 0, "badges": [], "last_quiz": None}
        save_points(p)
    return p[k]

def save_profile(uid, profile):
    p = load_points()
    p[str(uid)] = profile
    save_points(p)

def apply_achievements(profile):
    badges, new = set(profile.get("badges", [])), []
    for thr, badge in ACHIEVEMENTS:
        if profile["points"] >= thr and badge not in badges:
            badges.add(badge); new.append(badge)
    profile["badges"] = sorted(badges)
    return new


# ================================================================
#  ٨. إدارة التقويم
# ================================================================

DEFAULT_CAL = {
    "📌 مواعيد الامتحانات": "لم يتم تحديد المواعيد بعد.",
    "🏖️ العطل الرسمية":    "لم يتم تحديد العطل بعد.",
    "⏳ آخر الآجال":        "لم يتم تحديد الآجال بعد.",
    "📖 ورد اليوم":         "لم يتم ضبط ورد اليوم بعد.",
    "📜 حديث اليوم":        "لم يتم ضبط حديث اليوم بعد.",
}

def load_cal():
    c = _load(FILE_CAL, None)
    if not isinstance(c, dict) or not c:
        c = DEFAULT_CAL.copy(); _save(FILE_CAL, c)
    return c

def save_cal(c):
    _save(FILE_CAL, c)


# ================================================================
#  ٩. ربط رسائل الطلاب بالمشرفين
# ================================================================

def load_map():
    return _load(FILE_MAP, {})

def save_map(m):
    _save(FILE_MAP, m)


# ================================================================
#  ١٠. البث للجميع
# ================================================================

async def broadcast_all(bot, text, parse_mode=None):
    users, dead = load_users(), set()
    for uid in list(users):
        try:
            await bot.send_message(uid, text, parse_mode=parse_mode)
        except Forbidden:
            dead.add(uid)
        except Exception:
            pass
    if dead:
        save_users(users - dead)


# ================================================================
#  ١١. الجدولة اليومية
# ================================================================

FIXED_MSGS = [
    (7,  0, "morning",
     "🌿 *أذكار الصباح*\n\n"
     "اللهم بك أصبحنا وبك أمسينا وبك نحيا وبك نموت وإليك النشور.\n\n"
     "أصبحنا وأصبح الملك لله والحمد لله لا شريك له، له الملك وله الحمد "
     "وهو على كل شيء قدير."),
    (17, 0, "evening",
     "🌙 *أذكار المساء*\n\n"
     "اللهم بك أمسينا وبك أصبحنا وبك نحيا وبك نموت وإليك المصير.\n\n"
     "أمسينا وأمسى الملك لله والحمد لله لا شريك له، له الملك وله الحمد "
     "وهو على كل شيء قدير."),
]

CAL_MSGS = [
    (10, 0, "wird",   "📖 ورد اليوم"),
    (20, 0, "hadith", "📜 حديث اليوم"),
]


async def scheduler_loop(app: Application):
    while True:
        try:
            now   = datetime.now(TZ)
            today = now.date().isoformat()
            st    = _load(FILE_SCHED, {})
            if not isinstance(st, dict):
                st = {}
            st.setdefault(today, {})

            for h, m, key, text in FIXED_MSGS:
                if now.hour == h and now.minute == m and not st[today].get(key):
                    await broadcast_all(app.bot, text, parse_mode="Markdown")
                    st[today][key] = True
                    _save(FILE_SCHED, st)

            for h, m, key, cal_key in CAL_MSGS:
                if now.hour == h and now.minute == m and not st[today].get(key):
                    cal  = load_cal()
                    body = cal.get(cal_key, "لم يتم الضبط بعد.")
                    await broadcast_all(app.bot, f"{cal_key}\n\n{body}")
                    st[today][key] = True
                    _save(FILE_SCHED, st)

        except Exception as e:
            print(f"⚠️ scheduler: {e}")

        await asyncio.sleep(30)


async def on_startup(app: Application):
    app.create_task(scheduler_loop(app))
    print("✅ البوت يعمل — الجدولة اليومية نشطة")


# ================================================================
#  ١٢. النصوص الثابتة
# ================================================================

TXT_WELCOME = (
    "السلام عليكم ورحمة الله وبركاته 🌿\n\n"
    "أهلاً بك في *البوت المساعد لطالب الشريعة*\n"
    "جامعة البشير الإبراهيمي 🕌\n\n"
    "📚 تصفّح الدروس بسهولة\n"
    "📝 اختبارات قصيرة مع نقاط وإنجازات\n"
    "🗓️ تقويم جامعي محدَّث باستمرار\n"
    "✍️ أرسل سؤالك وسيجيبك المشرفون"
)

TXT_HELP = (
    "❓ *دليل الاستخدام*\n\n"
    "📚 *الدروس*\n"
    "اضغط «الدروس» ثم اختر:\n"
    "السنة ← التخصص ← السداسي ← المادة ← الدرس\n\n"
    "📝 *الاختبار القصير*\n"
    "أسئلة عشوائية — كل إجابة صحيحة تمنحك نقاطاً\n\n"
    "🏆 *نقاطي*\n"
    "اعرض نقاطك وإنجازاتك وترتيبك بين الطلاب\n\n"
    "🗓️ *التقويم الجامعي*\n"
    "مواعيد الامتحانات، العطل، وآخر الآجال\n\n"
    "✍️ *سؤال للمشرفين*\n"
    "أرسل أي رسالة (نص/صورة/ملف) في الخاص\n\n"
    "⏰ *رسائل يومية تلقائية*\n"
    "   07:00  أذكار الصباح\n"
    "   10:00  ورد اليوم\n"
    "   17:00  أذكار المساء\n"
    "   20:00  حديث اليوم"
)

TXT_ADMIN = (
    "🛠️ *أوامر المشرف*\n\n"
    "━━━ 📚 الدروس ━━━\n"
    "➕ *إضافة PDF* (Reply على الملف ثم):\n"
    "`/adddars السنة | التخصص | السداسي | المادة | العنوان`\n\n"
    "➕ *إضافة رابط:*\n"
    "`/adddars السنة | التخصص | السداسي | المادة | العنوان | https://...`\n\n"
    "📋 *عرض دروس مادة:*\n"
    "`/listdars السنة | التخصص | السداسي | المادة`\n\n"
    "🗑️ *حذف درس:*\n"
    "`/deldars السنة | التخصص | السداسي | المادة | رقم`\n\n"
    "━━━ 📝 الكويز ━━━\n"
    "➕ *إضافة سؤال:*\n"
    "`/addquiz السؤال | خ1 | خ2 | خ3 | خ4 | رقم_الصحيح | نقاط`\n\n"
    "📋 `/listquiz`   🗑️ `/delquiz رقم`\n\n"
    "━━━ 📢 عام ━━━\n"
    "📊 `/stats`  —  إحصائيات\n"
    "📢 `/broadcast النص`  أو Reply + `/broadcast`\n"
    "🗓️ `/setcal القسم | النص`  —  تحديث التقويم\n"
    "🏓 `/ping`  —  اختبار البوت\n"
    "📎 أرسل PDF في الخاص للحصول على file\\_id"
)


# ================================================================
#  ١٣. لوحات المفاتيح
# ================================================================

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 الدروس",           callback_data="D:years")],
        [InlineKeyboardButton("📝 اختبار قصير",      callback_data="Q:start"),
         InlineKeyboardButton("🏆 نقاطي",            callback_data="P:show")],
        [InlineKeyboardButton("🗓️ التقويم الجامعي",  callback_data="C:home")],
        [InlineKeyboardButton("❓ مساعدة",            callback_data="H:show")],
    ])

def kb_years(lessons):
    if not lessons:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ لا توجد دروس بعد — تحقق من lessons.py",
                                  callback_data="home")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
        ])
    rows = [[InlineKeyboardButton(y, callback_data=f"D:y:{i}")]
            for i, y in enumerate(lessons)]
    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(rows)

def kb_specs(lessons, year):
    rows = [[InlineKeyboardButton(s, callback_data=f"D:s:{i}")]
            for i, s in enumerate(lessons[year])]
    rows += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="D:years")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(rows)

def kb_sems(lessons, year, spec):
    rows = [[InlineKeyboardButton(sm, callback_data=f"D:sm:{i}")]
            for i, sm in enumerate(lessons[year][spec])]
    rows += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="D:specs")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(rows)

def kb_subjects(lessons, year, spec, sem):
    subs = lessons[year][spec][sem]
    rows = []
    for i, (name, items) in enumerate(subs.items()):
        label = f"{name}  ·  {len(items)} 📄" if items else name
        rows.append([InlineKeyboardButton(label, callback_data=f"D:sb:{i}")])
    rows += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="D:sems")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(rows)

def kb_files(items):
    rows = []
    for i, (title, val) in enumerate(items):
        if is_url(val):
            rows.append([InlineKeyboardButton(f"🔗 {title}", url=val)])
        else:
            rows.append([InlineKeyboardButton(f"📄 {title}", callback_data=f"D:f:{i}")])
    rows += [
        [InlineKeyboardButton("⬅️ رجوع",     callback_data="D:subjects")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(rows)

def kb_back(target):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ رجوع",     callback_data=target)],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])


# ================================================================
#  ١٤. أوامر البوت
# ================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        add_user(update.effective_chat.id)
    context.user_data.clear()
    await update.message.reply_text(TXT_WELCOME, reply_markup=kb_main(), parse_mode="Markdown")


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = datetime.now(TZ).strftime("%H:%M:%S")
    await update.message.reply_text(f"🏓 البوت يعمل ✅\n🕐 {t} (توقيت الجزائر)")


async def cmd_adminhelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text(TXT_ADMIN, parse_mode="Markdown")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        return
    users   = load_users()
    lessons = load_lessons()
    quiz    = load_quiz()
    points  = load_points()
    top3 = sorted(
        [(uid, d.get("points", 0)) for uid, d in points.items()],
        key=lambda x: x[1], reverse=True
    )[:3]
    top_txt = "\n".join(
        f"  {r+1}. `{uid}` — {pts} نقطة"
        for r, (uid, pts) in enumerate(top3)
    ) or "  لا توجد بيانات بعد"
    await update.message.reply_text(
        "📊 *إحصائيات البوت*\n\n"
        f"👥 الطلاب المسجلون : *{len(users)}*\n"
        f"📚 إجمالي الدروس   : *{total_lessons(lessons)}*\n"
        f"📝 أسئلة الكويز    : *{len(quiz)}*\n"
        f"🏆 الطلاب النشطون  : *{len(points)}*\n\n"
        f"🥇 *أعلى الطلاب:*\n{top_txt}",
        parse_mode="Markdown"
    )


# ── إدارة الدروس ──

async def cmd_adddars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        if msg: await msg.reply_text("❌ ليس لديك صلاحية.")
        return

    raw   = (msg.text or "").replace("/adddars", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    doc   = getattr(getattr(msg, "reply_to_message", None), "document", None)

    if len(parts) == 5:
        year, spec, sem, subj, title = parts
        if not doc:
            await msg.reply_text(
                "⚠️ *لم أجد ملف PDF!*\n\n"
                "الطريقة:\n"
                "١. أرسل PDF للبوت في الخاص\n"
                "٢. اعمل *Reply* على الملف\n"
                "٣. اكتب:\n"
                "`/adddars السنة | التخصص | السداسي | المادة | العنوان`",
                parse_mode="Markdown"
            )
            return
        value = doc.file_id

    elif len(parts) == 6:
        year, spec, sem, subj, title, url = parts
        if not is_url(url):
            await msg.reply_text("⚠️ الرابط يجب أن يبدأ بـ https://")
            return
        value = url

    else:
        await msg.reply_text("⚠️ صيغة غير صحيحة. اكتب /adminhelp.")
        return

    lessons = load_lessons()
    (lessons.setdefault(year, {})
            .setdefault(spec, {})
            .setdefault(sem,  {})
            .setdefault(subj, [])
            .append([title, value]))
    save_lessons(lessons)

    await msg.reply_text(
        f"✅ *تمت الإضافة!*\n\n"
        f"📚 {year} ← {spec}\n"
        f"📅 {sem} ← {subj}\n"
        f"{'🔗' if is_url(value) else '📄'} *{title}*",
        parse_mode="Markdown"
    )


async def cmd_listdars(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    year, spec, sem, subj = parts
    try:
        items = load_lessons()[year][spec][sem][subj]
    except KeyError:
        await msg.reply_text("⚠️ المسار غير موجود.")
        return
    if not items:
        await msg.reply_text(f"📭 لا توجد دروس في *{subj}*", parse_mode="Markdown")
        return
    lines = [f"📚 *دروس {subj} ({len(items)}):*\n"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {'🔗' if is_url(it[1]) else '📄'} {it[0]}")
    lines.append(f"\n🗑️ `/deldars {year} | {spec} | {sem} | {subj} | رقم`")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_deldars(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    year, spec, sem, subj, idx_s = parts
    try:
        idx = int(idx_s) - 1
        assert idx >= 0
    except Exception:
        await msg.reply_text("⚠️ الرقم يجب أن يكون موجباً.")
        return
    lessons = load_lessons()
    try:
        items = lessons[year][spec][sem][subj]
    except KeyError:
        await msg.reply_text("⚠️ المسار غير موجود.")
        return
    if idx >= len(items):
        await msg.reply_text(f"⚠️ يوجد {len(items)} درس فقط.")
        return
    removed = items.pop(idx)
    save_lessons(lessons)
    await msg.reply_text(f"✅ تم حذف: *{removed[0]}*", parse_mode="Markdown")


# ── إدارة الكويز ──

async def cmd_addquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "`/addquiz ما ركن الإسلام الأول؟ | الصلاة | الشهادة | الزكاة | الصوم | 2 | 3`",
            parse_mode="Markdown"
        )
        return
    q, c1, c2, c3, c4, ans_s, pts_s = parts
    try:
        ans = int(ans_s) - 1
        pts = int(pts_s)
        assert 0 <= ans <= 3 and pts > 0
    except Exception:
        await msg.reply_text("⚠️ رقم الإجابة من 1 إلى 4، والنقاط موجبة.")
        return
    quiz = load_quiz()
    quiz.append({"q": q, "choices": [c1,c2,c3,c4], "answer": ans, "points": pts})
    save_quiz(quiz)
    await msg.reply_text(
        f"✅ *تمت الإضافة!*\n\n❓ {q}\n✅ *{[c1,c2,c3,c4][ans]}*\n⭐ {pts} نقاط",
        parse_mode="Markdown"
    )


async def cmd_listquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        return
    quiz = load_quiz()
    if not quiz:
        await msg.reply_text("لا توجد أسئلة بعد.")
        return
    lines = [f"📝 *أسئلة الكويز ({len(quiz)}):*\n"]
    for i, q in enumerate(quiz, 1):
        lines.append(f"{i}. {q['q']}\n   ✅ {q['choices'][q['answer']]}  ·  ⭐{q['points']}")
    lines.append("\n🗑️ `/delquiz رقم`")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_delquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await msg.reply_text(f"⚠️ يوجد {len(quiz)} سؤال فقط.")
        return
    removed = quiz.pop(idx)
    save_quiz(quiz)
    await msg.reply_text(f"✅ تم حذف: *{removed['q']}*", parse_mode="Markdown")


# ── التقويم ──

async def cmd_setcal(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    cal = load_cal()
    cal[section] = value
    save_cal(cal)
    await update.message.reply_text(f"✅ تم تحديث: *{section}*", parse_mode="Markdown")


# ── البث ──

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
        await update.message.reply_text("⚠️ لا يوجد طلاب مسجلون بعد.")
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
        f"✅ أُرسلت إلى *{ok}* طالب\n⚠️ فشل: *{bad}*",
        parse_mode="Markdown"
    )


# ================================================================
#  ١٥. معالج الكولباك
# ================================================================

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data

    # ── الرئيسية ──
    if data == "home":
        if update.effective_chat.type == "private":
            add_user(update.effective_chat.id)
        context.user_data.clear()
        return await q.message.edit_text(
            TXT_WELCOME, reply_markup=kb_main(), parse_mode="Markdown"
        )

    # ── مساعدة ──
    if data == "H:show":
        return await q.message.edit_text(
            TXT_HELP, reply_markup=kb_back("home"), parse_mode="Markdown"
        )

    # ── الكويز ──
    if data == "Q:start":
        quiz = load_quiz()
        if not quiz:
            return await q.message.edit_text(
                "⚠️ لا توجد أسئلة في بنك الكويز بعد.",
                reply_markup=kb_back("home")
            )
        qid  = random.randint(0, len(quiz) - 1)
        item = quiz[qid]
        context.user_data["qid"] = qid
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(c, callback_data=f"Q:a:{qid}:{i}")]
             for i, c in enumerate(item["choices"])]
            + [[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
        )
        return await q.message.edit_text(
            f"📝 *اختبار قصير*\n\n{item['q']}",
            reply_markup=kb, parse_mode="Markdown"
        )

    if data.startswith("Q:a:"):
        parts   = data.split(":")
        qid     = int(parts[2])
        choice  = int(parts[3])
        quiz    = load_quiz()
        if qid >= len(quiz):
            return await q.message.edit_text("⚠️ السؤال لم يعد موجوداً.")
        item     = quiz[qid]
        correct  = item["answer"]
        pts      = item.get("points", 1)
        is_right = (choice == correct)

        profile           = get_profile(update.effective_user.id)
        profile["points"] = profile.get("points", 0) + (pts if is_right else 0)
        profile["last_quiz"] = datetime.utcnow().isoformat()
        new_badges        = apply_achievements(profile)
        save_profile(update.effective_user.id, profile)

        result = (f"✅ إجابة صحيحة! +{pts} نقطة" if is_right
                  else f"❌ إجابة خاطئة.\n✅ الصحيح: *{item['choices'][correct]}*")
        extra  = ("\n\n🏆 " + " | ".join(new_badges)) if new_badges else ""

        return await q.message.edit_text(
            f"📝 *اختبار قصير*\n\n{item['q']}\n\n"
            f"{result}\n⭐ نقاطك: *{profile['points']}*{extra}\n\n"
            "اضغط لسؤال جديد:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 سؤال جديد", callback_data="Q:start")],
                [InlineKeyboardButton("🏆 نقاطي",      callback_data="P:show")],
                [InlineKeyboardButton("🏠 الرئيسية",   callback_data="home")],
            ]),
            parse_mode="Markdown"
        )

    # ── النقاط ──
    if data == "P:show":
        profile = get_profile(update.effective_user.id)
        badges  = profile.get("badges", [])
        b_txt   = "\n".join(f"  {b}" for b in badges) if badges else "  لا توجد إنجازات بعد"
        all_pts = sorted(load_points().values(),
                         key=lambda x: x.get("points", 0), reverse=True)
        rank    = next(
            (i+1 for i, p in enumerate(all_pts)
             if p.get("points", 0) == profile.get("points", 0)), "—"
        )
        return await q.message.edit_text(
            f"🏆 *نقاطي وإنجازاتي*\n\n"
            f"⭐ النقاط  : *{profile.get('points', 0)}*\n"
            f"🏅 الترتيب : *{rank}*\n\n"
            f"🎖️ الإنجازات:\n{b_txt}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 سؤال جديد", callback_data="Q:start")],
                [InlineKeyboardButton("🏠 الرئيسية",  callback_data="home")],
            ]),
            parse_mode="Markdown"
        )

    # ── التقويم ──
    if data == "C:home":
        cal = load_cal()
        kb  = [[InlineKeyboardButton(k, callback_data=f"C:i:{k}")] for k in cal]
        kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
        return await q.message.edit_text(
            "🗓️ *التقويم الجامعي*\nاختر القسم:",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )

    if data.startswith("C:i:"):
        key = data[4:]
        cal = load_cal()
        return await q.message.edit_text(
            f"🗓️ *{key}*\n\n{cal.get(key, 'لا توجد معلومات.')}",
            reply_markup=kb_back("C:home"), parse_mode="Markdown"
        )

    # ── الدروس — التنقل ──
    lessons = load_lessons()
    ud      = context.user_data

    if data == "D:years":
        ud.clear()
        return await q.message.edit_text(
            "📘 اختر السنة الدراسية:",
            reply_markup=kb_years(lessons)
        )

    if data.startswith("D:y:"):
        idx  = int(data[4:])
        keys = list(lessons.keys())
        if idx >= len(keys): return
        ud["year"] = keys[idx]
        return await q.message.edit_text(
            f"📙 *{ud['year']}*\nاختر التخصص:",
            reply_markup=kb_specs(lessons, ud["year"]),
            parse_mode="Markdown"
        )

    if data == "D:specs":
        for k in ("spec","sem","subj","items"): ud.pop(k, None)
        return await q.message.edit_text(
            f"📙 *{ud.get('year','')}*\nاختر التخصص:",
            reply_markup=kb_specs(lessons, ud.get("year","")),
            parse_mode="Markdown"
        )

    if data.startswith("D:s:"):
        idx  = int(data[4:])
        year = ud.get("year")
        if not year: return
        keys = list(lessons[year].keys())
        if idx >= len(keys): return
        ud["spec"] = keys[idx]
        return await q.message.edit_text(
            f"📗 *{ud['year']}  ·  {ud['spec']}*\nاختر السداسي:",
            reply_markup=kb_sems(lessons, year, ud["spec"]),
            parse_mode="Markdown"
        )

    if data == "D:sems":
        for k in ("sem","subj","items"): ud.pop(k, None)
        return await q.message.edit_text(
            f"📗 *{ud.get('year','')}  ·  {ud.get('spec','')}*\nاختر السداسي:",
            reply_markup=kb_sems(lessons, ud.get("year",""), ud.get("spec","")),
            parse_mode="Markdown"
        )

    if data.startswith("D:sm:"):
        idx  = int(data[5:])
        year = ud.get("year"); spec = ud.get("spec")
        if not (year and spec): return
        keys = list(lessons[year][spec].keys())
        if idx >= len(keys): return
        ud["sem"] = keys[idx]
        return await q.message.edit_text(
            f"📚 *{ud['sem']}*\nاختر المادة:",
            reply_markup=kb_subjects(lessons, year, spec, ud["sem"]),
            parse_mode="Markdown"
        )

    if data == "D:subjects":
        for k in ("subj","items"): ud.pop(k, None)
        year = ud.get("year"); spec = ud.get("spec"); sem = ud.get("sem")
        if not (year and spec and sem): return
        return await q.message.edit_text(
            f"📚 *{sem}*\nاختر المادة:",
            reply_markup=kb_subjects(lessons, year, spec, sem),
            parse_mode="Markdown"
        )

    if data.startswith("D:sb:"):
        idx  = int(data[5:])
        year = ud.get("year"); spec = ud.get("spec"); sem = ud.get("sem")
        if not (year and spec and sem): return
        keys = list(lessons[year][spec][sem].keys())
        if idx >= len(keys): return
        subj  = keys[idx]
        items = lessons[year][spec][sem][subj]
        ud["subj"]  = subj
        ud["items"] = items
        if not items:
            return await q.message.edit_text(
                f"📭 لا توجد دروس بعد في مادة *{subj}*",
                reply_markup=kb_back("D:subjects"),
                parse_mode="Markdown"
            )
        return await q.message.edit_text(
            f"📖 *{subj}*\nاختر الدرس:",
            reply_markup=kb_files(items),
            parse_mode="Markdown"
        )

    if data.startswith("D:f:"):
        i     = int(data[4:])
        items = ud.get("items", [])
        if not items or not (0 <= i < len(items)):
            return await q.message.reply_text("⚠️ حدث خطأ، أعد فتح المادة.")
        title, fid = items[i]
        if is_url(fid):
            return await q.message.reply_text(f"🔗 {fid}")
        try:
            await q.message.reply_document(document=fid, caption=f"📄 {title}")
        except BadRequest:
            await q.message.reply_text("⚠️ الملف غير متاح (file_id منتهي الصلاحية).")
        except Exception:
            await q.message.reply_text("⚠️ حدث خطأ أثناء الإرسال.")


# ================================================================
#  ١٦. رسائل الخاص
# ================================================================

async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    msg  = update.message
    user = update.effective_user

    # المشرف: إعطاء file_id تلقائياً عند إرسال PDF
    if user.id in ADMIN_IDS:
        if msg and msg.document:
            fid = msg.document.file_id
            await msg.reply_text(
                f"📎 *file\_id للملف:*\n`{fid}`\n\n"
                "لإضافته درساً، اعمل *Reply* على الملف واكتب:\n"
                "`/adddars السنة | التخصص | السداسي | المادة | العنوان`\n\n"
                "💡 /adminhelp لقائمة الأوامر الكاملة",
                parse_mode="Markdown"
            )
        return

    # الطالب: توجيه رسالته للمشرفين
    add_user(update.effective_chat.id)
    try:
        meta = await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"📩 *سؤال جديد*\n\n"
            f"👤 {user.full_name}\n"
            f"🆔 `{user.id}`\n\n"
            "↩️ اعمل *Reply* للرد على الطالب",
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
    except Exception as e:
        print(f"⚠️ خطأ في توجيه رسالة الطالب: {e}")
        await msg.reply_text("⚠️ حدث خطأ، حاول مجدداً.")


# ================================================================
#  ١٧. ردود المشرفين
# ================================================================

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
    try:
        if msg.text:
            await context.bot.send_message(
                sid, f"📩 *رد من المشرفين:*\n\n{msg.text}", parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(sid, "📩 *رد من المشرفين:*", parse_mode="Markdown")
            await context.bot.copy_message(
                chat_id=sid, from_chat_id=ADMIN_CHAT_ID, message_id=msg.message_id
            )
    except Exception as e:
        print(f"⚠️ خطأ في إرسال الرد: {e}")


# ================================================================
#  ١٨. بناء التطبيق
# ================================================================

def build_app() -> Application:
    token = _clean(os.environ.get("BOT_TOKEN", ""))
    if not token:
        raise RuntimeError("❌ BOT_TOKEN غير موجود في متغيرات البيئة.")

    app = Application.builder().token(token).post_init(on_startup).build()

    # أوامر عامة
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ping",      cmd_ping))
    app.add_handler(CommandHandler("adminhelp", cmd_adminhelp))

    # إدارة الدروس
    app.add_handler(CommandHandler("adddars",  cmd_adddars))
    app.add_handler(CommandHandler("listdars", cmd_listdars))
    app.add_handler(CommandHandler("deldars",  cmd_deldars))

    # إدارة الكويز
    app.add_handler(CommandHandler("addquiz",  cmd_addquiz))
    app.add_handler(CommandHandler("listquiz", cmd_listquiz))
    app.add_handler(CommandHandler("delquiz",  cmd_delquiz))

    # أوامر مجموعة المشرفين فقط
    app.add_handler(CommandHandler("stats",     cmd_stats,     filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("setcal",    cmd_setcal,    filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast, filters=filters.Chat(ADMIN_CHAT_ID)))

    # الكولباك والرسائل
    app.add_handler(CallbackQueryHandler(handle_cb))
    app.add_handler(MessageHandler(
        filters.Chat(ADMIN_CHAT_ID) & ~filters.COMMAND, handle_admin_reply
    ))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private
    ))

    return app


if __name__ == "__main__":
    build_app().run_polling()
