"""
Logging Config

sets up both file and console logging

- logs to both file (logs/system.log) and console (stdout)
- uses INFO level by default
- consistent timestamp and log level formatting
- utf-8 encoding for log files

format:
    timestamp level_name logger_name | message




"""
import logging
import sys
from pathlib import Path

# create logs directory if it doesn't exist
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# config logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "system.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)