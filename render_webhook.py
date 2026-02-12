import os
import asyncio
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
import uvicorn

from telegram import Update
from bot import build_app

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Render Environment Variables.")
if not RENDER_EXTERNAL_URL:
    raise RuntimeError("RENDER_EXTERNAL_URL is missing (Render sets it automatically for Web Services).")

ptb_app = build_app()

async def telegram(request):
    data = await request.json()
    update = Update.de_json(data=data, bot=ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return Response()

async def health(_):
    return PlainTextResponse("OK")

starlette_app = Starlette(routes=[
    Route("/telegram", telegram, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
])

async def main():
    await ptb_app.initialize()
    await ptb_app.start()

    webhook_url = f"{RENDER_EXTERNAL_URL}/telegram"
    await ptb_app.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)

    config = uvicorn.Config(app=starlette_app, host="0.0.0.0", port=PORT, use_colors=False)
    server = uvicorn.Server(config=config)
    await server.serve()

    await ptb_app.stop()
    await ptb_app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
