import json
import os
import threading
import time
from datetime import datetime

import config

STATS_FILE = "stats.json"
REPORTS_DIR = "reports"

class StatsManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._last_save = 0.0
        self._dirty = False
        if not os.path.exists(REPORTS_DIR):
            os.makedirs(REPORTS_DIR)
        self.data = self._load()
        self._check_reset()

    def _load(self):
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {"last_reset": datetime.now().strftime("%Y-%m-%d"), "accounts": {}}

    def _save(self):
        tmp_path = f"{STATS_FILE}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        # Escrita atômica evita JSON corrompido se outra thread ler durante o flush.
        os.replace(tmp_path, STATS_FILE)
        self._last_save = time.time()
        self._dirty = False

    def _save_if_due(self, force=False):
        interval = getattr(config, "STATS_SAVE_INTERVAL", 5.0)
        if force or (time.time() - self._last_save) >= interval:
            self._save()
        else:
            self._dirty = True
            
    def _check_reset(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.data.get("last_reset") != today:
            self._generate_daily_report()
            self.data["last_reset"] = today
            self.data["accounts"] = {} # Reset diário
            self._save()

    def _generate_daily_report(self):
        date_str = self.data.get("last_reset")
        report_path = os.path.join(REPORTS_DIR, f"relatorio_{date_str}.txt")
        accounts = self.data.get("accounts", {})
        
        if not accounts: return
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"--- RELATÓRIO DIÁRIO DE GANHOS ({date_str}) ---\n\n")
            total = 0
            for email, profit in accounts.items():
                f.write(f"Email: {email}\nGanho: +{profit:,}\n".replace(',', '.'))
                f.write("-" * 20 + "\n")
                total += profit
            f.write(f"\nTOTAL DO DIA: +{total:,}\n".replace(',', '.'))

    def update_profit(self, email, points):
        """Atualiza o lucro de uma conta específica, suportando múltiplas instâncias."""
        if not email: return

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
                # Última linha de defesa: mantém o estado em memória mesmo se o disco falhar.
                self.data.setdefault("accounts", {})[email] = points
                self._dirty = True

    def get_profit(self, email):
        """Retorna o lucro já acumulado hoje para este email."""
        with self._lock:
            self._check_reset()
            return self.data.get("accounts", {}).get(email, 0)

    def get_all_stats(self):
        with self._lock:
            self._check_reset()
            if self._dirty:
                self._save_if_due(force=True)
            return self.data["accounts"]

# Singleton
manager = StatsManager()
