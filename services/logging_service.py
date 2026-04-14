"""Central logging setup for CLI, GUI and packaged builds."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: str = "logs", debug: bool = False) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(Path(log_dir) / "spinbot.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

