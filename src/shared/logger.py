import os
from loguru import logger
from datetime import datetime
import sys
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

today=datetime.today().strftime("%d-%m-%Y_%H-%M")
BASE_DIR  = Path(__file__).resolve().parent.parent.parent
LOG_DIR   = (BASE_DIR / 'logs').resolve()
LOG_PATH  = LOG_DIR / f'Log_{today}.log'
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()

fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function} | {message} | {extra}"

# Console
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    format=fmt,
    enqueue=True,
)

# Arquivo (rotaciona por dia)
logger.add(
    str(LOG_DIR / "kmm_{time:YYYY-MM-DD}.log"),
    level=LOG_LEVEL,
    rotation="00:00",
    retention="2 days",
    compression="zip",
    enqueue=True,
    format=fmt,
)
