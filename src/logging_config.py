"""
Journalisation de bout en bout avec Loguru.

Tous les logs — API, graphe multi-agent, outils, mais aussi les librairies
tierces qui utilisent le module `logging` standard (uvicorn, httpx,
sentence_transformers...) — passent par les mêmes sinks Loguru, pour que
l'équipe DevOps n'ait plus jamais à recouper deux formats de logs différents.
"""
import logging
import sys
from pathlib import Path

from loguru import logger

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


class _InterceptHandler(logging.Handler):
    """Redirige tout appel à logging.* (stdlib) vers Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level: str = "INFO") -> None:
    """
    À appeler une seule fois, au tout début du point d'entrée process (src/main.py).
    Remplace le handler par défaut de `logging` par l'intercepteur Loguru, et
    configure deux sinks Loguru : console (coloré) + fichier rotatif.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for noisy_logger in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx"):
        log = logging.getLogger(noisy_logger)
        log.handlers = [_InterceptHandler()]
        log.propagate = False  # sinon le root logger (déjà interceptor) rejoue le même record

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
        ),
        colorize=True,
    )
    logger.add(
        LOG_DIR / "horragor.log",
        level=level,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} — {message}",
        enqueue=True,  # thread/process-safe (FastAPI + LangGraph tournent en async/threads)
    )
