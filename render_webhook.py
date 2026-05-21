# ================================================================
#  render_webhook.py — سيرفر Webhook لـ Render
#  يستقبل تحديثات تيليغرام ويمررها لـ python-telegram-bot
# ================================================================

import os
import asyncio
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
import uvicorn

from telegram import Update
from bot import build_app


# ════════════════════════════════════════════════════════════════
#  إعدادات السيرفر
# ════════════════════════════════════════════════════════════════

PORT = int(os.environ.get("PORT", "10000"))


def get_public_url() -> str:
    """
    استخراج الـ URL العام بالأولوية:
    1. PUBLIC_BASE_URL   (يدوي)
    2. RENDER_EXTERNAL_URL
    3. RENDER_EXTERNAL_HOSTNAME
    """
    def clean(s):
        return "".join(str(s).strip().split()) if s else ""

    manual   = clean(os.environ.get("PUBLIC_BASE_URL", ""))
    ext_url  = clean(os.environ.get("RENDER_EXTERNAL_URL", ""))
    hostname = clean(os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""))

    base = manual or ext_url or (f"https://{hostname}" if hostname else "")
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


# ════════════════════════════════════════════════════════════════
#  إنشاء البوت والسيرفر
# ════════════════════════════════════════════════════════════════

ptb_app = build_app()


async def webhook_handler(request):
    """استقبال تحديثات تيليغرام"""
    try:
        data   = await request.json()
        update = Update.de_json(data=data, bot=ptb_app.bot)
        await ptb_app.update_queue.put(update)
    except Exception as e:
        print(f"⚠️ خطأ في معالجة التحديث: {e}")
    return Response(status_code=200)


async def health_handler(_):
    """نقطة فحص صحة السيرفر"""
    return PlainTextResponse("OK ✅")


# تطبيق Starlette
web_app = Starlette(routes=[
    Route("/telegram", webhook_handler, methods=["POST"]),
    Route("/health",   health_handler,  methods=["GET"]),
])


# ════════════════════════════════════════════════════════════════
#  نقطة الدخول الرئيسية
# ════════════════════════════════════════════════════════════════

async def main():
    # تهيئة البوت
    await ptb_app.initialize()
    await ptb_app.start()

    # التحقق من الـ URL
    base_url = get_public_url()
    if not base_url:
        raise RuntimeError(
            "❌ تعذّر تحديد الـ URL العام!\n"
            "تأكد من وجود RENDER_EXTERNAL_HOSTNAME في متغيرات Render،\n"
            "أو أضف PUBLIC_BASE_URL يدوياً."
        )

    webhook_url = f"{base_url}/telegram"
    print(f"🌐 Webhook URL : {webhook_url}")

    # تسجيل الـ Webhook
    try:
        await ptb_app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES
        )
        print("✅ تم تسجيل Webhook بنجاح")
    except Exception as e:
        print(f"⚠️ فشل تسجيل Webhook: {e}")

    # تشغيل السيرفر
    config = uvicorn.Config(
        app=web_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        use_colors=False
    )
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    asyncio.run(main())

