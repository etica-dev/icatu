"""Configuração centralizada de logging para toda a aplicação."""
import logging
import sys

_FMT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configura o logger raiz com handler para stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)
    # Silencia logs verbosos de libs externas
    for noisy in ("uvicorn.access", "httpx", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger nomeado (ex: get_logger('validador'))."""
    return logging.getLogger(name)
