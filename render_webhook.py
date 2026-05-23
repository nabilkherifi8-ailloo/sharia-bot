# ================================================================
#  render_webhook.py — سيرفر Webhook لـ Render
# ================================================================

import os
import asyncio
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
import uvicorn

from telegram import Update
from bot import build_app

PORT = int(os.environ.get("PORT", "10000"))


def get_public_url():
    def clean(s):
        return "".join(str(s).strip().split()) if s else ""
    manual   = clean(os.environ.get("PUBLIC_BASE_URL", ""))
    ext_url  = clean(os.environ.get("RENDER_EXTERNAL_URL", ""))
    hostname = clean(os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""))
    base = manual or ext_url or (f"https://{hostname}" if hostname else "")
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


ptb_app = build_app()


async def webhook_handler(request):
    try:
        data   = await request.json()
        update = Update.de_json(data=data, bot=ptb_app.bot)
        await ptb_app.update_queue.put(update)
    except Exception as e:
        print(f"⚠️ webhook error: {e}")
    return Response(status_code=200)


async def health_handler(_):
    return PlainTextResponse("OK ✅")


web_app = Starlette(routes=[
    Route("/telegram", webhook_handler, methods=["POST"]),
    Route("/health",   health_handler,  methods=["GET"]),
])


async def main():
    await ptb_app.initialize()
    await ptb_app.start()

    base = get_public_url()
    if not base:
        raise RuntimeError(
            "❌ تعذّر تحديد الـ URL.\n"
            "تأكد من RENDER_EXTERNAL_HOSTNAME أو أضف PUBLIC_BASE_URL."
        )

    wh = f"{base}/telegram"
    print(f"🌐 Webhook: {wh}")

    try:
        await ptb_app.bot.set_webhook(url=wh, allowed_updates=Update.ALL_TYPES)
        print("✅ Webhook registered")
    except Exception as e:
        print(f"⚠️ set_webhook failed: {e}")

    config = uvicorn.Config(
        app=web_app, host="0.0.0.0", port=PORT,
        log_level="info", use_colors=False
    )
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    asyncio.run(main())

