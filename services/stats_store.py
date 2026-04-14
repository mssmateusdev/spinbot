"""Thread-safe persistence for daily account metrics."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class StatsStore:
    def __init__(self, stats_file: str = "stats.json", reports_dir: str = "reports", save_interval: float = 5.0):
        self.stats_file = Path(stats_file)
        self.reports_dir = Path(reports_dir)
        self.save_interval = save_interval
        self._lock = threading.RLock()
        self._last_save = 0.0
        self._dirty = False
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = self._load()
        self._check_reset()

    def _load(self) -> dict[str, Any]:
        if self.stats_file.exists():
            try:
                with self.stats_file.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, dict):
                    data.setdefault("accounts", {})
                    data.setdefault("last_reset", datetime.now().strftime("%Y-%m-%d"))
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"last_reset": datetime.now().strftime("%Y-%m-%d"), "accounts": {}}

    def _save(self) -> None:
        tmp_path = self.stats_file.with_suffix(self.stats_file.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, indent=4, ensure_ascii=False)
        try:
            os.replace(tmp_path, self.stats_file)
        except PermissionError:
            # Some Windows/sandbox combinations deny atomic replace even inside the
            # workspace. Keep the app alive with a direct write fallback.
            with self.stats_file.open("w", encoding="utf-8") as file:
                json.dump(self.data, file, indent=4, ensure_ascii=False)
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        self._last_save = time.time()
        self._dirty = False

    def _save_if_due(self, force: bool = False) -> None:
        if force or (time.time() - self._last_save) >= self.save_interval:
            self._save()
        else:
            self._dirty = True

    def _check_reset(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.data.get("last_reset") != today:
            self._generate_daily_report()
            self.data["last_reset"] = today
            self.data["accounts"] = {}
            self._save()

    def _generate_daily_report(self) -> None:
        date_str = self.data.get("last_reset")
        accounts = self.data.get("accounts", {})
        if not accounts:
            return

        report_path = self.reports_dir / f"relatorio_{date_str}.txt"
        total = 0
        lines = [f"--- RELATORIO DIARIO DE GANHOS ({date_str}) ---", ""]
        for email, profit in accounts.items():
            lines.append(f"Email: {email}")
            lines.append(f"Ganho: +{profit:,}".replace(",", "."))
            lines.append("-" * 20)
            total += profit
        lines.append("")
        lines.append(f"TOTAL DO DIA: +{total:,}".replace(",", "."))
        report_path.write_text("\n".join(lines), encoding="utf-8")

    def update_profit(self, email: str, points: int) -> None:
        if not email:
            return
        with self._lock:
            try:
                current_data = self._load()
                today = datetime.now().strftime("%Y-%m-%d")
                if current_data.get("last_reset") != today:
                    self.data = current_data
                    self._check_reset()
                else:
                    self.data["accounts"] = current_data.get("accounts", {})
                self.data["accounts"][email] = points
                self.data["last_reset"] = today
                self._save_if_due()
            except Exception:
                self.data.setdefault("accounts", {})[email] = points
                self._dirty = True

    def get_profit(self, email: str) -> int:
        with self._lock:
            self._check_reset()
            return int(self.data.get("accounts", {}).get(email, 0))

    def get_all_stats(self) -> dict[str, int]:
        with self._lock:
            self._check_reset()
            if self._dirty:
                self._save_if_due(force=True)
            return dict(self.data.get("accounts", {}))
