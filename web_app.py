import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, status

from config import settings
from telegram_client import service

logger = logging.getLogger("telegram_forwarder.web")

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    logger.info("Starting Telegram Forwarder Service...")
    logger.info(f"Target Group to monitor: '{settings.TARGET_GROUP_NAME}'")
    logger.info(f"Destination Telegram recipient: '{settings.FORWARD_TO_USERNAME}'")
    try:
        await service.initialize()
    except Exception as e:
        logger.error(f"Error during Telegram client initialization: {e}")
    yield
    logger.info("Shutting down Telegram Forwarder Service...")
    await service.shutdown()

app = FastAPI(
    title="Telegram Forwarder",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan
)

@app.get("/health")
async def health(response: Response):
    info = service.get_status()
    if not service.is_healthy():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return info

@app.get("/live")
async def live():
    return {"status": "alive"}

@app.get("/")
async def root():
    return {"service": "telegram-forwarder", "status": "active"}
