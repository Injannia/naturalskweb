import logging
import os
from logging.handlers import RotatingFileHandler

from pythonjsonlogger import jsonlogger

from app.core.config import settings

_LOG_FILE = "naturalsk.log"


def setup_logging() -> None:
    """Configure root logging: JSON file (rotating, WARNING+) + stdout (INFO+).

    Idempotent — safe to call multiple times (clears existing handlers first).
    """
    os.makedirs(settings.LOGS_DIR, exist_ok=True)
    log_path = os.path.join(settings.LOGS_DIR, _LOG_FILE)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)

    json_fmt = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(json_fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(json_fmt)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)
