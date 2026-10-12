import logging
import os

DEV_MODE = os.getenv("SHIFU_DEV_MODE", "false").lower() in ("true", "1", "yes")

_dev_logger = logging.getLogger("app.agents.agente_v3.devbox")
_dev_logger.propagate = False   # Don't bubble up to root's StreamHandler (would double-print)


def _attach_file_handler() -> None:
    """Lazily attach the app's FileHandler to _dev_logger so boxes appear in app.log."""
    if _dev_logger.handlers:
        return
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.FileHandler):
            _dev_logger.addHandler(h)
            break


def dev_print(msg: str) -> None:
    """Write a dev box to console (real-time) and app.log (via FileHandler)."""
    print(msg, flush=True)          # stdout — immediate, no buffering
    _attach_file_handler()          # wire file handler once on first call
    _dev_logger.info(msg)           # file only — propagation disabled


