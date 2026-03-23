import json
import os
import time
from datetime import datetime

STATS_FILE = "stats.json"
REPORTS_DIR = "reports"

class StatsManager:
    def __init__(self):
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
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
            
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
        
        # Tenta carregar os dados mais recentes do disco para não sobrescrever ganhos de outras instâncias
        for _ in range(5): # 5 tentativas de lock "suave"
            try:
                current_data = self._load()
                # Mantém o reset diário consistente entre as instâncias
                today = datetime.now().strftime("%Y-%m-%d")
                if current_data.get("last_reset") != today:
                    # Se mudou o dia em outra instância, respeitamos o reset dela
                    self.data = current_data
                    self._check_reset()
                else:
                    self.data["accounts"] = current_data.get("accounts", {})
                
                # Atualiza os pontos desta instância
                self.data["accounts"][email] = points
                self.data["last_reset"] = today
                
                # Salva os dados mesclados
                self._save()
                break
            except Exception:
                time.sleep(0.5)

    def get_profit(self, email):
        """Retorna o lucro já acumulado hoje para este email."""
        self._check_reset()
        return self.data.get("accounts", {}).get(email, 0)

    def get_all_stats(self):
        self._check_reset()
        return self.data["accounts"]

# Singleton
manager = StatsManager()
