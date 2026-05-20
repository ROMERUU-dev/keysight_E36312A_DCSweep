from __future__ import annotations

import logging
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(level: int = logging.INFO, log_file: str | Path | None = None) -> None:
    """Configure application logging once."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )
