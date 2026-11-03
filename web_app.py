from fastapi import FastAPI
from config import settings
from telegram_client import service

# Pure headless web responder for Render free-tier health checks
app = FastAPI(
    title="Telegram Forwarder",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "running": service.is_running,
        "connected": service.is_connected
    }

@app.get("/")
async def root():
    return {"service": "telegram-forwarder", "status": "active"}
