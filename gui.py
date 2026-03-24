import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, scrolledtext
import threading
import queue
import os
import sys
from datetime import datetime
from stats_manager import manager
from crypto_utils import CryptoConverter

import config

# ──────────────────────────────────────────────────────────
# CONFIGURAÇÕES E UTILITÁRIOS
# ──────────────────────────────────────────────────────────

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Importar lógica do automador
import adbutils
from main import SpinAutomator
from device_profiles import calibrate_device

# Configurar caminho do ADB para o adbutils usar o interno se disponível
_adb_bin = resource_path("adb.exe")
if os.path.exists(_adb_bin):
    adbutils.adb_path = _adb_bin

# CORES (GNI Palette - Dark Modern)
C = {
    "bg":       "#18181b",   # Zinc 900
    "sidebar":  "#27272a",   # Zinc 800
    "card":     "#27272a",   # Zinc 800 (Card BG)
    "console":  "#09090b",   # Zinc 950
    "text":     "#f4f4f5",   # Zinc 100
    "text_h":   "#a1a1aa",   # Zinc 400
    "accent":   "#6366f1",   # Indigo 500 (Primary Action)
    "accent_h": "#818cf8",   # Indigo 400 (Hover)
    "active":   "#4f46e5",   # Indigo 600 (Sidebar Active)
    "danger":   "#ef4444",   # Red 500
    "success":  "#22c55e",   # Green 500
    "warning":  "#eab308",   # Yellow 500
    "border":   "#3f3f46",   # Zinc 700
}

FONT_HEAD = ("Segoe UI", 16, "bold")
FONT_SUB  = ("Segoe UI", 12, "bold")
FONT_MAIN = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 10)

class AutomatorWindow(tk.Toplevel):
    def __init__(self, parent, serial, model, email, stop_event):
        super().__init__(parent)
        self.serial = serial
        self.model = model
        self.email = email
        self.stop_event = stop_event
        self.is_active = True
        
        # Design Compacto (Solicitação do Usuário)
        self.title(f"{model}")
        self.geometry("340x460")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        
        # UI Elements (Stats)
        self._build_ui()
        
    def _build_ui(self):
        f = tk.Frame(self, bg=C["bg"], padx=10, pady=10)
        f.pack(fill="both", expand=True)
        
        tk.Label(f, text=f"Conta: {self.email}", font=("Segoe UI", 8, "bold"), bg=C["bg"], fg=C["accent"]).pack(anchor="w")
        tk.Label(f, text=f"ID: {self.serial}", font=("Segoe UI", 7), bg=C["bg"], fg=C["text_h"]).pack(anchor="w", pady=(0,8))
        
        # Stats Grid (Mais compacto)
        s_frame = tk.Frame(f, bg=C["card"], padx=8, pady=8)
        s_frame.pack(fill="x", pady=5)
        s_frame.columnconfigure(0, weight=1)
        s_frame.columnconfigure(1, weight=1)
        
        # Ciclos
        fc = tk.Frame(s_frame, bg=C["card"])
        fc.grid(row=0, column=0, sticky="nw")
        tk.Label(fc, text="CICLOS", font=("Segoe UI", 7, "bold"), bg=C["card"], fg=C["text_h"]).pack(anchor="w")
        self.lbl_cycles = tk.Label(fc, text="0", font=("Segoe UI", 12, "bold"), bg=C["card"], fg=C["success"])
        self.lbl_cycles.pack(anchor="w")
        
        # Pontos
        fp = tk.Frame(s_frame, bg=C["card"])
        fp.grid(row=0, column=1, sticky="nw")
        tk.Label(fp, text="PONTOS HOJE", font=("Segoe UI", 7, "bold"), bg=C["card"], fg=C["text_h"]).pack(anchor="w")
        self.lbl_profit = tk.Label(fp, text="+0", font=("Segoe UI", 11, "bold"), bg=C["card"], fg=C["success"])
        self.lbl_profit.pack(anchor="w")
        
        # BRL
        fb = tk.Frame(s_frame, bg=C["card"])
        fb.grid(row=1, column=1, sticky="nw", pady=(8,0))
        tk.Label(fb, text="LUCRO BRL", font=("Segoe UI", 7, "bold"), bg=C["card"], fg=C["text_h"]).pack(anchor="w")
        self.lbl_profit_brl = tk.Label(fb, text="R$ 0,00", font=("Segoe UI", 11, "bold"), bg=C["card"], fg=C["success"])
        self.lbl_profit_brl.pack(anchor="w")
        
        # Tempo
        ft = tk.Frame(s_frame, bg=C["card"])
        ft.grid(row=1, column=0, sticky="nw", pady=(8,0))
        tk.Label(ft, text="TEMPO", font=("Segoe UI", 7, "bold"), bg=C["card"], fg=C["text_h"]).pack(anchor="w")
        self.lbl_time = tk.Label(ft, text="00:00:00", font=("Segoe UI", 12, "bold"), bg=C["card"], fg=C["accent"])
        self.lbl_time.pack(anchor="w")
        
        # Status
        self.status_lbl = tk.Label(f, text="Status: Iniciando...", font=("Segoe UI", 8), bg=C["bg"], fg=C["warning"])
        self.status_lbl.pack(pady=5)
        
        # Mini Log (Menor altura para compacidade)
        log_f = tk.LabelFrame(f, text="Logs Locais", bg=C["bg"], fg=C["text_h"], bd=0, font=("Segoe UI", 8))
        log_f.pack(fill="both", expand=True)
        self.console = tk.Text(log_f, height=10, state="disabled", bg=C["console"], fg=C["text_h"], font=("Consolas", 7), bd=0, padx=5, pady=5)
        self.console.pack(fill="both", expand=True)

    def log(self, msg, level="info"):
        if not self.winfo_exists(): return
        self.console.config(state="normal")
        ts = datetime.now().strftime("[%H:%M] ")
        self.console.insert("end", f"{ts}{msg}\n")
        self.console.see("end")
        self.console.config(state="disabled")
        
    def update_stats(self, stats):
        if not self.winfo_exists(): return
        self.lbl_cycles.config(text=str(stats.get("cycles", 0)))
        p = stats.get('profit', 0)
        self.lbl_profit.config(text=f"+{p:,}".replace(',', '.'))
        brl = CryptoConverter.coins_to_brl(p)
        self.lbl_profit_brl.config(text=f"R$ {brl:,.4f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        self.lbl_time.config(text=stats.get('elapsed', "00:00:00"))
        self.status_lbl.config(text="Status: Ativo", fg=C["success"])

    def on_finish(self):
        self.is_active = False
        if self.winfo_exists():
            self.status_lbl.config(text="Status: Finalizado", fg=C["danger"])

class SpinGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SPINBOT - v0.4.0 (Multi-Instance)")
        self.root.geometry("950x700")
        self.root.configure(bg=C["bg"])
        self.root.minsize(850, 600)

        # Ícone
        try:
            icon_path = resource_path("icon.png")
            if os.path.exists(icon_path):
                img = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, img)
        except: pass

        # Variáveis de Estado
        self.log_queue = queue.Queue()
        self.is_running = False
        self.stop_event = threading.Event()
        
        self.selected_device = tk.StringVar()
        self.email_faucet = tk.StringVar(value="seuemail@exemplo.com")
        self.adb_ip = tk.StringVar(value="127.0.0.1:5555")
        
        self.device_vars = {} # Dicionário serial -> tk.BooleanVar
        self.ultra_eco = tk.BooleanVar(value=False)
        
        # Timer e Estatísticas persistentes na UI
        self.session_start = None
        self.last_profit = 0

        # Configuração do Grid
        self.root.grid_columnconfigure(0, weight=0) # Barra lateral fixa
        self.root.grid_columnconfigure(1, weight=1) # Conteúdo expande
        self.root.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._build_sidebar()

        # Content Area
        self.content_frame = tk.Frame(self.root, bg=C["bg"])
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # Views
        self.views = {}
        self._init_views()
        
        self.root.after(100, self._poll_logs)
        self.root.after(1000, self._tick) # Timer real-time
        self._refresh_devs()
        self._show_view("home")

    def _build_sidebar(self):
        self.sidebar = tk.Frame(self.root, bg=C["sidebar"], width=200)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        tk.Label(self.sidebar, text="SPINBOT", font=("Segoe UI", 16, "bold"), 
                 bg=C["sidebar"], fg=C["text"], pady=20).pack(fill="x")

        self.nav_btns = {}
        self._add_nav_btn("home", "📊 Dashboard", lambda: self._show_view("home"))
        self._add_nav_btn("predictions", "📈 Projeções", lambda: self._show_predictions())
        self._add_nav_btn("reports", "📊 Relatórios", lambda: self._show_reports())
        self._add_nav_btn("settings", "⚙️ Configurações", lambda: self._show_view("settings"))
        self._add_nav_btn("console", "🖥️ Console", lambda: self._show_view("console"))

        # Lista de Emails (Múltiplas Contas - 1 por linha)
        tk.Label(self.sidebar, text="Lista de Emails (1 por linha):", font=("Segoe UI", 9, "bold"), 
                 bg=C["sidebar"], fg=C["text_h"]).pack(pady=(20, 2), padx=15, anchor="w")
        
        entry_container = tk.Frame(self.sidebar, bg=C["border"], padx=1, pady=1)
        entry_container.pack(pady=(0, 10), padx=15, fill="both", expand=True)
        
        self.txt_emails = scrolledtext.ScrolledText(entry_container, bg=C["card"], fg="white", 
                                                  insertbackground="white", bd=0, font=("Segoe UI", 9),
                                                  highlightthickness=0, relief="flat", height=5)
        self.txt_emails.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Preencher com info anterior
        from stats_manager import manager
        last_emails = list(manager.get_all_stats().keys())
        if last_emails: 
            self.txt_emails.insert("1.0", "\n".join(last_emails))

        tk.Label(self.sidebar, text="v0.4.0 (Multi-Instance)", font=("Segoe UI", 8), 
                 bg=C["sidebar"], fg=C["text_h"]).pack(side="bottom", pady=10)

    def _add_nav_btn(self, key, text, command):
        btn = tk.Button(self.sidebar, text=text, command=command,
                        bg=C["sidebar"], fg=C["text_h"],
                        font=("Segoe UI", 10), bd=0, activebackground=C["active"],
                        activeforeground="white", cursor="hand2", anchor="w", padx=15, pady=8)
        btn.pack(fill="x", pady=1)
        self.nav_btns[key] = btn

    def _init_views(self):
        self.views["home"] = self._create_home_view()
        self.views["predictions"] = self._create_predictions_view()
        self.views["settings"] = self._create_settings_view()
        self.views["console"] = self._create_console_view()
        self.views["reports"] = self._create_reports_view()

    def _tick(self):
        """Cronômetro real-time na UI independente do bot."""
        if self.is_running and self.session_start:
            elapsed = datetime.now() - self.session_start
            self.lbl_time.config(text=str(elapsed).split('.')[0])
            # Atualiza projeções a cada tick se estiver na aba
            self._update_predictions(self.last_profit, str(elapsed).split('.')[0])
        
        self.root.after(1000, self._tick)

    def _show_view(self, view_name):
        for k, btn in self.nav_btns.items():
            if k == view_name:
                btn.configure(bg=C["active"], fg="white")
            else:
                btn.configure(bg=C["sidebar"], fg=C["text_h"])
        
        frame = self.views.get(view_name)
        if frame:
            frame.tkraise()

    # ── VIEWS IMPLEMENTATION ────────────────────────────────

    def _create_home_view(self):
        f = tk.Frame(self.content_frame, bg=C["bg"])
        f.grid(row=0, column=0, sticky="nsew")
        f.grid_columnconfigure(0, weight=1)
        
        header = tk.Frame(f, bg=C["bg"])
        header.pack(fill="x", pady=(0, 10))
        tk.Label(header, text="Dashboard", font=("Segoe UI", 14, "bold"), bg=C["bg"], fg=C["text"]).pack(side="left")
        
        tk.Button(header, text="↻ Atualizar Dispositivos", command=self._refresh_devs, 
                  bg=C["sidebar"], fg=C["text_h"], font=("Segoe UI", 8), bd=0, padx=10, cursor="hand2").pack(side="right")

        # Seleção de Instâncias (Solicitação do Usuário)
        sel_container = tk.LabelFrame(f, text="SELECIONE AS INSTÂNCIAS PARA TRABALHAR", bg=C["bg"], fg=C["accent"], 
                                    font=("Segoe UI", 8, "bold"), bd=0)
        sel_container.pack(fill="x", pady=(0, 15))
        
        self.device_list_frame = tk.Frame(sel_container, bg=C["sidebar"], padx=10, pady=10)
        self.device_list_frame.pack(fill="x")
        
        # Opções de Otimização
        opt_frame = tk.Frame(f, bg=C["bg"])
        opt_frame.pack(fill="x", pady=(0, 10))
        
        tk.Checkbutton(opt_frame, text="🍀 MODO ULTRA-ECO (Reduzir resolução/DPI p/ economizar CPU/GPU)", 
                       variable=self.ultra_eco, bg=C["bg"], fg=C["success"], 
                       selectcolor=C["bg"], activebackground=C["bg"],
                       activeforeground=C["success"], font=("Segoe UI", 8, "bold"),
                       bd=0, cursor="hand2").pack(side="left")
        
        # Botão Principal
        self.btn_main = tk.Button(f, text="INICIAR AUTOMAÇÃO", command=self._toggle_run,
                                  bg=C["accent"], fg="white", font=("Segoe UI", 12, "bold"),
                                  bd=0, cursor="hand2", activebackground=C["accent_h"], pady=12)
        self.btn_main.pack(fill="x", pady=5)

        # Stats Container (Grid)
        stats_frame = tk.Frame(f, bg=C["card"], padx=15, pady=15)
        stats_frame.pack(fill="x", pady=10)
        stats_frame.columnconfigure(0, weight=1)
        stats_frame.columnconfigure(1, weight=1)

        # Ciclos
        f_cycles = tk.Frame(stats_frame, bg=C["card"])
        f_cycles.grid(row=0, column=0, sticky="nw")
        tk.Label(f_cycles, text="CICLOS TOTAIS", font=("Segoe UI", 8, "bold"), bg=C["card"], fg=C["text_h"]).pack(anchor="w")
        self.lbl_cycles = tk.Label(f_cycles, text="0", font=("Segoe UI", 24, "bold"), bg=C["card"], fg=C["success"])
        self.lbl_cycles.pack(anchor="w")

        # Ganho Session
        f_profit = tk.Frame(stats_frame, bg=C["card"])
        f_profit.grid(row=0, column=1, sticky="nw")
        tk.Label(f_profit, text="PONTOS TOTAIS HOJE", font=("Segoe UI", 8, "bold"), bg=C["card"], fg=C["text_h"]).pack(anchor="w")
        self.lbl_profit = tk.Label(f_profit, text="+0", font=("Segoe UI", 18, "bold"), bg=C["card"], fg=C["success"])
        self.lbl_profit.pack(anchor="w")

        # Ganho BRL
        f_brl = tk.Frame(stats_frame, bg=C["card"])
        f_brl.grid(row=1, column=1, sticky="nw", pady=(15, 0))
        tk.Label(f_brl, text="LUCRO TOTAL BRL", font=("Segoe UI", 8, "bold"), bg=C["card"], fg=C["text_h"]).pack(anchor="w")
        self.lbl_profit_brl = tk.Label(f_brl, text="R$ 0,00", font=("Segoe UI", 18, "bold"), bg=C["card"], fg=C["success"])
        self.lbl_profit_brl.pack(anchor="w")

        # Tempo de Execução
        f_time = tk.Frame(stats_frame, bg=C["card"])
        f_time.grid(row=1, column=0, sticky="nw", pady=(15, 0))
        tk.Label(f_time, text="TEMPO DE SESSÃO", font=("Segoe UI", 9, "bold"), bg=C["card"], fg=C["text_h"]).pack(anchor="w")
        self.lbl_time = tk.Label(f_time, text="00:00:00", font=("Segoe UI", 24, "bold"), bg=C["card"], fg=C["accent"])
        self.lbl_time.pack(anchor="w")

        # Status
        self.status_lbl = tk.Label(stats_frame, text="Status: Aguardando...", font=("Segoe UI", 9), bg=C["card"], fg=C["text_h"])
        self.status_lbl.grid(row=2, column=0, columnspan=2, sticky="sw", pady=(20,0))
        
        # Mini Console
        log_frame = tk.LabelFrame(f, text="Últimas Atividades", bg=C["bg"], fg=C["text_h"], bd=0, font=("Segoe UI", 9))
        log_frame.pack(fill="both", expand=True, pady=10)
        
        self.mini_log = tk.Text(log_frame, height=5, state="disabled", bg=C["console"], fg=C["text_h"],
                                font=("Consolas", 8), bd=0, padx=5, pady=5)
        self.mini_log.pack(fill="both", expand=True)

        return f

    def _create_settings_view(self):
        f = tk.Frame(self.content_frame, bg=C["bg"])
        f.grid(row=0, column=0, sticky="nsew")
        tk.Label(f, text="Configurações", font=("Segoe UI", 14, "bold"), bg=C["bg"], fg=C["text"]).pack(anchor="w", pady=(0, 20))

        # Grupo: Dispositivo
        self._build_setting_group(f, "Dispositivo & Conexão", [
            ("combo_refresh", "Selecione o Dispositivo:", self.selected_device, self._refresh_devs),
            ("entry_btn", "ADB Remoto (IP:Porta):", self.adb_ip, "Conectar", self._connect_adb)
        ])
        
        # Grupo: Conta (Removed as email is now in sidebar)
        # self._build_setting_group(f, "Conta Faucet", [
        #     ("entry", "E-mail de Login:", self.email_faucet)
        # ])
        
        # Ferramentas
        tools_frame = tk.LabelFrame(f, text="Ferramentas Avançadas", bg=C["bg"], fg=C["accent"], 
                                   font=("Segoe UI", 9, "bold"), bd=1, relief="flat", padx=10, pady=10)
        tools_frame.pack(fill="x", pady=10)
        tk.Button(tools_frame, text="Recalibrar Tela", command=self._start_calib,
                  bg=C["sidebar"], fg=C["text"], bd=0, padx=15, pady=8, cursor="hand2").pack(anchor="w")

        return f

    def _build_setting_group(self, parent, title, items):
        frame = tk.LabelFrame(parent, text=title, bg=C["bg"], fg=C["accent"], 
                              font=("Segoe UI", 9, "bold"), bd=0, padx=0, pady=10)
        frame.pack(fill="x", pady=5)
        
        for item in items:
            type_ = item[0]
            label_text = item[1]
            tk.Label(frame, text=label_text, bg=C["bg"], fg=C["text_h"], font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
            
            if type_ == "combo_refresh":
                box = tk.Frame(frame, bg=C["bg"])
                box.pack(fill="x")
                self.combo_dev = ttk.Combobox(box, textvariable=item[2], state="readonly")
                self.combo_dev.pack(side="left", fill="x", expand=True, ipady=4)
                tk.Button(box, text="↻", command=item[3], bg=C["sidebar"], fg="white", bd=0, padx=10).pack(side="left", padx=5)
            
            elif type_ == "entry":
                tk.Entry(frame, textvariable=item[2], bg=C["sidebar"], fg="white", 
                         insertbackground="white", bd=0).pack(fill="x", ipady=7)
                
            elif type_ == "entry_btn":
                box = tk.Frame(frame, bg=C["bg"])
                box.pack(fill="x")
                tk.Entry(box, textvariable=item[2], bg=C["sidebar"], fg="white", 
                         insertbackground="white", bd=0).pack(side="left", fill="x", expand=True, ipady=7)
                tk.Button(box, text=item[3], command=item[4], bg=C["active"], fg="white", bd=0, padx=15).pack(side="left", padx=5)

    def _create_console_view(self):
        f = tk.Frame(self.content_frame, bg=C["bg"])
        f.grid(row=0, column=0, sticky="nsew")
        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(0, weight=1)
        
        tk.Label(f, text="Console de Logs", font=("Segoe UI", 12, "bold"), bg=C["bg"], fg=C["text"]).grid(row=0, column=0, sticky="w", pady=(0, 10))
        
        self.txt_log = scrolledtext.ScrolledText(f, state="disabled", bg=C["console"], fg=C["text_h"],
                                                font=("Consolas", 9), bd=0, padx=10, pady=10)
        self.txt_log.grid(row=1, column=0, sticky="nsew")
        
        self.txt_log.tag_config("info", foreground=C["text_h"])
        self.txt_log.tag_config("header", foreground=C["text"], font=("Consolas", 10, "bold"))
        self.txt_log.tag_config("success", foreground=C["success"])
        self.txt_log.tag_config("warning", foreground=C["warning"])
        self.txt_log.tag_config("error", foreground=C["danger"])
        self.txt_log.tag_config("action", foreground=C["accent_h"])
        
        return f

    def _create_predictions_view(self):
        f = tk.Frame(self.content_frame, bg=C["bg"])
        f.grid(row=0, column=0, sticky="nsew")
        
        tk.Label(f, text="Projeção de Ganhos", font=("Segoe UI", 14, "bold"), 
                 bg=C["bg"], fg=C["text"]).pack(anchor="w", pady=(0, 20))
        
        self.pred_frame = tk.Frame(f, bg=C["card"], padx=20, pady=20)
        self.pred_frame.pack(fill="x")
        
        self.pred_labels = {}
        for period in ["1 Hora", "12 Horas", "1 Dia", "1 Semana", "1 Mês"]:
            row = tk.Frame(self.pred_frame, bg=C["card"])
            row.pack(fill="x", pady=8)
            tk.Label(row, text=period, font=("Segoe UI", 10), bg=C["card"], fg=C["text_h"]).pack(side="left")
            lbl = tk.Label(row, text="Calculando...", font=("Segoe UI", 11, "bold"), bg=C["card"], fg=C["success"])
            lbl.pack(side="right")
            self.pred_labels[period] = lbl
        
        tk.Label(f, text="* Estimativas baseadas no lucro da sessão atual.", 
                 font=("Segoe UI", 8, "italic"), bg=C["bg"], fg=C["text_h"]).pack(anchor="w", pady=10)
        
        return f

    def _update_predictions(self, profit, elapsed_str):
        try:
            h, m, s = map(int, elapsed_str.split(':'))
            total_seconds = h*3600 + m*60 + s
            if total_seconds < 60: return # Aguarda 1 min para média estável
            
            rate = profit / total_seconds
            
            times = {
                "1 Hora": 3600,
                "12 Horas": 43200,
                "1 Dia": 86400,
                "1 Semana": 604800,
                "1 Mês": 2592000
            }
            
            for k, sec in times.items():
                val = int(rate * sec)
                self.pred_labels[k].config(text=f"+{val:,}".replace(',', '.'))
        except: pass

    def _show_predictions(self):
        self._show_view("predictions")

    def _create_reports_view(self):
        f = tk.Frame(self.content_frame, bg=C["bg"])
        f.grid(row=0, column=0, sticky="nsew")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        
        tk.Label(f, text="Relatório Diário de Ganhos", font=("Segoe UI", 14, "bold"), 
                 bg=C["bg"], fg=C["text"]).grid(row=0, column=0, sticky="w", pady=(0, 15))
        
        self.reports_text = tk.Text(f, bg=C["console"], fg=C["text_h"], 
                                   font=("Consolas", 11), bd=0, padx=15, pady=15)
        self.reports_text.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        
        btn_refresh = tk.Button(f, text="Atualizar Relatório", command=self._update_reports_text,
                                  bg=C["accent"], fg="white", font=("Segoe UI", 10, "bold"),
                                  bd=0, cursor="hand2", activebackground=C["accent_h"], pady=8)
        btn_refresh.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        
        return f

    def _update_reports_text(self):
        stats = manager.get_all_stats()
        self.reports_text.config(state="normal")
        self.reports_text.delete("1.0", tk.END)
        
        self.reports_text.insert(tk.END, f"--- LUCROS DE HOJE ({manager.data['last_reset']}) ---\n\n", "header")
        total = 0
        if not stats:
            self.reports_text.insert(tk.END, "Nenhum dado registrado hoje ainda.\n\n", "info")
        else:
            for email, profit in stats.items():
                self.reports_text.insert(tk.END, f"📧 {email}\n", "info")
                self.reports_text.insert(tk.END, f"💰 Ganho: +{profit:,}\n\n".replace(',', '.'), "success")
                total += profit
        
        self.reports_text.insert(tk.END, "-"*40 + "\n", "info")
        self.reports_text.insert(tk.END, f"💲 TOTAL ACUMULADO : +{total:,}\n".replace(',', '.'), "header")
        self.reports_text.config(state="disabled")

    def _show_reports(self):
        self._update_reports_text()
        self._show_view("reports")

    # ── LOGIC ──────────────────────────────────────────────

    def log(self, msg, level="info"):
        self.log_queue.put((msg, level))

    def _poll_logs(self):
        max_lines = getattr(config, 'MAX_LOG_LINES', 500)
        while not self.log_queue.empty():
            msg, level = self.log_queue.get()
            
            if hasattr(self, 'txt_log'):
                self.txt_log.config(state="normal")
                num_lines = int(self.txt_log.index('end-1c').split('.')[0])
                if num_lines > max_lines:
                    self.txt_log.delete('1.0', f'{num_lines - max_lines + 1}.0')
                
                timestamp = datetime.now().strftime("[%H:%M] ")
                self.txt_log.insert("end", timestamp, "info")
                self.txt_log.insert("end", f"{msg}\n", level)
                self.txt_log.see("end")
                self.txt_log.config(state="disabled")
            
            if hasattr(self, 'mini_log'):
                self.mini_log.config(state="normal")
                num_lines = int(self.mini_log.index('end-1c').split('.')[0])
                if num_lines > 15:
                    self.mini_log.delete('1.0', '2.0')
                self.mini_log.insert("end", f"> {msg}\n")
                self.mini_log.see("end")
                self.mini_log.config(state="disabled")
        
        self.root.after(100, self._poll_logs)

    def _toggle_run(self):
        if not self.is_running:
            self._start()
        else:
            self._stop()

    def _start(self):
        # 1. Obter dispositivos selecionados
        selected_serials = [s for s, var in self.device_vars.items() if var.get()]
        
        if not selected_serials:
            messagebox.showwarning("Aviso", "Selecione pelo menos uma instância na lista acima para iniciar!")
            return

        try:
            all_devices = adbutils.adb.device_list()
            devices = [d for d in all_devices if d.serial in selected_serials]
        except Exception as e:
            messagebox.showerror("Erro ADB", f"Falha ao listar dispositivos: {e}")
            return

        if not devices:
            messagebox.showwarning("Aviso", "Dispositivos selecionados não foram encontrados. Tente atualizar a lista.")
            return

        # 2. Obter emails da lista
        emails_raw = self.txt_emails.get("1.0", tk.END).strip()
        emails = [e.strip() for e in emails_raw.split("\n") if e.strip()]

        if not emails:
            messagebox.showwarning("Aviso", "Insira pelo menos um email na lista lateral!")
            return

        # 3. Validar contagem
        if len(emails) < len(devices):
            messagebox.showwarning("Faltam Emails", 
                f"Você selecionou {len(devices)} dispositivos, mas inseriu apenas {len(emails)} emails.\n"
                "Adicione mais emails na barra lateral.")
            return

        self.is_running = True
        self.session_start = datetime.now()
        self.stop_event.clear()
        self.btn_main.configure(text="PARAR TODAS AS INSTÂNCIAS", bg=C["danger"])
        self.status_lbl.config(text=f"Status: {len(devices)} Instâncias Ativas", fg=C["success"])
        
        self.instances = []
        for i, dev in enumerate(devices):
            email = emails[i]
            serial = dev.serial
            model = dev.prop.get('ro.product.model', 'Desconhecido')
            
            self.log(f"Iniciando Instância #{i+1}: {model} ({serial}) -> {email}", "header")
            
            # Criar Janela Individual (Design Compacto)
            window = AutomatorWindow(self.root, serial, model, email, self.stop_event)
            self.instances.append(window)
            
            # Posicionamento em cascata para não sobrepor tudo de uma vez
            offset = i * 40
            window.geometry(f"+{offset}+{offset}")
            
            # Iniciar Thread da Automação
            threading.Thread(
                target=self._run_instance, 
                args=(serial, email, window), 
                daemon=True
            ).start()

    def _stop(self):
        if self.is_running:
            self.log("Solicitando parada de todas as instâncias...", "warning")
            self.stop_event.set()
            self.status_lbl.config(text="Status: Parando...", fg=C["warning"])

    def _run_instance(self, serial, email, window):
        def _multi_log(msg, level="info"):
            window.log(msg, level)
            self.log(f"[{serial}] {msg}", level)

        automator = SpinAutomator(
            serial=serial,
            account_email=email,
            stop_event=self.stop_event,
            on_log=_multi_log,
            on_stats_update=window.update_stats
        )
        
        # Aplicar otimizações se selecionado
        if self.ultra_eco.get():
            from adb_utils import apply_headless_optimizations
            import uiautomator2 as u2
            try:
                d = u2.connect(serial)
                apply_headless_optimizations(d)
            except: pass

        try:
            automator.run()
        except Exception as e:
            window.log(f"Erro Crítico na Instância: {e}", "error")
        finally:
            # Restaurar padrões ao sair
            if self.ultra_eco.get():
                from adb_utils import restore_display_defaults
                import uiautomator2 as u2
                try:
                    d = u2.connect(serial)
                    restore_display_defaults(d)
                except: pass
            
            self.root.after(0, lambda: self._on_instance_finish(window))

    def _on_instance_finish(self, window):
        window.on_finish()
        # Verificar se todas terminaram
        if all(not w.is_active for w in self.instances):
            self._on_all_finish()

    def _on_all_finish(self):
        self.is_running = False
        self.btn_main.configure(text="INICIAR AUTOMAÇÃO", bg=C["accent"])
        self.status_lbl.config(text="Status: Processo Finalizado", fg=C["text_h"])
        self.log("Todas as instâncias foram finalizadas.", "header")

    def _update_stats(self, stats):
        def _u():
            if hasattr(self, 'lbl_cycles'):
                self.lbl_cycles.config(text=str(stats.get("cycles", 0)))
            if hasattr(self, 'lbl_profit'):
                profit = stats.get('profit', 0)
                self.lbl_profit.config(text=f"+{profit:,}".replace(',', '.'))
                self.last_profit = profit
                
                # Atualizar Lucro BRL
                brl_val = CryptoConverter.coins_to_brl(profit)
                self.lbl_profit_brl.config(text=f"R$ {brl_val:,.4f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
            if hasattr(self, 'lbl_balance'):
                balance = stats.get('current_coins', 0)
                self.lbl_balance.config(text=f"{balance:,}".replace(',', '.'))
            
            # Não atualizamos o timer por aqui mais, o _tick cuida disso
            # Mas atualizamos as projeções
            # self._update_predictions(stats.get('profit', 0), stats.get('elapsed', "00:00:00"))
            
            dev_str = self.selected_device.get()
            if dev_str:
                self.root.title(f"SPINBOT - {dev_str}")
        self.root.after(0, _u)

    def _refresh_devs(self):
        try:
            # Limpar lista atual
            if hasattr(self, 'device_list_frame'):
                for widget in self.device_list_frame.winfo_children():
                    widget.destroy()
            
            devices = adbutils.adb.device_list()
            vals = []
            
            if not devices:
                if hasattr(self, 'device_list_frame'):
                    tk.Label(self.device_list_frame, text="Nenhum dispositivo detectado. Verifique o ADB.", 
                             bg=C["sidebar"], fg=C["danger"], font=("Segoe UI", 9)).pack(pady=5)
            
            for i, d in enumerate(devices, 1):
                model = d.prop.get('ro.product.model', '?')
                serial = d.serial
                
                # Criar variável se não existir
                if serial not in self.device_vars:
                    self.device_vars[serial] = tk.BooleanVar(value=True)
                
                # Checkbutton estilizado
                if hasattr(self, 'device_list_frame'):
                    f_item = tk.Frame(self.device_list_frame, bg=C["sidebar"])
                    f_item.pack(fill="x", pady=2)
                    
                    cb = tk.Checkbutton(f_item, text=f"{i}. {model} ({serial})", 
                                       variable=self.device_vars[serial],
                                       bg=C["sidebar"], fg=C["text"], 
                                       selectcolor=C["bg"], activebackground=C["sidebar"],
                                       activeforeground=C["accent"], font=("Segoe UI", 9),
                                       bd=0, cursor="hand2")
                    cb.pack(side="left")
                    
                    label_status = tk.Label(f_item, text="• Online", bg=C["sidebar"], fg=C["success"], font=("Segoe UI", 8))
                    label_status.pack(side="right", padx=10)

                vals.append(f"{i}. {serial} | {model}")
            
            # Também atualiza o combo nas configurações por compatibilidade
            if hasattr(self, 'combo_dev'):
                self.combo_dev['values'] = vals
                if vals: self.combo_dev.current(0)
                
        except Exception as e:
            print(f"Erro ao atualizar dispositivos: {e}")

    def _connect_adb(self):
        addr = self.adb_ip.get()
        if not addr: return
        try:
            self.log(f"Conectando a {addr}...", "action")
            r = adbutils.adb.connect(addr)
            self.log(f"Resultado: {r}", "info")
            self._refresh_devs()
        except Exception as e: self.log(str(e), "error")

    def _start_calib(self):
        dev = self.selected_device.get()
        if not dev: 
            messagebox.showwarning("Erro", "Selecione um dispositivo!")
            return
        try:
            if ". " in dev and " | " in dev:
                serial = dev.split(". ")[1].split(" | ")[0]
            else:
                serial = dev.split(" | ")[0]
        except: serial = dev
        def _calib():
            self.log("Iniciando calibração...", "action")
            try:
                import uiautomator2 as u2
                d = u2.connect(serial)
                if calibrate_device(d, serial):
                    self.log("Calibrado com sucesso!", "success")
                else:
                    self.log("Falha na calibração.", "error")
            except Exception as e: self.log(str(e), "error")
        threading.Thread(target=_calib, daemon=True).start()

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    root = tk.Tk()
    app = SpinGUI(root)
    root.mainloop()
