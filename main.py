import logging
import sys

import uvicorn

from config import settings
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

if __name__ == "__main__":
    host_display = f"[{settings.HOST}]" if ":" in settings.HOST else settings.HOST
    logger.info(f"Listening on http://{host_display}:{settings.PORT} (host={settings.HOST}, ipv6={settings.use_ipv6})")
    uvicorn.run(
        "web_app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False
    )
