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
