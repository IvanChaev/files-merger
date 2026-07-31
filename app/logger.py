import logging
import os
import sys
import tempfile
from datetime import datetime


BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE, "logs")


def _cleanup_old_logs(keep=10):
    try:
        logs = sorted(
            [os.path.join(LOGS_DIR, f) for f in os.listdir(LOGS_DIR) if f.endswith(".log")],
            key=os.path.getmtime
        )
        for old in logs[:-keep]:
            try:
                os.remove(old)
            except OSError:
                pass
    except OSError:
        pass


def setup_logging():
    global LOGS_DIR
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
    except OSError:
        LOGS_DIR = tempfile.gettempdir()
        os.makedirs(LOGS_DIR, exist_ok=True)

    _cleanup_old_logs()

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = os.path.join(LOGS_DIR, f"{ts}.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(fmt)
    handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)

    logging.getLogger(__name__).info("Session log: %s", log_path)

    sys.excepthook = _log_unhandled


def _log_unhandled(exc_type, exc_value, exc_traceback):
    logging.getLogger("UNHANDLED").critical(
        "Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback)
    )


def get_logger(name):
    return logging.getLogger(name)
