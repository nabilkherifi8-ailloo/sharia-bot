# ================================================================
#  bot.py — البوت المساعد لطالب الشريعة
#  جامعة البشير الإبراهيمي — النسخة المتكاملة
# ================================================================

import os
import json
import copy
import random
import hashlib
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from telegram.error import Forbidden, BadRequest


# ================================================================
#  ١. الإعدادات
# ================================================================

ADMIN_CHAT_ID = -1003784231419
ADMIN_IDS     = {1490829295}

FILE_MAP      = "msg_map.json"
FILE_USERS    = "users.json"
FILE_POINTS   = "points.json"
FILE_CAL      = "calendar.json"
FILE_LESSONS  = "lessons_data.json"
FILE_QUIZ     = "quiz_data.json"
FILE_SCHED    = "schedule_state.json"
FILE_PROFILES = "profiles.json"
FILE_NOTES    = "notes.json"
FILE_LIKES    = "likes.json"
FILE_POLL     = "poll.json"
FILE_TERMS    = "terms.json"

TZ = ZoneInfo("Africa/Algiers")

# الولايات الجزائرية لمواقيت الصلاة
WILAYAS = {
    "الجزائر العاصمة": "Algiers",
    "وهران":           "Oran",
    "قسنطينة":         "Constantine",
    "عنابة":           "Annaba",
    "سطيف":            "Setif",
    "برج بو عريريج":   "Bordj Bou Arreridj",
    "بسكرة":           "Biskra",
    "بجاية":           "Bejaia",
    "باتنة":           "Batna",
    "تلمسان":          "Tlemcen",
    "المسيلة":         "M'Sila",
    "تيزي وزو":        "Tizi Ouzou",
}

# ================================================================
#  المساعد الذكي — Anthropic API
# ================================================================

AI_SYSTEM = """أنت مساعد علمي متخصص في الدراسات الإسلامية، تساعد طلاب كلية الشريعة في جامعة البشير الإبراهيمي بالجزائر.

مهامك:
- الإجابة على الأسئلة الفقهية وأصول الفقه والحديث والتفسير والعقيدة والتاريخ الإسلامي
- تقديم إجابات علمية موثوقة ومنهجية تناسب مستوى الطالب الجامعي
- الاستشهاد بالمذاهب الفقهية الأربعة عند الحاجة
- شرح المصطلحات الصعبة بأسلوب واضح ومبسّط
- التنبيه دائماً على ضرورة الرجوع للعلماء في مسائل الفتوى الشخصية

قواعد:
- أجب باللغة العربية الفصحى دائماً
- كن دقيقاً ومختصراً مع الشمولية
- إذا كانت المسألة خلافية، اذكر أبرز الآراء مع أدلتها
- لا تُفتِ في المسائل الشخصية، بل أحل للعلماء
- ابدأ إجابتك مباشرة بدون مقدمات طويلة"""


async def ask_ai(question: str) -> str:
    """إرسال سؤال لـ Google Gemini والحصول على إجابة — مجاني تماماً"""
    api_key = _clean(os.environ.get("GEMINI_API_KEY", ""))
    if not api_key:
        return (
            "⚠️ المساعد الذكي غير مُفعَّل بعد.\n\n"
            "يرجى إضافة GEMINI_API_KEY في متغيرات Render.\n"
            "احصل على مفتاح مجاني من:\n"
            "aistudio.google.com/app/apikey"
        )
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.5-flash:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{
                "parts": [{"text": f"{AI_SYSTEM}\n\nسؤال الطالب: {question}"}]
            }],
            "generationConfig": {
                "maxOutputTokens": 1000,
                "temperature": 0.7,
            }
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()

        if "candidates" not in data:
            error = data.get("error", {}).get("message", "خطأ غير معروف")
            print(f"⚠️ Gemini error: {error}")
            return f"⚠️ خطأ في المساعد الذكي: {error}"

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except httpx.TimeoutException:
        return "⚠️ انتهت مهلة الاتصال، حاول مجدداً."
    except Exception as e:
        print(f"⚠️ AI error: {e}")
        return "⚠️ حدث خطأ في المساعد الذكي، حاول مجدداً."

# تصنيفات الدروس
CAT_DARS    = "📖 درس"
CAT_MULAKH  = "📋 ملخص"
CAT_IMTIHAN = "📝 امتحان"
CATS        = [CAT_DARS, CAT_MULAKH, CAT_IMTIHAN]


# ================================================================
#  ٢. البيانات المدمجة
# ================================================================

DEFAULT_QUIZ = [
    {"q": "عدد أركان الإسلام؟",
     "choices": ["3","4","5","6"], "answer": 2, "points": 2},
    {"q": "النية محلها؟",
     "choices": ["اللسان","القلب","اليد","العين"], "answer": 1, "points": 2},
    {"q": "وقت صلاة الفجر ينتهي بـ؟",
     "choices": ["طلوع الشمس","الزوال","غروب الشمس","منتصف الليل"], "answer": 0, "points": 2},
    {"q": "حكم الوضوء للصلاة؟",
     "choices": ["سنة","واجب","مكروه","مباح"], "answer": 1, "points": 2},
    {"q": "كم عدد سور القرآن الكريم؟",
     "choices": ["110","114","120","100"], "answer": 1, "points": 2},
    {"q": "أول سورة نزلت من القرآن الكريم؟",
     "choices": ["الفاتحة","البقرة","العلق","المدثر"], "answer": 2, "points": 3},
    {"q": "كم عدد أركان الصلاة؟",
     "choices": ["10","12","14","8"], "answer": 1, "points": 2},
    {"q": "الزكاة فرضت في السنة؟",
     "choices": ["الأولى","الثانية","الثالثة","الرابعة"], "answer": 1, "points": 3},
]

ACHIEVEMENTS = [
    (10,  "🥉 مجتهد — 10 نقاط"),
    (25,  "🥈 متفوق — 25 نقطة"),
    (50,  "🥇 نجم الشريعة — 50 نقطة"),
    (100, "🏅 حافظ — 100 نقطة"),
    (200, "🌟 علامة — 200 نقطة"),
]

AYAT_YAWM = [
    {"ref": "البقرة: 255",       "text": "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَهُ مَا فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ", "note": "آية الكرسي"},
    {"ref": "آل عمران: 18",      "text": "شَهِدَ اللَّهُ أَنَّهُ لَا إِلَٰهَ إِلَّا هُوَ وَالْمَلَائِكَةُ وَأُولُو الْعِلْمِ قَائِمًا بِالْقِسْطِ ۚ لَا إِلَٰهَ إِلَّا هُوَ الْعَزِيزُ الْحَكِيمُ", "note": ""},
    {"ref": "النساء: 36",        "text": "وَاعْبُدُوا اللَّهَ وَلَا تُشْرِكُوا بِهِ شَيْئًا ۖ وَبِالْوَالِدَيْنِ إِحْسَانًا وَبِذِي الْقُرْبَىٰ وَالْيَتَامَىٰ وَالْمَسَاكِينِ", "note": ""},
    {"ref": "المائدة: 3",        "text": "الْيَوْمَ أَكْمَلْتُ لَكُمْ دِينَكُمْ وَأَتْمَمْتُ عَلَيْكُمْ نِعْمَتِي وَرَضِيتُ لَكُمُ الْإِسْلَامَ دِينًا", "note": ""},
    {"ref": "الأنعام: 162",      "text": "قُلْ إِنَّ صَلَاتِي وَنُسُكِي وَمَحْيَايَ وَمَمَاتِي لِلَّهِ رَبِّ الْعَالَمِينَ", "note": ""},
    {"ref": "الإسراء: 23",       "text": "وَقَضَىٰ رَبُّكَ أَلَّا تَعْبُدُوا إِلَّا إِيَّاهُ وَبِالْوَالِدَيْنِ إِحْسَانًا", "note": ""},
    {"ref": "طه: 114",           "text": "فَتَعَالَى اللَّهُ الْمَلِكُ الْحَقُّ ۗ وَلَا تَعْجَلْ بِالْقُرْآنِ مِن قَبْلِ أَن يُقْضَىٰ إِلَيْكَ وَحْيُهُ ۖ وَقُل رَّبِّ زِدْنِي عِلْمًا", "note": ""},
    {"ref": "الزمر: 53",         "text": "قُلْ يَا عِبَادِيَ الَّذِينَ أَسْرَفُوا عَلَىٰ أَنفُسِهِمْ لَا تَقْنَطُوا مِن رَّحْمَةِ اللَّهِ ۚ إِنَّ اللَّهَ يَغْفِرُ الذُّنُوبَ جَمِيعًا", "note": "آية الرجاء"},
    {"ref": "الحشر: 22-23",      "text": "هُوَ اللَّهُ الَّذِي لَا إِلَٰهَ إِلَّا هُوَ ۖ عَالِمُ الْغَيْبِ وَالشَّهَادَةِ ۖ هُوَ الرَّحْمَٰنُ الرَّحِيمُ", "note": ""},
    {"ref": "الملك: 1",          "text": "تَبَارَكَ الَّذِي بِيَدِهِ الْمُلْكُ وَهُوَ عَلَىٰ كُلِّ شَيْءٍ قَدِيرٌ", "note": ""},
    {"ref": "القدر: 1",          "text": "إِنَّا أَنزَلْنَاهُ فِي لَيْلَةِ الْقَدْرِ", "note": ""},
    {"ref": "الفاتحة: 1-2",      "text": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ ۝ الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ", "note": "فاتحة الكتاب"},
    {"ref": "البقرة: 285",       "text": "آمَنَ الرَّسُولُ بِمَا أُنزِلَ إِلَيْهِ مِن رَّبِّهِ وَالْمُؤْمِنُونَ ۚ كُلٌّ آمَنَ بِاللَّهِ وَمَلَائِكَتِهِ وَكُتُبِهِ وَرُسُلِهِ", "note": ""},
    {"ref": "الإخلاص: 1-4",      "text": "قُلْ هُوَ اللَّهُ أَحَدٌ ۝ اللَّهُ الصَّمَدُ ۝ لَمْ يَلِدْ وَلَمْ يُولَدْ ۝ وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ", "note": "سورة الإخلاص"},
]

ADYIA_YAWM = [
    {"title": "دعاء طلب العلم",     "text": "اللهم انفعني بما علّمتني وعلّمني ما ينفعني وزدني علماً وارزقني فهماً"},
    {"title": "دعاء الصباح",        "text": "اللهم بك أصبحنا وبك أمسينا وبك نحيا وبك نموت وإليك النشور"},
    {"title": "دعاء المساء",         "text": "اللهم بك أمسينا وبك أصبحنا وبك نحيا وبك نموت وإليك المصير"},
    {"title": "دعاء الاستفتاح",     "text": "اللهم باعد بيني وبين خطاياي كما باعدت بين المشرق والمغرب"},
    {"title": "دعاء القنوت",        "text": "اللهم اهدني فيمن هديت وعافني فيمن عافيت وتولني فيمن توليت"},
    {"title": "دعاء ختم القرآن",    "text": "اللهم ارحمني بالقرآن واجعله لي إماماً ونوراً وهدى ورحمة"},
    {"title": "دعاء المذاكرة",      "text": "اللهم لا سهل إلا ما جعلته سهلاً وأنت تجعل الحزن إذا شئت سهلاً"},
    {"title": "دعاء الفرج",         "text": "اللهم إني أسألك يا الله بأنك الواحد الأحد الصمد الذي لم يلد ولم يولد ولم يكن له كفواً أحد"},
    {"title": "دعاء الكرب",         "text": "لا إله إلا الله العظيم الحليم لا إله إلا الله رب العرش العظيم"},
    {"title": "دعاء التوبة",        "text": "اللهم أنت ربي لا إله إلا أنت خلقتني وأنا عبدك وأنا على عهدك ووعدك ما استطعت"},
    {"title": "دعاء طلب الثبات",    "text": "يا مقلب القلوب ثبت قلبي على دينك"},
    {"title": "دعاء الرزق",         "text": "اللهم اكفني بحلالك عن حرامك وأغنني بفضلك عمن سواك"},
    {"title": "دعاء السفر",         "text": "سبحان الذي سخّر لنا هذا وما كنا له مقرنين وإنا إلى ربنا لمنقلبون"},
    {"title": "دعاء النوم",          "text": "اللهم باسمك أموت وأحيا"},
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

def lesson_key(year, spec, sem, subj, idx):
    s = f"{year}|{spec}|{sem}|{subj}|{idx}"
    return hashlib.md5(s.encode()).hexdigest()[:10]

def get_cat(item):
    """استخراج تصنيف الدرس — افتراضي: درس"""
    return item[2] if len(item) > 2 else CAT_DARS

def cat_icon(cat):
    return {"📖 درس": "📖", "📋 ملخص": "📋", "📝 امتحان": "📝"}.get(cat, "📄")


# ================================================================
#  ٤. الدروس
# ================================================================

def load_lessons():
    if os.path.exists(FILE_LESSONS):
        d = _load(FILE_LESSONS, None)
        if isinstance(d, dict) and d:
            return d
    try:
        from lessons import LESSONS as _D
        d = copy.deepcopy(_D)
        _save(FILE_LESSONS, d)
        print("✅ lessons_data.json تم إنشاؤه")
        return d
    except ImportError:
        print("❌ lessons.py غير موجود")
    except Exception as e:
        print(f"❌ خطأ في الدروس: {e}")
    return {}

def save_lessons(d):
    _save(FILE_LESSONS, d)

def total_lessons(d):
    return sum(len(v) for y in d.values() for s in y.values()
               for sm in s.values() for v in sm.values())


# ================================================================
#  ٥. الكويز
# ================================================================

def load_quiz():
    d = _load(FILE_QUIZ, None)
    if isinstance(d, list) and d: return d
    _save(FILE_QUIZ, DEFAULT_QUIZ)
    return copy.deepcopy(DEFAULT_QUIZ)

def save_quiz(d): _save(FILE_QUIZ, d)


# ================================================================
#  ٦. المستخدمون
# ================================================================

def load_users():
    d = _load(FILE_USERS, [])
    try: return set(int(x) for x in d)
    except: return set()

def save_users(u): _save(FILE_USERS, sorted(list(u)))

def add_user(cid):
    u = load_users()
    if int(cid) not in u:
        u.add(int(cid)); save_users(u)


# ================================================================
#  ٧. النقاط
# ================================================================

def load_points(): return _load(FILE_POINTS, {})
def save_points(p): _save(FILE_POINTS, p)

def get_profile_points(uid):
    p, k = load_points(), str(uid)
    if k not in p:
        p[k] = {"points": 0, "badges": [], "last_quiz": None}
        save_points(p)
    return p[k]

def save_profile_points(uid, prof):
    p = load_points(); p[str(uid)] = prof; save_points(p)

def apply_achievements(prof):
    badges, new = set(prof.get("badges", [])), []
    for thr, badge in ACHIEVEMENTS:
        if prof["points"] >= thr and badge not in badges:
            badges.add(badge); new.append(badge)
    prof["badges"] = sorted(badges)
    return new


# ================================================================
#  ٨. التقويم
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

def save_cal(c): _save(FILE_CAL, c)


# ================================================================
#  ٩. الملف الشخصي للطالب
# ================================================================

def load_profiles(): return _load(FILE_PROFILES, {})
def save_profiles(p): _save(FILE_PROFILES, p)

def get_student_profile(uid):
    p, k = load_profiles(), str(uid)
    return p.get(k, {})

def save_student_profile(uid, data):
    p = load_profiles(); p[str(uid)] = data; save_profiles(p)


# ================================================================
#  ١٠. الملاحظات الشخصية
# ================================================================

def load_notes(): return _load(FILE_NOTES, {})
def save_notes(n): _save(FILE_NOTES, n)

def get_user_notes(uid):
    return load_notes().get(str(uid), [])

def add_note(uid, text):
    n = load_notes()
    k = str(uid)
    n.setdefault(k, [])
    n[k].append({"text": text, "date": datetime.now(TZ).strftime("%Y-%m-%d %H:%M")})
    save_notes(n)

def delete_note(uid, idx):
    n = load_notes()
    k = str(uid)
    if k in n and 0 <= idx < len(n[k]):
        removed = n[k].pop(idx)
        save_notes(n)
        return removed
    return None


# ================================================================
#  ١١. نظام الإعجاب
# ================================================================

def load_likes(): return _load(FILE_LIKES, {})
def save_likes(l): _save(FILE_LIKES, l)

def toggle_like(key, uid, title="", subj=""):
    l = load_likes()
    l.setdefault(key, {"count": 0, "users": [], "title": title, "subj": subj})
    uid_s = str(uid)
    if uid_s in l[key]["users"]:
        l[key]["users"].remove(uid_s)
        l[key]["count"] = max(0, l[key]["count"] - 1)
        save_likes(l)
        return False, l[key]["count"]   # removed
    else:
        l[key]["users"].append(uid_s)
        l[key]["count"] += 1
        save_likes(l)
        return True, l[key]["count"]    # added

def get_like_count(key):
    return load_likes().get(key, {}).get("count", 0)

def user_liked(key, uid):
    return str(uid) in load_likes().get(key, {}).get("users", [])


# ================================================================
#  ١٢. استطلاع الرأي
# ================================================================

def load_poll(): return _load(FILE_POLL, {"active": False})
def save_poll(p): _save(FILE_POLL, p)


# ================================================================
#  ١٣. قاموس المصطلحات
# ================================================================

def load_terms(): return _load(FILE_TERMS, {})
def save_terms(t): _save(FILE_TERMS, t)


# ================================================================
#  ١٤. ربط الرسائل
# ================================================================

def load_map(): return _load(FILE_MAP, {})
def save_map(m): _save(FILE_MAP, m)


# ================================================================
#  ١٥. البث للجميع
# ================================================================

async def send_to_all(bot, text, parse_mode=None, reply_markup=None):
    users, dead = load_users(), set()
    for uid in list(users):
        try:
            await bot.send_message(uid, text, parse_mode=parse_mode,
                                   reply_markup=reply_markup)
        except Forbidden:
            dead.add(uid)
        except Exception:
            pass
    if dead: save_users(users - dead)


# ================================================================
#  ١٦. مواقيت الصلاة
# ================================================================

async def fetch_prayer_times(city_en: str):
    url = (f"https://api.aladhan.com/v1/timingsByCity"
           f"?city={city_en}&country=Algeria&method=2")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url)
            data = r.json()
            return data["data"]["timings"], data["data"]["date"]["readable"]
    except Exception as e:
        print(f"⚠️ prayer API error: {e}")
        return None, None


# ================================================================
#  ١٧. الجدولة اليومية
# ================================================================

FIXED_MSGS = [
    (7,  0, "morning",
     "🌿 *أذكار الصباح*\n\n"
     "اللهم بك أصبحنا وبك أمسينا وبك نحيا وبك نموت وإليك النشور.\n"
     "أصبحنا وأصبح الملك لله والحمد لله لا شريك له."),
    (17, 0, "evening",
     "🌙 *أذكار المساء*\n\n"
     "اللهم بك أمسينا وبك أصبحنا وبك نحيا وبك نموت وإليك المصير.\n"
     "أمسينا وأمسى الملك لله والحمد لله لا شريك له."),
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
            if not isinstance(st, dict): st = {}
            st.setdefault(today, {})

            for h, m, key, text in FIXED_MSGS:
                if now.hour == h and now.minute == m and not st[today].get(key):
                    await send_to_all(app.bot, text, parse_mode="Markdown")
                    st[today][key] = True; _save(FILE_SCHED, st)

            for h, m, key, cal_key in CAL_MSGS:
                if now.hour == h and now.minute == m and not st[today].get(key):
                    cal  = load_cal()
                    body = cal.get(cal_key, "لم يتم الضبط بعد.")
                    await send_to_all(app.bot, f"{cal_key}\n\n{body}")
                    st[today][key] = True; _save(FILE_SCHED, st)

            # آية اليوم 08:00
            if now.hour == 8 and now.minute == 0 and not st[today].get("ayah"):
                ayah = AYAT_YAWM[now.timetuple().tm_yday % len(AYAT_YAWM)]
                text = (f"📖 *آية اليوم*\n\n"
                        f"*{ayah['ref']}*\n\n{ayah['text']}"
                        + (f"\n\n_{ayah['note']}_" if ayah['note'] else ""))
                await send_to_all(app.bot, text, parse_mode="Markdown")
                st[today]["ayah"] = True; _save(FILE_SCHED, st)

            # دعاء اليوم 21:00
            if now.hour == 21 and now.minute == 0 and not st[today].get("dua"):
                dua  = ADYIA_YAWM[now.timetuple().tm_yday % len(ADYIA_YAWM)]
                text = f"🤲 *دعاء اليوم*\n\n*{dua['title']}*\n\n{dua['text']}"
                await send_to_all(app.bot, text, parse_mode="Markdown")
                st[today]["dua"] = True; _save(FILE_SCHED, st)

        except Exception as e:
            print(f"⚠️ scheduler: {e}")

        await asyncio.sleep(30)


async def on_startup(app: Application):
    app.create_task(scheduler_loop(app))
    print("✅ البوت يعمل")


# ================================================================
#  ١٨. لوحات المفاتيح
# ================================================================

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 الدروس",            callback_data="D:years")],
        [InlineKeyboardButton("📝 اختبار قصير",       callback_data="Q:start"),
         InlineKeyboardButton("🏆 نقاطي",             callback_data="P:show")],
        [InlineKeyboardButton("🗓️ التقويم",            callback_data="C:home"),
         InlineKeyboardButton("🕌 الصلاة",             callback_data="PRAY:cities")],
        [InlineKeyboardButton("📖 آية اليوم",          callback_data="AY:show"),
         InlineKeyboardButton("📿 أذكار",              callback_data="DHKR:show")],
        [InlineKeyboardButton("🤲 دعاء اليوم",         callback_data="DUA:show"),
         InlineKeyboardButton("📚 القاموس",            callback_data="TERM:home")],
        [InlineKeyboardButton("📝 ملاحظاتي",           callback_data="NOTE:list"),
         InlineKeyboardButton("👤 ملفي",               callback_data="PROF:show")],
        [InlineKeyboardButton("💬 اقتراح درس",          callback_data="SUG:start"),
         InlineKeyboardButton("❓ مساعدة",             callback_data="H:show")],
        [InlineKeyboardButton("🤖 المساعد الذكي",       callback_data="AI:show")],
    ])

def kb_years(lessons):
    if not lessons:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ لا توجد دروس — تحقق من lessons.py", callback_data="home")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
        ])
    rows = [[InlineKeyboardButton(y, callback_data=f"D:y:{i}")]
            for i, y in enumerate(lessons)]
    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(rows)

def kb_specs(lessons, year):
    rows = [[InlineKeyboardButton(s, callback_data=f"D:s:{i}")]
            for i, s in enumerate(lessons[year])]
    rows += [[InlineKeyboardButton("⬅️ رجوع", callback_data="D:years")],
             [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
    return InlineKeyboardMarkup(rows)

def kb_sems(lessons, year, spec):
    rows = [[InlineKeyboardButton(sm, callback_data=f"D:sm:{i}")]
            for i, sm in enumerate(lessons[year][spec])]
    rows += [[InlineKeyboardButton("⬅️ رجوع", callback_data="D:specs")],
             [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
    return InlineKeyboardMarkup(rows)

def kb_subjects(lessons, year, spec, sem):
    subs = lessons[year][spec][sem]
    rows = []
    for i, (name, items) in enumerate(subs.items()):
        label = f"{name}  ·  {len(items)} 📄" if items else name
        rows.append([InlineKeyboardButton(label, callback_data=f"D:sb:{i}")])
    rows += [[InlineKeyboardButton("⬅️ رجوع", callback_data="D:sems")],
             [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
    return InlineKeyboardMarkup(rows)

def kb_files(items, year, spec, sem, subj, cat_filter="all"):
    rows = []
    for i, item in enumerate(items):
        cat = get_cat(item)
        if cat_filter != "all" and cat != cat_filter:
            continue
        icon = cat_icon(cat)
        if is_url(item[1]):
            rows.append([InlineKeyboardButton(f"{icon} {item[0]}", url=item[1])])
        else:
            rows.append([InlineKeyboardButton(f"{icon} {item[0]}", callback_data=f"D:f:{i}")])
    # أزرار التصفية
    filter_row = [
        InlineKeyboardButton("📄 الكل" if cat_filter == "all" else "الكل", callback_data="D:cat:all"),
        InlineKeyboardButton("📖 دروس",  callback_data="D:cat:درس"),
        InlineKeyboardButton("📋 ملخص",  callback_data="D:cat:ملخص"),
        InlineKeyboardButton("📝 امتحان", callback_data="D:cat:امتحان"),
    ]
    rows.append(filter_row)
    rows += [[InlineKeyboardButton("⬅️ رجوع", callback_data="D:subjects")],
             [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
    return InlineKeyboardMarkup(rows)

def kb_back(target):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ رجوع",     callback_data=target)],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])

def kb_like(key, count, liked):
    icon = "❤️" if liked else "🤍"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{icon} أعجبني ({count})", callback_data=f"LIKE:{key}")
    ]])

def kb_dhikr(s, h, a):
    done_s = "✅" if s >= 33 else ""
    done_h = "✅" if h >= 33 else ""
    done_a = "✅" if a >= 34 else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"سبحان الله  {s}/33 {done_s}",   callback_data="DHKR:+:s")],
        [InlineKeyboardButton(f"الحمد لله   {h}/33 {done_h}",   callback_data="DHKR:+:h")],
        [InlineKeyboardButton(f"الله أكبر   {a}/34 {done_a}",   callback_data="DHKR:+:a")],
        [InlineKeyboardButton("🔄 إعادة",     callback_data="DHKR:reset"),
         InlineKeyboardButton("✖️ إغلاق",     callback_data="DHKR:close")],
    ])

def kb_poll_vote(options, poll_id="0"):
    rows = [[InlineKeyboardButton(f"  {opt}", callback_data=f"POLL:v:{i}")]
            for i, opt in enumerate(options)]
    return InlineKeyboardMarkup(rows)

def kb_wilayas():
    rows = []
    items = list(WILAYAS.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(items[i][0], callback_data=f"PRAY:w:{items[i][1]}")]
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(items[i+1][0], callback_data=f"PRAY:w:{items[i+1][1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(rows)


# ================================================================
#  ١٩. النصوص الثابتة
# ================================================================

TXT_WELCOME = (
    "السلام عليكم ورحمة الله وبركاته 🌿\n\n"
    "أهلاً بك في *البوت المساعد لطالب الشريعة*\n"
    "جامعة البشير الإبراهيمي 🕌\n\n"
    "📚 دروس · 📝 اختبارات · 🗓️ تقويم\n"
    "🕌 صلاة · 📿 أذكار · 🤲 أدعية\n"
    "📝 ملاحظات · 👤 ملف شخصي · 📚 قاموس"
)

TXT_HELP = (
    "❓ *دليل الاستخدام*\n\n"
    "📚 *الدروس* — تصفّح حسب السنة والمادة\n"
    "📝 *الاختبار* — أسئلة عشوائية مع نقاط\n"
    "🏆 *نقاطي* — نقاطك وإنجازاتك وترتيبك\n"
    "🗓️ *التقويم* — امتحانات وعطل وآجال\n"
    "🕌 *الصلاة* — مواقيت الصلاة لولايتك\n"
    "📖 *آية اليوم* — آية مع ملاحظة تفسيرية\n"
    "📿 *أذكار* — عداد تسبيح تفاعلي\n"
    "🤲 *دعاء اليوم* — دعاء مختار يومياً\n"
    "📚 *القاموس* — شرح المصطلحات الفقهية\n"
    "📝 *ملاحظاتي* — سجّل ملاحظاتك الشخصية\n"
    "👤 *ملفي* — اسمك وتخصصك وسنتك\n"
    "💬 *اقتراح درس* — اطلب إضافة درس\n"
    "🤖 *المساعد الذكي* — اسأل أي سؤال شرعي أو علمي\n\n"
    "✍️ *سؤال للمشرفين:* أرسل أي رسالة هنا\n\n"
    "⏰ *رسائل يومية تلقائية:*\n"
    "   07:00 أذكار الصباح\n"
    "   08:00 آية اليوم\n"
    "   10:00 ورد اليوم\n"
    "   17:00 أذكار المساء\n"
    "   20:00 حديث اليوم\n"
    "   21:00 دعاء اليوم"
)

TXT_ADMIN = (
    "🛠️ *أوامر المشرف*\n\n"
    "━━━ 📚 الدروس ━━━\n"
    "➕ إضافة PDF *(Reply على الملف)*:\n"
    "`/adddars سنة | تخصص | سداسي | مادة | عنوان`\n"
    "`/adddars سنة | تخصص | سداسي | مادة | عنوان | ملخص`  ← مع تصنيف\n\n"
    "➕ إضافة رابط:\n"
    "`/adddars سنة | تخصص | سداسي | مادة | عنوان | https://...`\n"
    "`/adddars سنة | تخصص | سداسي | مادة | عنوان | https://... | امتحان`\n\n"
    "_التصنيفات: درس / ملخص / امتحان_\n\n"
    "📋 `/listdars سنة | تخصص | سداسي | مادة`\n"
    "🗑️ `/deldars سنة | تخصص | سداسي | مادة | رقم`\n\n"
    "━━━ 📝 الكويز ━━━\n"
    "➕ `/addquiz سؤال | خ1 | خ2 | خ3 | خ4 | رقم | نقاط`\n"
    "📋 `/listquiz`   🗑️ `/delquiz رقم`\n\n"
    "━━━ 🗳️ الاستطلاع ━━━\n"
    "➕ `/poll السؤال | خيار1 | خيار2 | خيار3`\n"
    "📊 `/pollresults`   🔒 `/endpoll`\n\n"
    "━━━ 📚 القاموس ━━━\n"
    "➕ `/addterm مصطلح | تعريف`\n"
    "🗑️ `/delterm مصطلح`   📋 `/listterms`\n\n"
    "━━━ 📢 عام ━━━\n"
    "📊 `/stats`   🏓 `/ping`\n"
    "📢 `/broadcast النص` أو Reply + `/broadcast`\n"
    "🗓️ `/setcal القسم | النص`\n"
    "📎 أرسل PDF في الخاص للحصول على file\\_id"
)


# ================================================================
#  ٢٠. الأوامر الأساسية
# ================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        add_user(update.effective_chat.id)
    context.user_data.clear()
    prof = get_student_profile(update.effective_user.id)
    greet = f"أهلاً *{prof['name']}* 🌿\n\n" if prof.get("name") else ""
    await update.message.reply_text(
        greet + TXT_WELCOME, reply_markup=kb_main(), parse_mode="Markdown"
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = datetime.now(TZ).strftime("%H:%M:%S")
    await update.message.reply_text(f"🏓 البوت يعمل ✅\n🕐 {t}")

async def cmd_adminhelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_text(TXT_ADMIN, parse_mode="Markdown")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    users   = load_users()
    lessons = load_lessons()
    quiz    = load_quiz()
    points  = load_points()
    terms   = load_terms()
    top3    = sorted([(u, d.get("points", 0)) for u, d in points.items()],
                     key=lambda x: x[1], reverse=True)[:3]
    top_txt = "\n".join(f"  {r+1}. `{u}` — {p} نقطة" for r, (u, p) in enumerate(top3)) \
              or "  لا توجد بيانات"
    await update.message.reply_text(
        "📊 *إحصائيات البوت*\n\n"
        f"👥 الطلاب : *{len(users)}*\n"
        f"📚 الدروس : *{total_lessons(lessons)}*\n"
        f"📝 الكويز : *{len(quiz)}*\n"
        f"📚 القاموس: *{len(terms)}* مصطلح\n"
        f"🏆 النشطون: *{len(points)}*\n\n"
        f"🥇 *أعلى الطلاب:*\n{top_txt}",
        parse_mode="Markdown"
    )


# ================================================================
#  ٢١. إدارة الدروس
# ================================================================

async def cmd_adddars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id):
        if msg: await msg.reply_text("❌ ليس لديك صلاحية.")
        return

    raw   = (msg.text or "").replace("/adddars", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    doc   = getattr(getattr(msg, "reply_to_message", None), "document", None)

    year = spec = sem = subj = title = value = cat = None

    if len(parts) == 5:
        year, spec, sem, subj, title = parts
        if not doc:
            await msg.reply_text(
                "⚠️ اعمل *Reply* على ملف PDF ثم اكتب الأمر\n"
                "أو أضف رابطاً كحقل سادس.",
                parse_mode="Markdown")
            return
        value, cat = doc.file_id, CAT_DARS

    elif len(parts) == 6:
        year, spec, sem, subj, title, p5 = parts
        if is_url(p5):
            value, cat = p5, CAT_DARS
        else:
            if not doc:
                await msg.reply_text("⚠️ لم أجد ملف PDF في الرسالة المردود عليها.")
                return
            value = doc.file_id
            cat   = next((c for c in CATS if p5 in c), CAT_DARS)

    elif len(parts) == 7:
        year, spec, sem, subj, title, url, cat_s = parts
        if not is_url(url):
            await msg.reply_text("⚠️ الحقل السادس يجب أن يكون رابطاً.")
            return
        value = url
        cat   = next((c for c in CATS if cat_s in c), CAT_DARS)

    else:
        await msg.reply_text("⚠️ صيغة خاطئة. /adminhelp للتفاصيل.")
        return

    lessons = load_lessons()
    (lessons.setdefault(year, {})
            .setdefault(spec, {})
            .setdefault(sem, {})
            .setdefault(subj, [])
            .append([title, value, cat]))
    save_lessons(lessons)

    await msg.reply_text(
        f"✅ *تمت الإضافة!*\n\n"
        f"📚 {year} ← {spec}\n"
        f"📅 {sem} ← {subj}\n"
        f"{cat_icon(cat)} [{cat}] *{title}*",
        parse_mode="Markdown"
    )

async def cmd_listdars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id): return
    raw   = (msg.text or "").replace("/listdars", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 4:
        await msg.reply_text("`/listdars سنة | تخصص | سداسي | مادة`", parse_mode="Markdown")
        return
    year, spec, sem, subj = parts
    try:    items = load_lessons()[year][spec][sem][subj]
    except: await msg.reply_text("⚠️ المسار غير موجود."); return
    if not items:
        await msg.reply_text(f"📭 لا توجد دروس في *{subj}*", parse_mode="Markdown"); return
    lines = [f"📚 *{subj} ({len(items)}):*\n"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {cat_icon(get_cat(it))} [{get_cat(it).split()[1]}] {it[0]}")
    lines.append(f"\n🗑️ `/deldars {year} | {spec} | {sem} | {subj} | رقم`")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_deldars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id): return
    raw   = (msg.text or "").replace("/deldars", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 5:
        await msg.reply_text("`/deldars سنة | تخصص | سداسي | مادة | رقم`", parse_mode="Markdown")
        return
    year, spec, sem, subj, idx_s = parts
    try:
        idx = int(idx_s) - 1
        assert idx >= 0
    except:
        await msg.reply_text("⚠️ رقم غير صحيح."); return
    lessons = load_lessons()
    try:    items = lessons[year][spec][sem][subj]
    except: await msg.reply_text("⚠️ المسار غير موجود."); return
    if idx >= len(items):
        await msg.reply_text(f"⚠️ يوجد {len(items)} درس فقط."); return
    removed = items.pop(idx)
    save_lessons(lessons)
    await msg.reply_text(f"✅ حُذف: *{removed[0]}*", parse_mode="Markdown")


# ================================================================
#  ٢٢. إدارة الكويز
# ================================================================

async def cmd_addquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id): return
    raw   = (msg.text or "").replace("/addquiz", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 7:
        await msg.reply_text(
            "`/addquiz سؤال | خ1 | خ2 | خ3 | خ4 | رقم_الصحيح | نقاط`",
            parse_mode="Markdown"); return
    q, c1, c2, c3, c4, ans_s, pts_s = parts
    try:
        ans = int(ans_s) - 1; pts = int(pts_s)
        assert 0 <= ans <= 3 and pts > 0
    except:
        await msg.reply_text("⚠️ رقم الإجابة 1-4 والنقاط موجبة."); return
    quiz = load_quiz()
    quiz.append({"q": q, "choices": [c1,c2,c3,c4], "answer": ans, "points": pts})
    save_quiz(quiz)
    await msg.reply_text(f"✅ تمت الإضافة!\n❓ {q}\n✅ *{[c1,c2,c3,c4][ans]}*",
                         parse_mode="Markdown")

async def cmd_listquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id): return
    quiz = load_quiz()
    if not quiz: await msg.reply_text("لا توجد أسئلة."); return
    lines = [f"📝 *الكويز ({len(quiz)}):*\n"]
    for i, q in enumerate(quiz, 1):
        lines.append(f"{i}. {q['q']}\n   ✅ {q['choices'][q['answer']]}  ⭐{q['points']}")
    lines.append("\n🗑️ `/delquiz رقم`")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_delquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id): return
    raw = (msg.text or "").replace("/delquiz", "", 1).strip()
    try:
        idx = int(raw) - 1; assert idx >= 0
    except:
        await msg.reply_text("`/delquiz رقم`", parse_mode="Markdown"); return
    quiz = load_quiz()
    if idx >= len(quiz): await msg.reply_text(f"⚠️ يوجد {len(quiz)} سؤال."); return
    removed = quiz.pop(idx); save_quiz(quiz)
    await msg.reply_text(f"✅ حُذف: *{removed['q']}*", parse_mode="Markdown")


# ================================================================
#  ٢٣. الاستطلاع
# ================================================================

async def cmd_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    msg = update.message
    raw = (msg.text or "").replace("/poll", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        await msg.reply_text("`/poll السؤال | خيار1 | خيار2 | خيار3`", parse_mode="Markdown")
        return
    question = parts[0]
    options  = parts[1:]
    poll_data = {"active": True, "question": question,
                 "options": options, "votes": {}}
    save_poll(poll_data)

    text = (f"🗳️ *استطلاع رأي*\n\n*{question}*\n\n"
            "اضغط على خيارك 👇")
    kb = kb_poll_vote(options)
    await send_to_all(context.bot, text, parse_mode="Markdown", reply_markup=kb)
    await msg.reply_text("✅ تم إرسال الاستطلاع لجميع الطلاب.")

async def cmd_pollresults(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    poll = load_poll()
    if not poll.get("question"):
        await update.message.reply_text("لا يوجد استطلاع."); return
    votes   = poll.get("votes", {})
    options = poll.get("options", [])
    total   = len(votes)
    lines   = [f"📊 *نتائج الاستطلاع*\n\n*{poll['question']}*\n\nالمشاركون: {total}\n"]
    counts = [sum(1 for v in votes.values() if v == i) for i in range(len(options))]
    for i, opt in enumerate(options):
        pct  = round(counts[i]/total*100) if total else 0
        bar  = "█" * (pct // 10) + "░" * (10 - pct // 10)
        lines.append(f"{i+1}. {opt}\n   {bar} {counts[i]} ({pct}%)\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_endpoll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    poll = load_poll()
    poll["active"] = False
    save_poll(poll)
    await update.message.reply_text("🔒 تم إغلاق الاستطلاع.")


# ================================================================
#  ٢٤. القاموس الفقهي
# ================================================================

async def cmd_addterm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id): return
    raw = (msg.text or "").replace("/addterm", "", 1).strip()
    if "|" not in raw:
        await msg.reply_text("`/addterm مصطلح | تعريف`", parse_mode="Markdown"); return
    term, definition = [x.strip() for x in raw.split("|", 1)]
    terms = load_terms()
    terms[term] = definition
    save_terms(terms)
    await msg.reply_text(f"✅ أُضيف: *{term}*", parse_mode="Markdown")

async def cmd_delterm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id): return
    term = (msg.text or "").replace("/delterm", "", 1).strip()
    terms = load_terms()
    if term not in terms:
        await msg.reply_text(f"⚠️ المصطلح '{term}' غير موجود."); return
    del terms[term]; save_terms(terms)
    await msg.reply_text(f"✅ حُذف: *{term}*", parse_mode="Markdown")

async def cmd_listterms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not is_admin(update.effective_user.id, update.effective_chat.id): return
    terms = load_terms()
    if not terms: await msg.reply_text("القاموس فارغ."); return
    lines = [f"📚 *القاموس ({len(terms)} مصطلح):*\n"]
    for t, d in list(terms.items())[:30]:
        lines.append(f"• *{t}*: {d[:60]}{'...' if len(d) > 60 else ''}")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


# ================================================================
#  ٢٥. التقويم والبث
# ================================================================

async def cmd_setcal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID: return
    txt = (update.message.text or "").replace("/setcal", "", 1).strip()
    if "|" not in txt:
        await update.message.reply_text("`/setcal القسم | النص`", parse_mode="Markdown"); return
    sec, val = [x.strip() for x in txt.split("|", 1)]
    cal = load_cal(); cal[sec] = val; save_cal(cal)
    await update.message.reply_text(f"✅ تم تحديث: *{sec}*", parse_mode="Markdown")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID: return
    try:
        member = await context.bot.get_chat_member(ADMIN_CHAT_ID, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ للمشرفين فقط."); return
    except:
        await update.message.reply_text("❌ تعذّر التحقق."); return

    users = load_users()
    if not users: await update.message.reply_text("لا يوجد طلاب."); return
    ok = bad = 0; dead = set()

    if context.args:
        text = " ".join(context.args)
        for uid in list(users):
            try:
                await context.bot.send_message(uid, f"📢 *إعلان:*\n\n{text}", parse_mode="Markdown")
                ok += 1
            except Forbidden: dead.add(uid); bad += 1
            except: bad += 1
    elif update.message.reply_to_message:
        src = update.message.reply_to_message
        for uid in list(users):
            try:
                await context.bot.copy_message(uid, ADMIN_CHAT_ID, src.message_id)
                ok += 1
            except Forbidden: dead.add(uid); bad += 1
            except: bad += 1
    else:
        await update.message.reply_text(
            "اكتب `/broadcast النص`\nأو Reply + `/broadcast`",
            parse_mode="Markdown"); return

    if dead: save_users(users - dead)
    await update.message.reply_text(f"✅ أُرسلت إلى *{ok}*\n⚠️ فشل: *{bad}*", parse_mode="Markdown")


# ================================================================
#  ٢٦. معالج الكولباك الرئيسي
# ================================================================

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    uid  = update.effective_user.id
    ud   = context.user_data

    # ── الرئيسية ──────────────────────────────────────────────
    if data == "home":
        context.user_data.clear()
        if update.effective_chat.type == "private":
            add_user(update.effective_chat.id)
        prof   = get_student_profile(uid)
        greet  = f"أهلاً *{prof['name']}* 🌿\n\n" if prof.get("name") else ""
        return await q.message.edit_text(
            greet + TXT_WELCOME, reply_markup=kb_main(), parse_mode="Markdown"
        )

    # ── مساعدة ──────────────────────────────────────────────
    if data == "H:show":
        return await q.message.edit_text(TXT_HELP, reply_markup=kb_back("home"),
                                         parse_mode="Markdown")

    # ── الكويز ──────────────────────────────────────────────
    if data == "Q:start":
        quiz = load_quiz()
        if not quiz:
            return await q.message.edit_text("⚠️ بنك الكويز فارغ.",
                                             reply_markup=kb_back("home"))
        qid  = random.randint(0, len(quiz)-1)
        item = quiz[qid]
        ud["qid"] = qid
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(c, callback_data=f"Q:a:{qid}:{i}")]
             for i, c in enumerate(item["choices"])]
            + [[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
        )
        return await q.message.edit_text(f"📝 *اختبار قصير*\n\n{item['q']}",
                                         reply_markup=kb, parse_mode="Markdown")

    if data.startswith("Q:a:"):
        parts   = data.split(":")
        qid     = int(parts[2]); choice = int(parts[3])
        quiz    = load_quiz()
        if qid >= len(quiz): return
        item     = quiz[qid]
        correct  = item["answer"]; pts = item.get("points", 1)
        is_right = choice == correct
        prof     = get_profile_points(uid)
        prof["points"] = prof.get("points", 0) + (pts if is_right else 0)
        prof["last_quiz"] = datetime.utcnow().isoformat()
        new_badges = apply_achievements(prof)
        save_profile_points(uid, prof)
        result = (f"✅ صحيحة! +{pts} نقطة" if is_right
                  else f"❌ خاطئة.\n✅ الصحيح: *{item['choices'][correct]}*")
        extra  = ("\n\n🏆 " + " | ".join(new_badges)) if new_badges else ""
        return await q.message.edit_text(
            f"📝 *اختبار قصير*\n\n{item['q']}\n\n{result}\n"
            f"⭐ نقاطك: *{prof['points']}*{extra}\n\nاضغط لسؤال جديد:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 سؤال جديد", callback_data="Q:start")],
                [InlineKeyboardButton("🏆 نقاطي",      callback_data="P:show")],
                [InlineKeyboardButton("🏠 الرئيسية",   callback_data="home")],
            ]),
            parse_mode="Markdown"
        )

    # ── النقاط ──────────────────────────────────────────────
    if data == "P:show":
        prof   = get_profile_points(uid)
        badges = prof.get("badges", [])
        b_txt  = "\n".join(f"  {b}" for b in badges) if badges else "  لا توجد إنجازات بعد"
        all_pts = sorted(load_points().values(), key=lambda x: x.get("points",0), reverse=True)
        rank    = next((i+1 for i, p in enumerate(all_pts)
                        if p.get("points",0) == prof.get("points",0)), "—")
        return await q.message.edit_text(
            f"🏆 *نقاطي وإنجازاتي*\n\n"
            f"⭐ النقاط  : *{prof.get('points',0)}*\n"
            f"🏅 الترتيب : *{rank}*\n\n"
            f"🎖️ الإنجازات:\n{b_txt}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 سؤال جديد", callback_data="Q:start")],
                [InlineKeyboardButton("🏠 الرئيسية",  callback_data="home")],
            ]),
            parse_mode="Markdown"
        )

    # ── التقويم ──────────────────────────────────────────────
    if data == "C:home":
        cal = load_cal()
        kb  = [[InlineKeyboardButton(k, callback_data=f"C:i:{k}")] for k in cal]
        kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
        return await q.message.edit_text("🗓️ *التقويم الجامعي*\nاختر القسم:",
                                         reply_markup=InlineKeyboardMarkup(kb),
                                         parse_mode="Markdown")
    if data.startswith("C:i:"):
        key = data[4:]; cal = load_cal()
        return await q.message.edit_text(
            f"🗓️ *{key}*\n\n{cal.get(key, 'لا توجد معلومات.')}",
            reply_markup=kb_back("C:home"), parse_mode="Markdown"
        )

    # ── مواقيت الصلاة ──────────────────────────────────────
    if data == "PRAY:cities":
        return await q.message.edit_text(
            "🕌 *مواقيت الصلاة*\nاختر ولايتك:",
            reply_markup=kb_wilayas(), parse_mode="Markdown"
        )

    if data.startswith("PRAY:w:"):
        city_en = data[7:]
        city_ar = next((k for k,v in WILAYAS.items() if v == city_en), city_en)
        await q.message.edit_text("⏳ جاري جلب مواقيت الصلاة...")
        timings, date_str = await fetch_prayer_times(city_en)
        if not timings:
            return await q.message.edit_text(
                "⚠️ تعذّر جلب المواقيت، حاول لاحقاً.",
                reply_markup=kb_back("PRAY:cities")
            )
        text = (
            f"🕌 *مواقيت الصلاة — {city_ar}*\n"
            f"📅 {date_str}\n\n"
            f"🌅 الفجر    : `{timings['Fajr']}`\n"
            f"🌄 الشروق   : `{timings['Sunrise']}`\n"
            f"☀️ الظهر    : `{timings['Dhuhr']}`\n"
            f"🌤️ العصر    : `{timings['Asr']}`\n"
            f"🌇 المغرب   : `{timings['Maghrib']}`\n"
            f"🌙 العشاء   : `{timings['Isha']}`"
        )
        return await q.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 ولاية أخرى", callback_data="PRAY:cities")],
                [InlineKeyboardButton("🏠 الرئيسية",   callback_data="home")],
            ]),
            parse_mode="Markdown"
        )

    # ── آية اليوم ──────────────────────────────────────────
    if data == "AY:show":
        ayah = AYAT_YAWM[datetime.now(TZ).timetuple().tm_yday % len(AYAT_YAWM)]
        text = (f"📖 *آية اليوم*\n\n"
                f"*{ayah['ref']}*\n\n"
                f"{ayah['text']}"
                + (f"\n\n_{ayah['note']}_" if ayah['note'] else ""))
        return await q.message.edit_text(text, reply_markup=kb_back("home"),
                                         parse_mode="Markdown")

    # ── دعاء اليوم ──────────────────────────────────────────
    if data == "DUA:show":
        dua = ADYIA_YAWM[datetime.now(TZ).timetuple().tm_yday % len(ADYIA_YAWM)]
        return await q.message.edit_text(
            f"🤲 *دعاء اليوم*\n\n*{dua['title']}*\n\n{dua['text']}",
            reply_markup=kb_back("home"), parse_mode="Markdown"
        )

    # ── عداد الأذكار ──────────────────────────────────────
    if data == "DHKR:show":
        ud["dhkr_s"] = 0; ud["dhkr_h"] = 0; ud["dhkr_a"] = 0
        return await q.message.edit_text(
            "📿 *عداد الأذكار*\n\nاضغط لزيادة العداد:",
            reply_markup=kb_dhikr(0, 0, 0), parse_mode="Markdown"
        )

    if data.startswith("DHKR:+:"):
        t = data[-1]
        s = ud.get("dhkr_s", 0); h = ud.get("dhkr_h", 0); a = ud.get("dhkr_a", 0)
        if t == "s" and s < 33: s += 1; ud["dhkr_s"] = s
        if t == "h" and h < 33: h += 1; ud["dhkr_h"] = h
        if t == "a" and a < 34: a += 1; ud["dhkr_a"] = a
        done = s >= 33 and h >= 33 and a >= 34
        txt = ("📿 *عداد الأذكار*\n\n✅ *اكتمل العدد!*\nبارك الله فيك 🌿"
               if done else "📿 *عداد الأذكار*\n\nاضغط لزيادة العداد:")
        try:
            return await q.message.edit_text(
                txt, reply_markup=kb_dhikr(s, h, a) if not done else
                InlineKeyboardMarkup([[InlineKeyboardButton("🔄 إعادة", callback_data="DHKR:show"),
                                        InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]),
                parse_mode="Markdown"
            )
        except: pass

    if data == "DHKR:reset":
        ud["dhkr_s"] = 0; ud["dhkr_h"] = 0; ud["dhkr_a"] = 0
        return await q.message.edit_text(
            "📿 *عداد الأذكار*\n\nاضغط لزيادة العداد:",
            reply_markup=kb_dhikr(0, 0, 0), parse_mode="Markdown"
        )

    if data == "DHKR:close":
        return await q.message.edit_text(TXT_WELCOME, reply_markup=kb_main(),
                                         parse_mode="Markdown")

    # ── القاموس ──────────────────────────────────────────
    if data == "TERM:home":
        terms = load_terms()
        if not terms:
            return await q.message.edit_text(
                "📚 *القاموس الفقهي*\n\nلم يُضف أي مصطلح بعد.",
                reply_markup=kb_back("home"), parse_mode="Markdown"
            )
        rows = []
        for i, term in enumerate(list(terms.keys())[:20]):
            rows.append([InlineKeyboardButton(term, callback_data=f"TERM:t:{i}")])
        rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
        return await q.message.edit_text(
            f"📚 *القاموس الفقهي* ({len(terms)} مصطلح)\nاختر مصطلحاً:",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown"
        )

    if data.startswith("TERM:t:"):
        idx   = int(data[7:])
        terms = load_terms()
        items = list(terms.items())
        if idx >= len(items): return
        term, defn = items[idx]
        return await q.message.edit_text(
            f"📚 *{term}*\n\n{defn}",
            reply_markup=kb_back("TERM:home"), parse_mode="Markdown"
        )

    # ── الاستطلاع ──────────────────────────────────────────
    if data.startswith("POLL:v:"):
        poll = load_poll()
        if not poll.get("active"):
            await q.answer("الاستطلاع مغلق.", show_alert=True); return
        choice = int(data[7:])
        if choice >= len(poll.get("options", [])):
            await q.answer("خيار غير صحيح.", show_alert=True); return
        poll["votes"][str(uid)] = choice
        save_poll(poll)
        opt = poll["options"][choice]
        await q.answer(f"✅ تم تسجيل صوتك: {opt}", show_alert=True)
        # إظهار نتائج مؤقتة
        votes = poll["votes"]; total = len(votes)
        options = poll["options"]
        counts = [sum(1 for v in votes.values() if v == i) for i in range(len(options))]
        lines = [f"🗳️ *{poll['question']}*\n\nنتائج مؤقتة:\n"]
        for i, opt in enumerate(options):
            pct = round(counts[i]/total*100) if total else 0
            lines.append(f"{i+1}. {opt}: {counts[i]} ({pct}%)")
        try:
            await q.message.edit_text(
                "\n".join(lines),
                reply_markup=kb_poll_vote(options),
                parse_mode="Markdown"
            )
        except: pass
        return

    # ── الإعجاب ──────────────────────────────────────────
    if data.startswith("LIKE:"):
        key    = data[5:]
        added, count = toggle_like(key, uid)
        liked  = added
        icon   = "❤️" if liked else "🤍"
        msg_txt = "✅ أُضيف إلى إعجاباتك!" if liked else "💔 أُزيل من إعجاباتك"
        await q.answer(msg_txt)
        try:
            await q.message.edit_reply_markup(
                reply_markup=kb_like(key, count, liked)
            )
        except: pass
        return

    # ── الملاحظات ──────────────────────────────────────────
    if data == "NOTE:list":
        notes = get_user_notes(uid)
        if not notes:
            return await q.message.edit_text(
                "📝 *ملاحظاتي*\n\nلا توجد ملاحظات بعد.\nاضغط ➕ لإضافة ملاحظة.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ إضافة ملاحظة", callback_data="NOTE:add")],
                    [InlineKeyboardButton("🏠 الرئيسية",      callback_data="home")],
                ]),
                parse_mode="Markdown"
            )
        rows = []
        for i, note in enumerate(notes):
            label = note["text"][:30] + ("..." if len(note["text"]) > 30 else "")
            rows.append([
                InlineKeyboardButton(f"📄 {label}", callback_data=f"NOTE:view:{i}"),
                InlineKeyboardButton("🗑️", callback_data=f"NOTE:del:{i}"),
            ])
        rows += [
            [InlineKeyboardButton("➕ إضافة ملاحظة", callback_data="NOTE:add")],
            [InlineKeyboardButton("🏠 الرئيسية",      callback_data="home")],
        ]
        return await q.message.edit_text(
            f"📝 *ملاحظاتي* ({len(notes)})\nاختر ملاحظة:",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown"
        )

    if data.startswith("NOTE:view:"):
        idx = int(data[10:])
        notes = get_user_notes(uid)
        if idx >= len(notes): return
        note = notes[idx]
        return await q.message.edit_text(
            f"📝 *ملاحظة #{idx+1}*\n📅 {note['date']}\n\n{note['text']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ حذف", callback_data=f"NOTE:del:{idx}")],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="NOTE:list")],
            ]),
            parse_mode="Markdown"
        )

    if data.startswith("NOTE:del:"):
        idx = int(data[9:])
        delete_note(uid, idx)
        await q.answer("✅ حُذفت الملاحظة.")
        notes = get_user_notes(uid)
        if not notes:
            return await q.message.edit_text(
                "📝 *ملاحظاتي*\n\nلا توجد ملاحظات.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ إضافة ملاحظة", callback_data="NOTE:add")],
                    [InlineKeyboardButton("🏠 الرئيسية",      callback_data="home")],
                ]),
                parse_mode="Markdown"
            )
        rows = []
        for i, note in enumerate(notes):
            label = note["text"][:30] + ("..." if len(note["text"]) > 30 else "")
            rows.append([
                InlineKeyboardButton(f"📄 {label}", callback_data=f"NOTE:view:{i}"),
                InlineKeyboardButton("🗑️", callback_data=f"NOTE:del:{i}"),
            ])
        rows += [[InlineKeyboardButton("➕ إضافة ملاحظة", callback_data="NOTE:add")],
                 [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
        return await q.message.edit_text(
            f"📝 *ملاحظاتي* ({len(notes)})\nاختر ملاحظة:",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown"
        )

    if data == "NOTE:add":
        ud["awaiting"] = "note_add"
        return await q.message.edit_text(
            "📝 *إضافة ملاحظة*\n\n✍️ اكتب ملاحظتك الآن:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="NOTE:list")]
            ]),
            parse_mode="Markdown"
        )

    # ── الملف الشخصي ──────────────────────────────────────
    if data == "PROF:show":
        prof = get_student_profile(uid)
        name = prof.get("name", "غير محدد")
        spec = prof.get("spec", "غير محدد")
        year = prof.get("year", "غير محددة")
        return await q.message.edit_text(
            f"👤 *ملفي الشخصي*\n\n"
            f"📛 الاسم     : *{name}*\n"
            f"🎓 التخصص   : *{spec}*\n"
            f"📅 السنة     : *{year}*",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ تعديل الاسم",   callback_data="PROF:name")],
                [InlineKeyboardButton("🎓 التخصص",        callback_data="PROF:spec")],
                [InlineKeyboardButton("📅 السنة",          callback_data="PROF:year")],
                [InlineKeyboardButton("🏠 الرئيسية",       callback_data="home")],
            ]),
            parse_mode="Markdown"
        )

    if data == "PROF:name":
        ud["awaiting"] = "profile_name"
        return await q.message.edit_text(
            "✏️ *تعديل الاسم*\n\nاكتب اسمك:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="PROF:show")]
            ]),
            parse_mode="Markdown"
        )

    if data == "PROF:spec":
        lessons = load_lessons()
        specs   = set()
        for yr in lessons.values():
            for sp in yr: specs.add(sp)
        custom_specs = ["شعبة أصول الفقه", "شعبة أصول الدين", "بدون تخصص"]
        all_specs = list(specs) or custom_specs
        rows = [[InlineKeyboardButton(s, callback_data=f"PROF:setspec:{s}")]
                for s in all_specs[:10]]
        rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="PROF:show")])
        return await q.message.edit_text(
            "🎓 *اختر تخصصك:*",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown"
        )

    if data.startswith("PROF:setspec:"):
        spec = data[13:]
        prof = get_student_profile(uid)
        prof["spec"] = spec
        save_student_profile(uid, prof)
        await q.answer("✅ تم تحديث التخصص")
        return await handle_cb(update, context)  # won't work, need to re-call

    if data == "PROF:year":
        rows = [[InlineKeyboardButton(y, callback_data=f"PROF:setyear:{y}")]
                for y in ["سنة أولى", "سنة ثانية", "سنة ثالثة"]]
        rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="PROF:show")])
        return await q.message.edit_text(
            "📅 *اختر سنتك الدراسية:*",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown"
        )

    if data.startswith("PROF:setyear:"):
        year = data[13:]
        prof = get_student_profile(uid)
        prof["year"] = year
        save_student_profile(uid, prof)
        await q.answer("✅ تم تحديث السنة")
        prof_disp = get_student_profile(uid)
        return await q.message.edit_text(
            f"👤 *ملفي الشخصي*\n\n"
            f"📛 الاسم   : *{prof_disp.get('name','غير محدد')}*\n"
            f"🎓 التخصص : *{prof_disp.get('spec','غير محدد')}*\n"
            f"📅 السنة   : *{prof_disp.get('year','غير محددة')}*",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ تعديل الاسم", callback_data="PROF:name")],
                [InlineKeyboardButton("🎓 التخصص",      callback_data="PROF:spec")],
                [InlineKeyboardButton("📅 السنة",        callback_data="PROF:year")],
                [InlineKeyboardButton("🏠 الرئيسية",     callback_data="home")],
            ]),
            parse_mode="Markdown"
        )

    if data.startswith("PROF:setspec:"):
        spec = data[13:]
        prof = get_student_profile(uid)
        prof["spec"] = spec
        save_student_profile(uid, prof)
        await q.answer("✅ تم تحديث التخصص")
        prof_disp = get_student_profile(uid)
        return await q.message.edit_text(
            f"👤 *ملفي الشخصي*\n\n"
            f"📛 الاسم   : *{prof_disp.get('name','غير محدد')}*\n"
            f"🎓 التخصص : *{spec}*\n"
            f"📅 السنة   : *{prof_disp.get('year','غير محددة')}*",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ تعديل الاسم", callback_data="PROF:name")],
                [InlineKeyboardButton("🎓 التخصص",      callback_data="PROF:spec")],
                [InlineKeyboardButton("📅 السنة",        callback_data="PROF:year")],
                [InlineKeyboardButton("🏠 الرئيسية",     callback_data="home")],
            ]),
            parse_mode="Markdown"
        )

    # ── المساعد الذكي ─────────────────────────────────────────
    if data == "AI:show":
        ud["awaiting"] = "ai_question"
        return await q.message.edit_text(
            "🤖 *المساعد الذكي*\n\n"
            "مرحباً! أنا مساعدك العلمي المتخصص في الدراسات الإسلامية.\n\n"
            "يمكنني مساعدتك في:\n"
            "📖 الفقه وأصول الفقه\n"
            "📜 الحديث النبوي وعلومه\n"
            "🌟 التفسير والقرآن الكريم\n"
            "🕌 العقيدة الإسلامية\n"
            "📚 التاريخ الإسلامي\n"
            "🔤 شرح المصطلحات الصعبة\n\n"
            "✍️ *اكتب سؤالك الآن:*",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="home")]
            ]),
            parse_mode="Markdown"
        )

    # ── اقتراح درس ──────────────────────────────────────────
    if data == "SUG:start":
        ud["awaiting"] = "suggest"
        return await q.message.edit_text(
            "💬 *اقتراح درس*\n\n"
            "✍️ اكتب اسم المادة والسداسي والسنة وأي تفاصيل مفيدة:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="home")]
            ]),
            parse_mode="Markdown"
        )

    # ── تنقل الدروس ──────────────────────────────────────────
    lessons = load_lessons()

    if data == "D:years":
        ud.clear()
        return await q.message.edit_text("📘 اختر السنة الدراسية:",
                                         reply_markup=kb_years(lessons))

    if data.startswith("D:y:"):
        idx = int(data[4:]); keys = list(lessons.keys())
        if idx >= len(keys): return
        ud["year"] = keys[idx]
        return await q.message.edit_text(
            f"📙 *{ud['year']}*\nاختر التخصص:",
            reply_markup=kb_specs(lessons, ud["year"]), parse_mode="Markdown"
        )

    if data == "D:specs":
        for k in ("spec","sem","subj","items"): ud.pop(k, None)
        return await q.message.edit_text(
            f"📙 *{ud.get('year','')}*\nاختر التخصص:",
            reply_markup=kb_specs(lessons, ud.get("year","")), parse_mode="Markdown"
        )

    if data.startswith("D:s:"):
        idx = int(data[4:]); year = ud.get("year")
        if not year: return
        keys = list(lessons[year].keys())
        if idx >= len(keys): return
        ud["spec"] = keys[idx]
        return await q.message.edit_text(
            f"📗 *{ud['year']}  ·  {ud['spec']}*\nاختر السداسي:",
            reply_markup=kb_sems(lessons, year, ud["spec"]), parse_mode="Markdown"
        )

    if data == "D:sems":
        for k in ("sem","subj","items"): ud.pop(k, None)
        return await q.message.edit_text(
            f"📗 *{ud.get('year','')}  ·  {ud.get('spec','')}*\nاختر السداسي:",
            reply_markup=kb_sems(lessons, ud.get("year",""), ud.get("spec","")),
            parse_mode="Markdown"
        )

    if data.startswith("D:sm:"):
        idx = int(data[5:]); year = ud.get("year"); spec = ud.get("spec")
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
        idx = int(data[5:]); year = ud.get("year")
        spec = ud.get("spec"); sem = ud.get("sem")
        if not (year and spec and sem): return
        keys = list(lessons[year][spec][sem].keys())
        if idx >= len(keys): return
        subj  = keys[idx]
        items = lessons[year][spec][sem][subj]
        ud["subj"] = subj; ud["items"] = items; ud["cat_filter"] = "all"
        if not items:
            return await q.message.edit_text(
                f"📭 لا توجد دروس بعد في مادة *{subj}*",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 اقتراح إضافة هذا الدرس", callback_data="SUG:start")],
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="D:subjects")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ]),
                parse_mode="Markdown"
            )
        return await q.message.edit_text(
            f"📖 *{subj}*\nاختر الدرس:",
            reply_markup=kb_files(items, year, spec, sem, subj, "all"),
            parse_mode="Markdown"
        )

    if data.startswith("D:cat:"):
        cat_f = data[6:]; year = ud.get("year")
        spec = ud.get("spec"); sem = ud.get("sem"); subj = ud.get("subj")
        items = ud.get("items", [])
        if not items: return
        ud["cat_filter"] = cat_f
        return await q.message.edit_text(
            f"📖 *{subj}*\nاختر الدرس:",
            reply_markup=kb_files(items, year, spec, sem, subj, cat_f),
            parse_mode="Markdown"
        )

    if data.startswith("D:f:"):
        i     = int(data[4:]); items = ud.get("items", [])
        year  = ud.get("year"); spec = ud.get("spec")
        sem   = ud.get("sem"); subj = ud.get("subj")
        if not items or not (0 <= i < len(items)): return
        item  = items[i]
        title, fid = item[0], item[1]
        lkey  = lesson_key(year or "", spec or "", sem or "", subj or "", i)
        count = get_like_count(lkey)
        liked = user_liked(lkey, uid)
        if is_url(fid):
            await q.message.reply_text(f"🔗 {fid}")
        else:
            try:
                await q.message.reply_document(document=fid, caption=f"📄 {title}")
            except BadRequest:
                await q.message.reply_text("⚠️ الملف غير متاح (file_id منتهي).")
                return
            except Exception:
                await q.message.reply_text("⚠️ حدث خطأ أثناء الإرسال.")
                return
        # إرسال زر الإعجاب
        await q.message.reply_text(
            f"هل أفادك هذا الدرس؟",
            reply_markup=kb_like(lkey, count, liked)
        )


# ================================================================
#  ٢٧. رسائل الخاص
# ================================================================

async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    msg  = update.message
    user = update.effective_user
    ud   = context.user_data

    # ── معالجة حالات الانتظار ──
    awaiting = ud.pop("awaiting", None)
    if awaiting and msg and msg.text:
        text = msg.text.strip()

        if awaiting == "note_add":
            add_note(user.id, text)
            await msg.reply_text(
                "✅ تمت إضافة الملاحظة!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 ملاحظاتي", callback_data="NOTE:list")],
                    [InlineKeyboardButton("🏠 الرئيسية",  callback_data="home")],
                ])
            )
            return

        if awaiting == "profile_name":
            prof = get_student_profile(user.id)
            prof["name"] = text
            save_student_profile(user.id, prof)
            await msg.reply_text(
                f"✅ تم حفظ الاسم: *{text}*",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👤 ملفي", callback_data="PROF:show")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ]),
                parse_mode="Markdown"
            )
            return

        if awaiting == "suggest":
            try:
                await context.bot.send_message(
                    ADMIN_CHAT_ID,
                    f"💬 *اقتراح درس جديد*\n\n"
                    f"👤 {user.full_name}\n"
                    f"🆔 `{user.id}`\n\n"
                    f"📝 {text}",
                    parse_mode="Markdown"
                )
                await msg.reply_text("✅ تم إرسال اقتراحك للمشرفين، شكراً! 🌿")
            except Exception:
                await msg.reply_text("⚠️ حدث خطأ، حاول مجدداً.")
            return

        if awaiting == "ai_question":
            # إظهار مؤشر الكتابة
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            await msg.reply_text("⏳ جاري التفكير في إجابتك...")
            answer = await ask_ai(text)
            await msg.reply_text(
                f"🤖 *المساعد الذكي*\n\n{answer}\n\n"
                "─────────────────\n"
                "⚠️ _هذه إجابة استرشادية. للفتوى الشرعية الشخصية يُرجع للعلماء._",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 سؤال جديد",   callback_data="AI:show")],
                    [InlineKeyboardButton("🏠 الرئيسية",    callback_data="home")],
                ]),
                parse_mode="Markdown"
            )
            return

    # ── المشرف: file_id تلقائي ──
    if user.id in ADMIN_IDS:
        if msg and msg.document:
            fid = msg.document.file_id
            await msg.reply_text(
                f"📎 *file\_id:*\n`{fid}`\n\n"
                "Reply على الملف ثم:\n"
                "`/adddars سنة | تخصص | سداسي | مادة | عنوان`\n\n"
                "/adminhelp للأوامر الكاملة",
                parse_mode="Markdown"
            )
        return

    # ── الطالب: توجيه للمشرفين ──
    add_user(update.effective_chat.id)
    try:
        meta = await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"📩 *سؤال جديد*\n\n"
            f"👤 {user.full_name}\n"
            f"🆔 `{user.id}`\n\n"
            "↩️ Reply للرد على الطالب",
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
        print(f"⚠️ {e}")
        await msg.reply_text("⚠️ حدث خطأ، حاول مجدداً.")


# ================================================================
#  ٢٨. ردود المشرفين
# ================================================================

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID: return
    msg = update.message
    if not msg or not msg.reply_to_message: return
    m   = load_map()
    sid = m.get(str(msg.reply_to_message.message_id))
    if not sid: return
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
        print(f"⚠️ reply error: {e}")


# ================================================================
#  ٢٩. بناء التطبيق
# ================================================================

def build_app() -> Application:
    token = _clean(os.environ.get("BOT_TOKEN", ""))
    if not token:
        raise RuntimeError("❌ BOT_TOKEN غير موجود.")

    app = Application.builder().token(token).post_init(on_startup).build()

    # أوامر عامة
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ping",      cmd_ping))
    app.add_handler(CommandHandler("adminhelp", cmd_adminhelp))

    # الدروس
    app.add_handler(CommandHandler("adddars",  cmd_adddars))
    app.add_handler(CommandHandler("listdars", cmd_listdars))
    app.add_handler(CommandHandler("deldars",  cmd_deldars))

    # الكويز
    app.add_handler(CommandHandler("addquiz",  cmd_addquiz))
    app.add_handler(CommandHandler("listquiz", cmd_listquiz))
    app.add_handler(CommandHandler("delquiz",  cmd_delquiz))

    # الاستطلاع
    app.add_handler(CommandHandler("poll",        cmd_poll,        filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("pollresults", cmd_pollresults, filters=filters.Chat(ADMIN_CHAT_ID)))
    app.add_handler(CommandHandler("endpoll",     cmd_endpoll,     filters=filters.Chat(ADMIN_CHAT_ID)))

    # القاموس
    app.add_handler(CommandHandler("addterm",  cmd_addterm))
    app.add_handler(CommandHandler("delterm",  cmd_delterm))
    app.add_handler(CommandHandler("listterms",cmd_listterms))

    # المجموعة فقط
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
