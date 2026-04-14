"""Typed view over legacy module-level configuration."""

from __future__ import annotations

from dataclasses import dataclass, field

import config


@dataclass(frozen=True)
class AppSettings:
    app_package: str = config.APP_PACKAGE
    adb_path: str = config.ADB_PATH
    debug_folder: str = config.DEBUG_FOLDER
    safe_ad_packages: tuple[str, ...] = field(default_factory=lambda: tuple(config.SAFE_AD_PACKAGES))
    stats_save_interval: float = config.STATS_SAVE_INTERVAL
    max_log_lines: int = config.MAX_LOG_LINES


def load_settings() -> AppSettings:
    return AppSettings()

