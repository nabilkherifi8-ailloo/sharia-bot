import os
import asyncio
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
import uvicorn

from telegram import Update
from bot import build_app


def _clean(s: str) -> str:
    """إزالة كل whitespace بما فيه \n \r \t والمسافات."""
    if not s:
        return ""
    return "".join(str(s).strip().split())


def get_public_base_url() -> str:
    # Render يوفر غالبًا hostname نظيف:
    host = _clean(os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""))
    url = _clean(os.environ.get("RENDER_EXTERNAL_URL", ""))
    manual = _clean(os.environ.get("PUBLIC_BASE_URL", ""))  # اختياري لو احتجناه

    base = manual or url or (f"https://{host}" if host else "")
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


PORT = int(os.environ.get("PORT", "10000"))
ptb_app = build_app()  # build_app الآن ينظف التوكن بنفسه


async def telegram(request):
    data = await request.json()
    update = Update.de_json(data=data, bot=ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return Response(status_code=200)


async def health(_):
    return PlainTextResponse("OK")


starlette_app = Starlette(routes=[
    Route("/telegram", telegram, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
])


async def main():
    await ptb_app.initialize()
    await ptb_app.start()

    base_url = get_public_base_url()
    if not base_url:
        raise RuntimeError(
            "Public URL not found. On Render Web Services, RENDER_EXTERNAL_HOSTNAME should exist. "
            "If it doesn't, set PUBLIC_BASE_URL manually (e.g., https://your-service.onrender.com)."
        )

    webhook_url = f"{base_url}/telegram"
    print("PUBLIC_BASE_URL =", repr(base_url))
    print("WEBHOOK_URL     =", repr(webhook_url))

    # حتى لو فشل set_webhook لا نجعل السيرفر ينهار
    try:
        await ptb_app.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print("WARNING: set_webhook failed:", repr(e))

    config = uvicorn.Config(app=starlette_app, host="0.0.0.0", port=PORT, log_level="info", use_colors=False)
    server = uvicorn.Server(config=config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
