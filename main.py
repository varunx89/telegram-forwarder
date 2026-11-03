import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from config import settings
from telegram_client import service
from web_app import app

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("telegram_forwarder.main")

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    logger.info("Starting Telegram Forwarder Service...")
    logger.info(f"Target Group to monitor: '{settings.TARGET_GROUP_NAME}'")
    logger.info(f"Destination Telegram recipient: '{settings.FORWARD_TO_USERNAME}'")
    
    # Initialize Telethon client asynchronously
    try:
        await service.initialize()
    except Exception as e:
        logger.error(f"Error initializing Telethon client: {e}")
        
    yield
    
    logger.info("Shutting down Telegram Forwarder Service...")
    await service.shutdown()

# Attach lifespan to FastAPI
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    logger.info(f"Listening on http://{settings.HOST}:{settings.PORT}")
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False
    )
