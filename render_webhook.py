import os
import asyncio
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
import uvicorn

from telegram import Update
from bot import build_app

# قراءة المتغيرات من بيئة Render
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

# التأكد أن BOT_TOKEN موجود
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Render Environment Variables.")

# بناء تطبيق البوت
ptb_app = build_app()

# نقطة استقبال Webhook
async def telegram(request):
    data = await request.json()
    update = Update.de_json(data=data, bot=ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return Response()

# صفحة صحية بسيطة
async def health(_):
    return PlainTextResponse("OK")

# تعريف المسارات
routes = [
    Route("/telegram", telegram, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
]

starlette_app = Starlette(routes=routes)

async def main():
    # تهيئة البوت
    await ptb_app.initialize()
    await ptb_app.start()

    # بناء رابط Webhook نظيف بدون سطر جديد
    webhook_url = f"{RENDER_EXTERNAL_URL}/telegram".strip()

    # تثبيت Webhook
    await ptb_app.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES
    )

    # تشغيل خادم Uvicorn
    config = uvicorn.Config(
        app=starlette_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        use_colors=False
    )
    server = uvicorn.Server(config=config)
    await server.serve()

    # إيقاف التطبيق بشكل نظيف
    await ptb_app.stop()
    await ptb_app.shutdown()

# نقطة بداية التنفيذ
if __name__ == "__main__":
    asyncio.run(main())
