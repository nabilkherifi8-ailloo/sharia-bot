import os
import asyncio
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
import uvicorn

from telegram import Update
from bot import build_app

# ====== قراءة المتغيرات وتطهيرها ======
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Render Environment Variables.")

# نستخدم strip() للتأكد من عدم وجود أحرف غير مطبوعة

ptb_app = build_app()

async def telegram(request):
    data = await request.json()
    update = Update.de_json(data=data, bot=ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return Response()

async def health(_):
    return PlainTextResponse("OK")

routes = [
    Route("/telegram", telegram, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
]

starlette_app = Starlette(routes=routes)

async def main():
    # ====== تهيئة البوت ======
    await ptb_app.initialize()
    await ptb_app.start()

    # ========== ضبط Webhook ==========
    # نستخدم الرابط بدون أي سطر جديد
    webhook_url = f"{RENDER_EXTERNAL_URL}/telegram"
    webhook_url = webhook_url.strip()

    await ptb_app.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES
    )

    # ====== تشغيل الخادم ======
    config = uvicorn.Config(
        app=starlette_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        use_colors=False
    )
    server = uvicorn.Server(config=config)
    await server.serve()

    # ======= إغلاق التطبيق بشكل نظيف ======
    await ptb_app.stop()
    await ptb_app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
