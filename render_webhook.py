# =============================================================
#  render_webhook.py  —  سيرفر Webhook لـ Render
# =============================================================

import os
import asyncio
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
import uvicorn

from telegram import Update
from bot import build_app


def _clean(s: str) -> str:
    return "".join(str(s).strip().split()) if s else ""


def get_webhook_url() -> str:
    """يستخرج الـ URL العام من متغيرات بيئة Render"""
    manual   = _clean(os.environ.get("PUBLIC_BASE_URL", ""))
    ext_url  = _clean(os.environ.get("RENDER_EXTERNAL_URL", ""))
    hostname = _clean(os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""))

    base = manual or ext_url or (f"https://{hostname}" if hostname else "")
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


PORT    = int(os.environ.get("PORT", "10000"))
ptb_app = build_app()


# ── مسارات Starlette ──
async def telegram_webhook(request):
    data   = await request.json()
    update = Update.de_json(data=data, bot=ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return Response(status_code=200)


async def health_check(_):
    return PlainTextResponse("OK ✅")


starlette_app = Starlette(routes=[
    Route("/telegram", telegram_webhook, methods=["POST"]),
    Route("/health",   health_check,     methods=["GET"]),
])


async def main():
    await ptb_app.initialize()
    await ptb_app.start()

    webhook_url = get_webhook_url()
    if not webhook_url:
        raise RuntimeError(
            "تعذّر تحديد الـ URL العام.\n"
            "تأكد من وجود RENDER_EXTERNAL_HOSTNAME في متغيرات بيئة Render،\n"
            "أو أضف PUBLIC_BASE_URL يدوياً."
        )

    full_webhook = f"{webhook_url}/telegram"
    print(f"🌐 Webhook URL : {full_webhook}")

    try:
        await ptb_app.bot.set_webhook(
            url=full_webhook,
            allowed_updates=Update.ALL_TYPES
        )
        print("✅ Webhook set successfully")
    except Exception as e:
        print(f"⚠️  set_webhook failed: {e}")

    config = uvicorn.Config(
        app=starlette_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        use_colors=False
    )
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    asyncio.run(main())
