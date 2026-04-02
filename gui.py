import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

import adbutils

import config
from crypto_utils import CryptoConverter
from device_profiles import calibrate_device
from main import SpinAutomator
from stats_manager import manager


APP_VERSION = "0.6.1"


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


_adb_bin = resource_path("adb.exe")
if os.path.exists(_adb_bin):
    adbutils.adb_path = _adb_bin


C = {
    "bg": "#0b1220",
    "surface": "#142033",
    "surface_alt": "#1a2940",
    "surface_soft": "#20324d",
    "panel": "#0f1a2b",
    "console": "#08111d",
    "text": "#eef4ff",
    "muted": "#9cb0c9",
    "accent": "#30c48d",
    "accent_soft": "#1f8b65",
    "accent_alt": "#53a7ff",
    "danger": "#ff6b6b",
    "warning": "#ffcc66",
    "success": "#4ade80",
    "border": "#29405f",
}

FONT_HERO = ("Bahnschrift", 22, "bold")
FONT_TITLE = ("Bahnschrift", 16, "bold")
FONT_SUBTITLE = ("Segoe UI Semibold", 11)
FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY = ("Segoe UI", 8)
FONT_MONO = ("Consolas", 9)


class AutomatorWindow(tk.Toplevel):
    def __init__(self, parent, serial, model, email, stop_event):
        super().__init__(parent)
        self.serial = serial
        self.model = model
        self.email = email
        self.stop_event = stop_event
        self.is_active = True

        self.title(model)
        self.geometry("390x520")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self._build_ui()

    def _metric_block(self, parent, title, value, color, row, column):
        card = tk.Frame(parent, bg=C["surface_alt"], padx=12, pady=10, highlightthickness=1, highlightbackground=C["border"])
        card.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
        tk.Label(card, text=title.upper(), font=FONT_TINY, bg=C["surface_alt"], fg=C["muted"]).pack(anchor="w")
        label = tk.Label(card, text=value, font=("Bahnschrift", 16, "bold"), bg=C["surface_alt"], fg=color)
        label.pack(anchor="w", pady=(6, 0))
        return label

    def _build_ui(self):
        shell = tk.Frame(self, bg=C["bg"], padx=12, pady=12)
        shell.pack(fill="both", expand=True)

        top = tk.Frame(shell, bg=C["surface"], padx=14, pady=14, highlightthickness=1, highlightbackground=C["border"])
        top.pack(fill="x")
        tk.Label(top, text=self.model, font=FONT_TITLE, bg=C["surface"], fg=C["text"]).pack(anchor="w")
        tk.Label(top, text=self.email, font=FONT_SMALL, bg=C["surface"], fg=C["accent"]).pack(anchor="w", pady=(2, 0))
        tk.Label(top, text=self.serial, font=FONT_TINY, bg=C["surface"], fg=C["muted"]).pack(anchor="w", pady=(4, 0))

        stats = tk.Frame(shell, bg=C["bg"])
        stats.pack(fill="x", pady=10)
        stats.grid_columnconfigure((0, 1), weight=1)
        self.lbl_cycles = self._metric_block(stats, "Ciclos", "0", C["success"], 0, 0)
        self.lbl_profit = self._metric_block(stats, "Pontos hoje", "+0", C["accent"], 0, 1)
        self.lbl_time = self._metric_block(stats, "Tempo", "00:00:00", C["accent_alt"], 1, 0)
        self.lbl_profit_brl = self._metric_block(stats, "Lucro BRL", "R$ 0,00", C["warning"], 1, 1)

        self.status_lbl = tk.Label(shell, text="Status: iniciando...", font=FONT_SMALL, bg=C["bg"], fg=C["warning"], anchor="w")
        self.status_lbl.pack(fill="x", pady=(0, 8))

        log_wrap = tk.Frame(shell, bg=C["surface"], padx=1, pady=1, highlightthickness=1, highlightbackground=C["border"])
        log_wrap.pack(fill="both", expand=True)
        self.console = tk.Text(log_wrap, height=12, state="disabled", bg=C["console"], fg=C["muted"], font=("Consolas", 8), bd=0, padx=8, pady=8, insertbackground=C["text"])
        self.console.pack(fill="both", expand=True)

    def log(self, msg, level="info"):
        if not self.winfo_exists():
            return
        self.console.config(state="normal")
        self.console.insert("end", f"[{datetime.now():%H:%M}] {msg}\n")
        self.console.see("end")
        self.console.config(state="disabled")

    def update_stats(self, stats):
        if not self.winfo_exists():
            return
        profit = stats.get("profit", 0)
        brl = CryptoConverter.coins_to_brl(profit)
        self.lbl_cycles.config(text=str(stats.get("cycles", 0)))
        self.lbl_profit.config(text=f"+{profit:,}".replace(",", "."))
        self.lbl_time.config(text=stats.get("elapsed", "00:00:00"))
        self.lbl_profit_brl.config(text=f"R$ {brl:,.4f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.status_lbl.config(text="Status: ativo", fg=C["success"])

    def on_finish(self):
        self.is_active = False
        if self.winfo_exists():
            self.status_lbl.config(text="Status: finalizado", fg=C["danger"])


class SpinGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"SpinBot v{APP_VERSION}")
        self.root.geometry("1180x760")
        self.root.minsize(1024, 680)
        self.root.configure(bg=C["bg"])

        self.log_queue = queue.Queue()
        self.stop_event = threading.Event()

        self.selected_device = tk.StringVar()
        self.adb_ip = tk.StringVar(value="127.0.0.1:5555")
        self.ultra_eco = tk.BooleanVar(value=False)

        self.is_running = False
        self.session_start = None
        self.last_profit = 0
        self.instances = []
        self.device_vars = {}
        self.instance_stats = {}
        self.reports_dirty = True

        self._setup_window_icon()
        self._configure_styles()
        self._build_layout()
        self._init_views()

        self.root.after(100, self._poll_logs)
        self.root.after(1000, self._tick)
        self._refresh_devs()
        self._show_view("home")

    def _setup_window_icon(self):
        try:
            icon_path = resource_path("icon.png")
            if os.path.exists(icon_path):
                icon = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, icon)
                self._icon_ref = icon
        except Exception:
            self._icon_ref = None

    def _configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Spin.TCombobox",
            fieldbackground=C["surface_alt"],
            background=C["surface_alt"],
            foreground=C["text"],
            bordercolor=C["border"],
            lightcolor=C["border"],
            darkcolor=C["border"],
            arrowcolor=C["text"],
        )

    def _build_layout(self):
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self.root, bg=C["panel"], width=290)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        self.content_frame = tk.Frame(self.root, bg=C["bg"])
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

    def _build_sidebar(self):
        brand = tk.Frame(self.sidebar, bg=C["surface"], padx=18, pady=18, highlightthickness=1, highlightbackground=C["border"])
        brand.pack(fill="x", padx=16, pady=(16, 12))
        tk.Label(brand, text="SpinBot", font=FONT_HERO, bg=C["surface"], fg=C["text"]).pack(anchor="w")
        tk.Label(brand, text="Painel de controle para multiplas instancias e monitoramento em tempo real.", font=FONT_SMALL, bg=C["surface"], fg=C["muted"], justify="left", wraplength=230).pack(anchor="w", pady=(8, 0))

        quick = tk.Frame(self.sidebar, bg=C["panel"])
        quick.pack(fill="x", padx=16)
        self.summary_cards = {
            "devices": self._build_sidebar_stat(quick, "Dispositivos", "0"),
            "emails": self._build_sidebar_stat(quick, "Emails", "0"),
        }

        self.nav_btns = {}
        self._add_nav_btn("home", "Dashboard")
        self._add_nav_btn("predictions", "Projecoes")
        self._add_nav_btn("reports", "Relatorios")
        self._add_nav_btn("settings", "Configuracoes")
        self._add_nav_btn("console", "Console")

        email_card = tk.Frame(self.sidebar, bg=C["surface"], padx=16, pady=16, highlightthickness=1, highlightbackground=C["border"])
        email_card.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        tk.Label(email_card, text="Emails de trabalho", font=FONT_SUBTITLE, bg=C["surface"], fg=C["text"]).pack(anchor="w")
        tk.Label(email_card, text="Use um email por linha. Os primeiros emails serao associados aos dispositivos selecionados.", font=FONT_TINY, bg=C["surface"], fg=C["muted"], justify="left", wraplength=230).pack(anchor="w", pady=(6, 10))

        text_wrap = tk.Frame(email_card, bg=C["surface_soft"], padx=1, pady=1)
        text_wrap.pack(fill="both", expand=True)
        self.txt_emails = scrolledtext.ScrolledText(text_wrap, height=8, bg=C["surface_alt"], fg=C["text"], insertbackground=C["text"], bd=0, wrap="word", font=FONT_BODY, padx=10, pady=10, highlightthickness=0)
        self.txt_emails.pack(fill="both", expand=True)

        previous_emails = list(manager.get_all_stats().keys())
        if previous_emails:
            self.txt_emails.insert("1.0", "\n".join(previous_emails))

        tk.Label(self.sidebar, text=f"SpinBot v{APP_VERSION}", font=FONT_TINY, bg=C["panel"], fg=C["muted"]).pack(side="bottom", pady=(0, 14))

    def _build_sidebar_stat(self, parent, title, value):
        card = tk.Frame(parent, bg=C["surface"], padx=14, pady=12, highlightthickness=1, highlightbackground=C["border"])
        card.pack(fill="x", pady=4)
        tk.Label(card, text=title.upper(), font=FONT_TINY, bg=C["surface"], fg=C["muted"]).pack(anchor="w")
        label = tk.Label(card, text=value, font=("Bahnschrift", 18, "bold"), bg=C["surface"], fg=C["accent_alt"])
        label.pack(anchor="w", pady=(4, 0))
        return label

    def _add_nav_btn(self, key, text):
        btn = tk.Button(self.sidebar, text=text, command=lambda item=key: self._show_view(item), bg=C["panel"], fg=C["muted"], activebackground=C["surface"], activeforeground=C["text"], relief="flat", bd=0, cursor="hand2", anchor="w", padx=18, pady=11, font=FONT_BODY)
        btn.pack(fill="x", padx=16, pady=2)
        self.nav_btns[key] = btn

    def _init_views(self):
        self.views = {
            "home": self._create_home_view(),
            "predictions": self._create_predictions_view(),
            "reports": self._create_reports_view(),
            "settings": self._create_settings_view(),
            "console": self._create_console_view(),
        }

    def _make_card(self, parent, title=None, subtitle=None, padding=16):
        card = tk.Frame(parent, bg=C["surface"], padx=padding, pady=padding, highlightthickness=1, highlightbackground=C["border"])
        if title:
            tk.Label(card, text=title, font=FONT_TITLE, bg=C["surface"], fg=C["text"]).pack(anchor="w")
        if subtitle:
            tk.Label(card, text=subtitle, font=FONT_SMALL, bg=C["surface"], fg=C["muted"], wraplength=720, justify="left").pack(anchor="w", pady=(5, 0))
        return card

    def _create_home_view(self):
        frame = tk.Frame(self.content_frame, bg=C["bg"])
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)

        hero = self._make_card(frame, "Operacao central", "Escolha as instancias, acompanhe os numeros do dia e inicie a automacao em lote.", padding=18)
        hero.pack(fill="x", pady=(0, 14))

        actions = tk.Frame(hero, bg=C["surface"])
        actions.pack(fill="x", pady=(16, 0))
        self.btn_main = tk.Button(actions, text="Iniciar automacao", command=self._toggle_run, bg=C["accent"], fg=C["bg"], activebackground=C["success"], activeforeground=C["bg"], relief="flat", bd=0, cursor="hand2", padx=18, pady=12, font=FONT_SUBTITLE)
        self.btn_main.pack(side="left")
        tk.Button(actions, text="Atualizar dispositivos", command=self._refresh_devs, bg=C["surface_soft"], fg=C["text"], activebackground=C["surface_alt"], activeforeground=C["text"], relief="flat", bd=0, cursor="hand2", padx=16, pady=12, font=FONT_BODY).pack(side="left", padx=10)
        tk.Checkbutton(actions, text="Modo ultra-eco", variable=self.ultra_eco, bg=C["surface"], fg=C["success"], activebackground=C["surface"], activeforeground=C["success"], selectcolor=C["surface"], cursor="hand2", font=FONT_BODY, bd=0).pack(side="right")

        devices_card = self._make_card(frame, "Instancias selecionadas", "Marque quais dispositivos entram na rodada atual.")
        devices_card.pack(fill="x", pady=(0, 14))
        self.device_list_frame = tk.Frame(devices_card, bg=C["surface"])
        self.device_list_frame.pack(fill="x", pady=(12, 0))

        metrics = tk.Frame(frame, bg=C["bg"])
        metrics.pack(fill="x", pady=(0, 14))
        metrics.grid_columnconfigure((0, 1), weight=1)
        self.lbl_cycles = self._build_metric_card(metrics, "Ciclos totais", "0", C["accent_alt"], 0, 0)
        self.lbl_profit = self._build_metric_card(metrics, "Pontos totais hoje", "+0", C["success"], 0, 1)
        self.lbl_time = self._build_metric_card(metrics, "Tempo de sessao", "00:00:00", C["warning"], 1, 0)
        self.lbl_profit_brl = self._build_metric_card(metrics, "Lucro em BRL", "R$ 0,00", C["accent"], 1, 1)

        self.status_badge = tk.Label(frame, text="Aguardando inicio", bg=C["surface_soft"], fg=C["text"], padx=12, pady=8, font=FONT_BODY)
        self.status_badge.pack(anchor="w", pady=(0, 14))

        activity = self._make_card(frame, "Ultimas atividades", "Eventos recentes de todas as instancias em uma unica linha do tempo.")
        activity.pack(fill="both", expand=True)
        self.mini_log = tk.Text(activity, height=8, state="disabled", bg=C["console"], fg=C["muted"], font=FONT_MONO, bd=0, padx=10, pady=10, insertbackground=C["text"])
        self.mini_log.pack(fill="both", expand=True, pady=(12, 0))
        return frame

    def _build_metric_card(self, parent, title, value, color, row, column):
        card = tk.Frame(parent, bg=C["surface"], padx=16, pady=16, highlightthickness=1, highlightbackground=C["border"])
        card.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
        tk.Label(card, text=title.upper(), font=FONT_TINY, bg=C["surface"], fg=C["muted"]).pack(anchor="w")
        label = tk.Label(card, text=value, font=("Bahnschrift", 24, "bold"), bg=C["surface"], fg=color)
        label.pack(anchor="w", pady=(8, 0))
        return label

    def _create_settings_view(self):
        frame = tk.Frame(self.content_frame, bg=C["bg"])
        frame.grid(row=0, column=0, sticky="nsew")

        connection = self._make_card(frame, "Conexao e dispositivo", "Atualize a lista local ou conecte um ADB remoto sem sair do painel.")
        connection.pack(fill="x", pady=(0, 14))
        tk.Label(connection, text="Dispositivo padrao", font=FONT_BODY, bg=C["surface"], fg=C["muted"]).pack(anchor="w", pady=(12, 6))

        combo_row = tk.Frame(connection, bg=C["surface"])
        combo_row.pack(fill="x")
        self.combo_dev = ttk.Combobox(combo_row, textvariable=self.selected_device, state="readonly", style="Spin.TCombobox")
        self.combo_dev.pack(side="left", fill="x", expand=True, ipady=5)
        tk.Button(combo_row, text="Atualizar", command=self._refresh_devs, bg=C["surface_soft"], fg=C["text"], relief="flat", bd=0, cursor="hand2", padx=12, pady=8, font=FONT_BODY).pack(side="left", padx=(8, 0))

        tk.Label(connection, text="ADB remoto (IP:porta)", font=FONT_BODY, bg=C["surface"], fg=C["muted"]).pack(anchor="w", pady=(14, 6))
        adb_row = tk.Frame(connection, bg=C["surface"])
        adb_row.pack(fill="x")
        tk.Entry(adb_row, textvariable=self.adb_ip, bg=C["surface_alt"], fg=C["text"], insertbackground=C["text"], relief="flat", bd=0, font=FONT_BODY).pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        tk.Button(adb_row, text="Conectar", command=self._connect_adb, bg=C["accent_alt"], fg=C["bg"], relief="flat", bd=0, cursor="hand2", padx=16, pady=8, font=FONT_BODY).pack(side="left")

        tools = self._make_card(frame, "Ferramentas avancadas", "Use a calibracao para ajustar leitura e clique em dispositivos com resolucoes diferentes.")
        tools.pack(fill="x")
        tk.Button(tools, text="Recalibrar tela", command=self._start_calib, bg=C["surface_soft"], fg=C["text"], relief="flat", bd=0, cursor="hand2", padx=16, pady=10, font=FONT_BODY).pack(anchor="w", pady=(12, 0))
        return frame

    def _create_console_view(self):
        frame = tk.Frame(self.content_frame, bg=C["bg"])
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        card = self._make_card(frame, "Console consolidado", "Logs completos das automacoes em execucao.")
        card.grid(row=0, column=0, sticky="nsew")
        self.txt_log = scrolledtext.ScrolledText(card, state="disabled", bg=C["console"], fg=C["muted"], font=FONT_MONO, bd=0, padx=12, pady=12, insertbackground=C["text"])
        self.txt_log.pack(fill="both", expand=True, pady=(12, 0))

        self.txt_log.tag_config("info", foreground=C["muted"])
        self.txt_log.tag_config("header", foreground=C["text"], font=("Consolas", 10, "bold"))
        self.txt_log.tag_config("success", foreground=C["success"])
        self.txt_log.tag_config("warning", foreground=C["warning"])
        self.txt_log.tag_config("error", foreground=C["danger"])
        self.txt_log.tag_config("action", foreground=C["accent_alt"])
        return frame

    def _create_predictions_view(self):
        frame = tk.Frame(self.content_frame, bg=C["bg"])
        frame.grid(row=0, column=0, sticky="nsew")

        card = self._make_card(frame, "Projecoes", "Estimativas dinamicas a partir do ritmo atual da sessao. Os valores estabilizam apos o primeiro minuto.")
        card.pack(fill="x")

        self.pred_labels = {}
        for period in ["1 Hora", "12 Horas", "1 Dia", "1 Semana", "1 Mes"]:
            row = tk.Frame(card, bg=C["surface_alt"], padx=14, pady=12, highlightthickness=1, highlightbackground=C["border"])
            row.pack(fill="x", pady=5)
            tk.Label(row, text=period, font=FONT_SUBTITLE, bg=C["surface_alt"], fg=C["text"]).pack(side="left")
            label = tk.Label(row, text="Calculando...", font=("Bahnschrift", 16, "bold"), bg=C["surface_alt"], fg=C["success"])
            label.pack(side="right")
            self.pred_labels[period] = label
        return frame

    def _create_reports_view(self):
        frame = tk.Frame(self.content_frame, bg=C["bg"])
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        card = self._make_card(frame, "Relatorios diarios", "Resumo persistido por conta com total agregado do dia.")
        card.grid(row=0, column=0, sticky="nsew")
        self.reports_text = tk.Text(card, bg=C["console"], fg=C["muted"], font=("Consolas", 10), bd=0, padx=12, pady=12, insertbackground=C["text"])
        self.reports_text.pack(fill="both", expand=True, pady=(12, 10))
        tk.Button(card, text="Atualizar relatorio", command=self._update_reports_text, bg=C["accent"], fg=C["bg"], relief="flat", bd=0, cursor="hand2", padx=16, pady=10, font=FONT_BODY).pack(anchor="w")
        return frame

    def _show_view(self, view_name):
        for key, btn in self.nav_btns.items():
            if key == view_name:
                btn.configure(bg=C["surface"], fg=C["text"])
            else:
                btn.configure(bg=C["panel"], fg=C["muted"])
        self.views[view_name].tkraise()
        if view_name == "reports" and self.reports_dirty:
            self._update_reports_text()

    def log(self, msg, level="info"):
        self.log_queue.put((msg, level))

    def _poll_logs(self):
        while not self.log_queue.empty():
            msg, level = self.log_queue.get()

            if hasattr(self, "txt_log"):
                self.txt_log.config(state="normal")
                max_lines = getattr(config, "MAX_LOG_LINES", 500)
                num_lines = int(self.txt_log.index("end-1c").split(".")[0])
                if num_lines > max_lines:
                    self.txt_log.delete("1.0", f"{num_lines - max_lines + 1}.0")
                self.txt_log.insert("end", f"[{datetime.now():%H:%M}] ", "info")
                self.txt_log.insert("end", f"{msg}\n", level)
                self.txt_log.see("end")
                self.txt_log.config(state="disabled")

            if hasattr(self, "mini_log"):
                self.mini_log.config(state="normal")
                num_lines = int(self.mini_log.index("end-1c").split(".")[0])
                if num_lines > 20:
                    self.mini_log.delete("1.0", "2.0")
                self.mini_log.insert("end", f"[{datetime.now():%H:%M}] {msg}\n")
                self.mini_log.see("end")
                self.mini_log.config(state="disabled")

        self.root.after(100, self._poll_logs)

    def _tick(self):
        if self.is_running and self.session_start:
            elapsed = str(datetime.now() - self.session_start).split(".")[0]
            self.lbl_time.config(text=elapsed)
            self._update_predictions(self.last_profit, elapsed)
        self.summary_cards["emails"].config(text=str(len(self._get_emails())))
        self.root.after(1000, self._tick)

    def _toggle_run(self):
        if self.is_running:
            self._stop()
        else:
            self._start()

    def _get_emails(self):
        raw = self.txt_emails.get("1.0", tk.END).strip()
        return [email.strip() for email in raw.splitlines() if email.strip()]

    def _start(self):
        selected_serials = [serial for serial, var in self.device_vars.items() if var.get()]
        if not selected_serials:
            messagebox.showwarning("Aviso", "Selecione pelo menos uma instancia para iniciar.")
            return

        emails = self._get_emails()
        if not emails:
            messagebox.showwarning("Aviso", "Informe pelo menos um email na barra lateral.")
            return

        try:
            devices = [device for device in adbutils.adb.device_list() if device.serial in selected_serials]
        except Exception as exc:
            messagebox.showerror("Erro ADB", f"Falha ao listar dispositivos: {exc}")
            return

        if len(emails) < len(devices):
            messagebox.showwarning("Faltam emails", f"Foram selecionados {len(devices)} dispositivos, mas existem apenas {len(emails)} emails preenchidos.")
            return

        self.is_running = True
        self.session_start = datetime.now()
        self.stop_event.clear()
        self.instance_stats = {}
        self.instances = []

        self.btn_main.configure(text="Parar automacao", bg=C["danger"], fg=C["text"], activebackground="#ff8585")
        self.status_badge.config(text=f"{len(devices)} instancia(s) em execucao", bg=C["accent_soft"], fg=C["text"])
        self.log(f"Iniciando lote com {len(devices)} dispositivo(s).", "header")

        for index, device in enumerate(devices):
            serial = device.serial
            model = device.prop.get("ro.product.model", "Desconhecido")
            email = emails[index]

            window = AutomatorWindow(self.root, serial, model, email, self.stop_event)
            window.geometry(f"+{70 + (index * 34)}+{70 + (index * 34)}")
            self.instances.append(window)

            self.log(f"[{serial}] Instancia criada para {email}", "action")
            threading.Thread(target=self._run_instance, args=(serial, email, window), daemon=True).start()

    def _stop(self):
        if not self.is_running:
            return
        self.stop_event.set()
        self.status_badge.config(text="Encerrando instancias...", bg=C["warning"], fg=C["bg"])
        self.log("Solicitando parada de todas as instancias...", "warning")

    def _run_instance(self, serial, email, window):
        def _multi_log(msg, level="info"):
            window.log(msg, level)
            self.log(f"[{serial}] {msg}", level)

        def _on_stats(stats):
            window.update_stats(stats)
            self._store_instance_stats(serial, stats)

        automator = SpinAutomator(serial=serial, account_email=email, stop_event=self.stop_event, on_log=_multi_log, on_stats_update=_on_stats)

        if self.ultra_eco.get():
            from adb_utils import apply_headless_optimizations
            import uiautomator2 as u2

            try:
                apply_headless_optimizations(u2.connect(serial))
            except Exception as exc:
                self.log(f"[{serial}] Falha ao aplicar ultra-eco: {exc}", "warning")

        try:
            automator.run()
        except Exception as exc:
            window.log(f"Erro critico na instancia: {exc}", "error")
            self.log(f"[{serial}] Erro critico na instancia: {exc}", "error")
        finally:
            if self.ultra_eco.get():
                from adb_utils import restore_display_defaults
                import uiautomator2 as u2

                try:
                    restore_display_defaults(u2.connect(serial))
                except Exception as exc:
                    self.log(f"[{serial}] Falha ao restaurar display: {exc}", "warning")

            self.root.after(0, lambda: self._on_instance_finish(window, serial))

    def _store_instance_stats(self, serial, stats):
        self.instance_stats[serial] = stats
        self.root.after(0, self._update_aggregate_stats)

    def _update_aggregate_stats(self):
        cycles = sum(item.get("cycles", 0) for item in self.instance_stats.values())
        profit = sum(item.get("profit", 0) for item in self.instance_stats.values())

        self.last_profit = profit
        self.lbl_cycles.config(text=str(cycles))
        self.lbl_profit.config(text=f"+{profit:,}".replace(",", "."))

        brl_val = CryptoConverter.coins_to_brl(profit)
        self.lbl_profit_brl.config(text=f"R$ {brl_val:,.4f}".replace(",", "X").replace(".", ",").replace("X", "."))

        if self.is_running:
            device_count = len([window for window in self.instances if window.is_active])
            self.status_badge.config(text=f"{device_count} instancia(s) em execucao", bg=C["accent_soft"], fg=C["text"])

        self.root.title(f"SpinBot v{APP_VERSION} | {cycles} ciclos | +{profit:,}".replace(",", "."))

    def _on_instance_finish(self, window, serial):
        window.on_finish()
        self.instance_stats.pop(serial, None)
        self._update_aggregate_stats()
        if all(not item.is_active for item in self.instances):
            self._on_all_finish()

    def _on_all_finish(self):
        self.is_running = False
        self.btn_main.configure(text="Iniciar automacao", bg=C["accent"], fg=C["bg"], activebackground=C["success"])
        self.status_badge.config(text="Processo finalizado", bg=C["surface_soft"], fg=C["text"])
        self.log("Todas as instancias foram finalizadas.", "header")
        self.reports_dirty = True

    def _refresh_devs(self):
        try:
            devices = adbutils.adb.device_list()
        except Exception as exc:
            self.log(f"Falha ao atualizar dispositivos: {exc}", "error")
            devices = []

        if hasattr(self, "device_list_frame"):
            for child in self.device_list_frame.winfo_children():
                child.destroy()

        combo_values = []
        self.summary_cards["devices"].config(text=str(len(devices)))

        if not devices and hasattr(self, "device_list_frame"):
            tk.Label(self.device_list_frame, text="Nenhum dispositivo detectado. Verifique o ADB.", bg=C["surface"], fg=C["danger"], font=FONT_BODY).pack(anchor="w")

        for index, device in enumerate(devices, start=1):
            serial = device.serial
            model = device.prop.get("ro.product.model", "Desconhecido")
            combo_values.append(f"{index}. {serial} | {model}")

            if serial not in self.device_vars:
                self.device_vars[serial] = tk.BooleanVar(value=True)

            if hasattr(self, "device_list_frame"):
                item = tk.Frame(self.device_list_frame, bg=C["surface_alt"], padx=12, pady=10, highlightthickness=1, highlightbackground=C["border"])
                item.pack(fill="x", pady=4)
                tk.Checkbutton(item, text=model, variable=self.device_vars[serial], bg=C["surface_alt"], fg=C["text"], activebackground=C["surface_alt"], activeforeground=C["text"], selectcolor=C["surface_alt"], cursor="hand2", bd=0, font=FONT_SUBTITLE).pack(anchor="w")
                tk.Label(item, text=serial, font=FONT_TINY, bg=C["surface_alt"], fg=C["muted"]).pack(anchor="w", pady=(2, 0))
                tk.Label(item, text="Online", font=FONT_TINY, bg=C["surface_alt"], fg=C["success"]).pack(anchor="e")

        if hasattr(self, "combo_dev"):
            self.combo_dev["values"] = combo_values
            if combo_values:
                self.combo_dev.current(0)

    def _connect_adb(self):
        address = self.adb_ip.get().strip()
        if not address:
            return
        try:
            self.log(f"Conectando a {address}...", "action")
            result = adbutils.adb.connect(address)
            self.log(f"Resultado do ADB: {result}", "info")
            self._refresh_devs()
        except Exception as exc:
            self.log(str(exc), "error")

    def _start_calib(self):
        device_desc = self.selected_device.get().strip()
        if not device_desc:
            messagebox.showwarning("Erro", "Selecione um dispositivo nas configuracoes.")
            return

        try:
            if ". " in device_desc:
                serial = device_desc.split(". ", 1)[1].split(" | ", 1)[0]
            else:
                serial = device_desc.split(" | ", 1)[0]
        except Exception:
            serial = device_desc

        def _calibrate():
            self.log(f"[{serial}] Iniciando calibracao...", "action")
            try:
                import uiautomator2 as u2

                if calibrate_device(u2.connect(serial), serial):
                    self.log(f"[{serial}] Calibracao concluida com sucesso.", "success")
                else:
                    self.log(f"[{serial}] Calibracao nao concluida.", "warning")
            except Exception as exc:
                self.log(f"[{serial}] Erro na calibracao: {exc}", "error")

        threading.Thread(target=_calibrate, daemon=True).start()

    def _update_predictions(self, profit, elapsed_str):
        try:
            hours, minutes, seconds = map(int, elapsed_str.split(":"))
            total_seconds = (hours * 3600) + (minutes * 60) + seconds
            if total_seconds < 60:
                return

            rate = profit / total_seconds
            periods = {
                "1 Hora": 3600,
                "12 Horas": 43200,
                "1 Dia": 86400,
                "1 Semana": 604800,
                "1 Mes": 2592000,
            }
            for label, duration in periods.items():
                projected = int(rate * duration)
                self.pred_labels[label].config(text=f"+{projected:,}".replace(",", "."))
        except Exception:
            return

    def _update_reports_text(self):
        stats = manager.get_all_stats()
        total = sum(stats.values())

        self.reports_text.config(state="normal")
        self.reports_text.delete("1.0", tk.END)
        self.reports_text.insert("end", f"Relatorio do dia {manager.data['last_reset']}\n")
        self.reports_text.insert("end", "=" * 42 + "\n\n")
        if not stats:
            self.reports_text.insert("end", "Nenhum dado registrado hoje.\n")
        else:
            for email, profit in stats.items():
                self.reports_text.insert("end", f"Conta : {email}\n")
                self.reports_text.insert("end", f"Pontos: +{profit:,}\n\n".replace(",", "."))

        self.reports_text.insert("end", "-" * 42 + "\n")
        self.reports_text.insert("end", f"TOTAL: +{total:,}\n".replace(",", "."))
        self.reports_text.config(state="disabled")
        self.reports_dirty = False


if __name__ == "__main__":
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    app = SpinGUI(root)
    root.mainloop()
