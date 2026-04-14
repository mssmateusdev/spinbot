"""Compatibility wrapper for the metrics persistence service."""

from __future__ import annotations

import config
from services.stats_store import StatsStore


STATS_FILE = "stats.json"
REPORTS_DIR = "reports"


class StatsManager(StatsStore):
    def __init__(self):
        super().__init__(
            stats_file=STATS_FILE,
            reports_dir=REPORTS_DIR,
            save_interval=getattr(config, "STATS_SAVE_INTERVAL", 5.0),
        )


manager = StatsManager()

