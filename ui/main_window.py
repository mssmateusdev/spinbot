import os
import sys
import threading
from datetime import datetime

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import config
from automation.orchestrator import BatchOrchestrator, OrchestratorCallbacks
from core.metrics import parse_elapsed, project_profit
from crypto_utils import CryptoConverter
from devices.manager import DeviceManager
from device_profiles import calibrate_device
from models.automation import InstanceConfig
from services.paths import resource_path
from stats_manager import manager


APP_VERSION = getattr(config, "APP_VERSION", "0.6.4")


C = {
    "bg": "#141922",
    "bg_alt": "#1a202b",
    "panel": "#10151d",
    "surface": "#1c2330",
    "surface_alt": "#242d3c",
    "surface_soft": "#2f3b50",
    "console": "#0f141c",
    "text": "#eff4ff",
    "muted": "#95a3bc",
    "accent": "#5f8fff",
    "accent_2": "#7d63ff",
    "success": "#2fd18f",
    "warning": "#ffcb66",
    "danger": "#ff7a7a",
    "border": "#313b4f",
}

LEVEL_COLORS = {
    "info": C["muted"],
    "success": C["success"],
    "warning": C["warning"],
    "error": C["danger"],
    "action": C["accent"],
    "header": C["text"],
}

NAV_ITEMS = [
    ("welcome", "01", "Inicio"),
    ("home", "02", "Dashboard"),
    ("predictions", "03", "Projecoes"),
    ("reports", "04", "Relatorios"),
    ("settings", "05", "Configuracoes"),
    ("console", "06", "Console"),
]


class UiBus(QObject):
    global_log = Signal(str, str)
    instance_log = Signal(str, str, str)
    instance_stats = Signal(str, dict)
    instance_finished = Signal(str)


class StatCard(QFrame):
    def __init__(self, title, value="0", color=C["accent"]):
        super().__init__()
        self.setObjectName("StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        title_label = QLabel(title.upper())
        title_label.setObjectName("CardCaption")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.value_label.setStyleSheet(f"color: {color};")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(value)


class NavButton(QPushButton):
    def __init__(self, index_text, text):
        super().__init__(f"{index_text}  {text}")
        self.setCheckable(True)
        self.setObjectName("NavButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)


class DeviceCard(QFrame):
    def __init__(self, serial, model, checked=True):
        super().__init__()
        self.checkbox = QCheckBox(model)
        self.checkbox.setChecked(checked)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.setObjectName("DeviceCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.checkbox)
        top.addStretch()
        online = QLabel("Online")
        online.setObjectName("OnlineLabel")
        top.addWidget(online)

        serial_label = QLabel(serial)
        serial_label.setObjectName("DimLabel")

        layout.addLayout(top)
        layout.addWidget(serial_label)

    def is_checked(self):
        return self.checkbox.isChecked()


class InstanceWindow(QMainWindow):
    def __init__(self, serial, model, email):
        super().__init__()
        self.serial = serial
        self.model = model
        self.email = email
        self.is_active = True

        self.setWindowTitle(model)
        self.resize(400, 520)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("Card")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 14)
        header_layout.setSpacing(4)
        header_layout.addWidget(self._label(model, "Title"))
        header_layout.addWidget(self._label(email, "AccentLabel"))
        header_layout.addWidget(self._label(serial, "DimLabel"))

        stats_wrap = QWidget()
        stats = QGridLayout(stats_wrap)
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setHorizontalSpacing(8)
        stats.setVerticalSpacing(8)
        self.cycles_card = StatCard("Ciclos", "0", C["accent"])
        self.profit_card = StatCard("Pontos Hoje", "+0", C["success"])
        self.time_card = StatCard("Tempo", "00:00:00", C["warning"])
        self.brl_card = StatCard("Lucro BRL", "R$ 0,00", C["accent_2"])
        stats.addWidget(self.cycles_card, 0, 0)
        stats.addWidget(self.profit_card, 0, 1)
        stats.addWidget(self.time_card, 1, 0)
        stats.addWidget(self.brl_card, 1, 1)

        self.status_label = self._label("Status: iniciando...", "WarnLabel")
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setObjectName("Console")

        root.addWidget(header)
        root.addWidget(stats_wrap)
        root.addWidget(self.status_label)
        root.addWidget(self.console, 1)

    def _label(self, text, object_name):
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    def log(self, msg, level="info"):
        self.console.append(f"[{datetime.now():%H:%M}] {msg}")
        self.console.moveCursor(QTextCursor.End)

    def update_stats(self, stats):
        profit = stats.get("profit", 0)
        brl = CryptoConverter.coins_to_brl(profit)
        self.cycles_card.set_value(str(stats.get("cycles", 0)))
        self.profit_card.set_value(f"+{profit:,}".replace(",", "."))
        self.time_card.set_value(stats.get("elapsed", "00:00:00"))
        self.brl_card.set_value(f"R$ {brl:,.4f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.status_label.setText("Status: ativo")
        self.status_label.setStyleSheet(f"color: {C['success']}; font-weight: 700;")

    def on_finish(self):
        self.is_active = False
        self.status_label.setText("Status: finalizado")
        self.status_label.setStyleSheet(f"color: {C['danger']}; font-weight: 700;")


class SpinGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bus = UiBus()
        self.device_manager = DeviceManager()
        self.orchestrator = BatchOrchestrator(
            OrchestratorCallbacks(
                on_log=self.bus.instance_log.emit,
                on_stats=self.bus.instance_stats.emit,
                on_finished=self.bus.instance_finished.emit,
            )
        )
        self.selected_device_value = ""
        self.is_running = False
        self.session_start = None
        self.last_profit = 0
        self.instance_stats = {}
        self.instance_windows = {}
        self.device_cards = {}
        self.reports_dirty = True

        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._refresh_devs()

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._tick)
        self.tick_timer.start(1000)

    def _setup_window(self):
        self.setWindowTitle(f"SpinBot v{APP_VERSION}")
        self.resize(1220, 760)
        self.setMinimumSize(QSize(980, 640))
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)

        content_shell = QWidget()
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(14, 14, 14, 14)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        root.addWidget(content_shell, 1)

        self.pages = {}
        self._build_welcome_page()
        self._build_home_page()
        self._build_predictions_page()
        self._build_reports_page()
        self._build_settings_page()
        self._build_console_page()
        self._show_page("welcome")
        self._apply_styles()

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(252)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        brand = self._card("BrandCard")
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(16, 16, 16, 16)
        brand_layout.setSpacing(6)
        brand_layout.addWidget(self._make_label("SpinBot", "HeroTitle"))
        brand_layout.addWidget(self._make_label("Painel moderno, compacto e pronto para automacao em lote.", "DimLabel"))
        layout.addWidget(brand)

        stats_row = QWidget()
        stats = QGridLayout(stats_row)
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setHorizontalSpacing(6)
        self.devices_summary = StatCard("Dispositivos", "0", C["accent"])
        self.emails_summary = StatCard("Emails", "0", C["accent_2"])
        stats.addWidget(self.devices_summary, 0, 0)
        stats.addWidget(self.emails_summary, 0, 1)
        layout.addWidget(stats_row)

        nav_card = self._card()
        nav_layout = QVBoxLayout(nav_card)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(4)
        self.nav_buttons = {}
        for key, index_text, text in NAV_ITEMS:
            button = NavButton(index_text, text)
            button.clicked.connect(lambda checked=False, item=key: self._show_page(item))
            nav_layout.addWidget(button)
            self.nav_buttons[key] = button
        layout.addWidget(nav_card)

        emails_card = self._card()
        emails_layout = QVBoxLayout(emails_card)
        emails_layout.setContentsMargins(12, 12, 12, 12)
        emails_layout.setSpacing(8)
        emails_layout.addWidget(self._make_label("Emails", "SectionTitle"))
        emails_layout.addWidget(self._make_label("Um por linha para distribuir entre as instancias selecionadas.", "DimLabel"))
        self.txt_emails = QPlainTextEdit()
        self.txt_emails.setPlaceholderText("email1@dominio.com\nemail2@dominio.com")
        self.txt_emails.setObjectName("InputArea")
        previous_emails = list(manager.get_all_stats().keys())
        if previous_emails:
            self.txt_emails.setPlainText("\n".join(previous_emails))
        self.txt_emails.textChanged.connect(self._update_email_counter)
        emails_layout.addWidget(self.txt_emails, 1)
        layout.addWidget(emails_card, 1)

        footer = self._make_label(f"SpinBot v{APP_VERSION}", "DimLabel")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)
        return sidebar

    def _build_welcome_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch()

        card = self._card("WelcomeCard")
        card.setMaximumWidth(560)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 34, 34, 34)
        card_layout.setSpacing(16)
        title = self._make_label("SpinBot", "WelcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = self._make_label("Tela inicial de acesso ao painel. Clique no botao abaixo para abrir o programa.", "WelcomeSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        open_button = self._button("Abrir Programa", primary=True)
        open_button.setMinimumHeight(48)
        open_button.clicked.connect(lambda: self._show_page("home"))

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(8)
        card_layout.addWidget(open_button, 0, Qt.AlignCenter)

        outer.addWidget(card, 0, Qt.AlignCenter)
        outer.addStretch()
        self.stack.addWidget(page)
        self.pages["welcome"] = page

    def _build_home_page(self):
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 4)
        grid.setRowStretch(2, 1)

        hero = self._card()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(14, 14, 14, 14)
        hero_layout.setSpacing(10)
        hero_layout.addWidget(self._make_label("Operacao Central", "SectionTitle"))
        hero_layout.addWidget(self._make_label("Controle o lote atual, acompanhe o progresso e distribua a automacao entre varias instancias.", "DimLabel"))

        actions = QHBoxLayout()
        self.start_button = self._button("Iniciar", primary=True)
        self.start_button.clicked.connect(self._toggle_run)
        refresh_button = self._button("Atualizar")
        refresh_button.clicked.connect(self._refresh_devs)
        self.ultra_eco_checkbox = QCheckBox("Ultra-eco")
        self.ultra_eco_checkbox.setCursor(Qt.PointingHandCursor)
        actions.addWidget(self.start_button)
        actions.addWidget(refresh_button)
        actions.addStretch()
        actions.addWidget(self.ultra_eco_checkbox)
        hero_layout.addLayout(actions)

        self.status_badge = QLabel("Aguardando inicio")
        self.status_badge.setObjectName("StatusBadge")
        hero_layout.addWidget(self.status_badge, 0, Qt.AlignLeft)
        grid.addWidget(hero, 0, 0)

        metrics_wrap = QWidget()
        metrics = QGridLayout(metrics_wrap)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(8)
        metrics.setVerticalSpacing(8)
        self.total_cycles_card = StatCard("Ciclos", "0", C["accent"])
        self.total_profit_card = StatCard("Pontos Hoje", "+0", C["success"])
        self.total_time_card = StatCard("Tempo", "00:00:00", C["warning"])
        self.total_brl_card = StatCard("Lucro BRL", "R$ 0,00", C["accent_2"])
        metrics.addWidget(self.total_cycles_card, 0, 0)
        metrics.addWidget(self.total_profit_card, 0, 1)
        metrics.addWidget(self.total_time_card, 1, 0)
        metrics.addWidget(self.total_brl_card, 1, 1)
        grid.addWidget(metrics_wrap, 1, 0)

        activity = self._card()
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(14, 14, 14, 14)
        activity_layout.addWidget(self._make_label("Atividades", "SectionTitle"))
        self.mini_log = QTextEdit()
        self.mini_log.setReadOnly(True)
        self.mini_log.setObjectName("Console")
        activity_layout.addWidget(self.mini_log, 1)
        grid.addWidget(activity, 2, 0)

        instances = self._card()
        instances_layout = QVBoxLayout(instances)
        instances_layout.setContentsMargins(14, 14, 14, 14)
        instances_layout.addWidget(self._make_label("Instancias", "SectionTitle"))
        instances_layout.addWidget(self._make_label("Lista compacta com rolagem para acomodar diferentes resolucoes.", "DimLabel"))
        self.device_scroll = QScrollArea()
        self.device_scroll.setWidgetResizable(True)
        self.device_scroll.setObjectName("ScrollArea")
        self.device_list_widget = QWidget()
        self.device_list_layout = QVBoxLayout(self.device_list_widget)
        self.device_list_layout.setContentsMargins(0, 0, 0, 0)
        self.device_list_layout.setSpacing(8)
        self.device_list_layout.addStretch()
        self.device_scroll.setWidget(self.device_list_widget)
        instances_layout.addWidget(self.device_scroll, 1)
        grid.addWidget(instances, 0, 1, 3, 1)

        self.stack.addWidget(page)
        self.pages["home"] = page

    def _build_predictions_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.addWidget(self._make_label("Projecoes", "SectionTitle"))
        card_layout.addWidget(self._make_label("Estimativas baseadas no ritmo atual da sessao.", "DimLabel"))
        self.prediction_labels = {}
        for label_text in ["1 Hora", "12 Horas", "1 Dia", "1 Semana", "1 Mes"]:
            row = self._card("InnerCard")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.addWidget(self._make_label(label_text, "BodyLabel"))
            row_layout.addStretch()
            value = self._make_label("Calculando...", "AccentLabel")
            self.prediction_labels[label_text] = value
            row_layout.addWidget(value)
            card_layout.addWidget(row)
        layout.addWidget(card)
        self.stack.addWidget(page)
        self.pages["predictions"] = page

    def _build_reports_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.addWidget(self._make_label("Relatorios Diarios", "SectionTitle"))
        card_layout.addWidget(self._make_label("Resumo persistido por conta e total agregado do dia.", "DimLabel"))
        self.reports_text = QPlainTextEdit()
        self.reports_text.setReadOnly(True)
        self.reports_text.setObjectName("Console")
        refresh_button = self._button("Atualizar Relatorio")
        refresh_button.clicked.connect(self._update_reports_text)
        card_layout.addWidget(self.reports_text, 1)
        card_layout.addWidget(refresh_button, 0, Qt.AlignLeft)
        layout.addWidget(card)
        self.stack.addWidget(page)
        self.pages["reports"] = page

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        connection = self._card()
        connection_layout = QVBoxLayout(connection)
        connection_layout.setContentsMargins(14, 14, 14, 14)
        connection_layout.addWidget(self._make_label("Conexao e Dispositivo", "SectionTitle"))
        connection_layout.addWidget(self._make_label("Atualize a lista local ou conecte um ADB remoto sem sair do painel.", "DimLabel"))
        connection_layout.addWidget(self._make_label("Dispositivo padrao", "BodyLabel"))

        combo_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.currentTextChanged.connect(self._on_device_combo_changed)
        combo_row.addWidget(self.device_combo, 1)
        refresh_button = self._button("Atualizar")
        refresh_button.clicked.connect(self._refresh_devs)
        combo_row.addWidget(refresh_button)
        connection_layout.addLayout(combo_row)

        connection_layout.addWidget(self._make_label("ADB remoto (IP:porta)", "BodyLabel"))
        adb_row = QHBoxLayout()
        self.adb_input = QLineEdit("127.0.0.1:5555")
        self.adb_input.setObjectName("LineInput")
        adb_row.addWidget(self.adb_input, 1)
        connect_button = self._button("Conectar", primary=True)
        connect_button.clicked.connect(self._connect_adb)
        adb_row.addWidget(connect_button)
        connection_layout.addLayout(adb_row)

        tools = self._card()
        tools_layout = QVBoxLayout(tools)
        tools_layout.setContentsMargins(14, 14, 14, 14)
        tools_layout.addWidget(self._make_label("Ferramentas Avancadas", "SectionTitle"))
        tools_layout.addWidget(self._make_label("Use a calibracao para ajustar leitura e clique em dispositivos com resolucoes diferentes.", "DimLabel"))
        calibrate_button = self._button("Recalibrar Tela")
        calibrate_button.clicked.connect(self._start_calib)
        tools_layout.addWidget(calibrate_button, 0, Qt.AlignLeft)

        layout.addWidget(connection)
        layout.addWidget(tools)
        layout.addStretch()
        self.stack.addWidget(page)
        self.pages["settings"] = page

    def _build_console_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.addWidget(self._make_label("Console Consolidado", "SectionTitle"))
        card_layout.addWidget(self._make_label("Logs completos das automacoes em execucao.", "DimLabel"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setObjectName("Console")
        card_layout.addWidget(self.txt_log, 1)
        layout.addWidget(card)
        self.stack.addWidget(page)
        self.pages["console"] = page

    def _connect_signals(self):
        self.bus.global_log.connect(self._append_global_log)
        self.bus.instance_log.connect(self._append_instance_log)
        self.bus.instance_stats.connect(self._store_instance_stats)
        self.bus.instance_finished.connect(self._on_instance_finish)

    def _apply_styles(self):
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {C['bg']};
            }}
            QWidget {{
                background: transparent;
                color: {C['text']};
                font-family: 'Segoe UI';
                font-size: 12px;
            }}
            #Sidebar {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {C['panel']}, stop:1 {C['bg_alt']});
                border-right: 1px solid {C['border']};
            }}
            #Card, #BrandCard, #StatCard, #DeviceCard, #InnerCard, #WelcomeCard {{
                background: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 14px;
            }}
            #InnerCard {{
                background: {C['surface_alt']};
            }}
            #WelcomeCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['surface']}, stop:1 {C['surface_alt']});
            }}
            QLabel, QCheckBox {{
                background: transparent;
                border: none;
            }}
            QStackedWidget, QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            #NavButton {{
                text-align: left;
                padding: 9px 12px;
                border: 0;
                border-radius: 10px;
                background: {C['surface']};
                color: {C['muted']};
                font-weight: 700;
            }}
            #NavButton:checked {{
                background: {C['surface_soft']};
                color: {C['text']};
            }}
            QLabel#HeroTitle {{ font-size: 28px; font-weight: 800; color: {C['text']}; }}
            QLabel#WelcomeTitle {{ font-size: 42px; font-weight: 800; color: {C['text']}; }}
            QLabel#WelcomeSubtitle {{ font-size: 14px; color: {C['muted']}; }}
            QLabel#SectionTitle {{ font-size: 20px; font-weight: 800; }}
            QLabel#Title {{ font-size: 18px; font-weight: 800; }}
            QLabel#StatValue {{ font-size: 28px; font-weight: 800; }}
            QLabel#CardCaption, QLabel#DimLabel {{ color: {C['muted']}; }}
            QLabel#BodyLabel {{ color: {C['text']}; font-weight: 700; }}
            QLabel#AccentLabel {{ color: {C['accent']}; font-weight: 800; }}
            QLabel#WarnLabel {{ color: {C['warning']}; font-weight: 800; }}
            QLabel#OnlineLabel {{ color: {C['success']}; font-size: 11px; font-weight: 700; }}
            QLabel#StatusBadge {{ background: {C['surface_soft']}; border-radius: 11px; padding: 7px 12px; }}
            QPushButton {{ background: {C['surface_soft']}; color: {C['text']}; border: 0; border-radius: 10px; padding: 10px 14px; font-weight: 800; }}
            QPushButton:hover {{ background: #3a4962; }}
            QLineEdit#LineInput, QPlainTextEdit#InputArea, QPlainTextEdit#Console, QTextEdit#Console, QComboBox {{
                background: {C['surface_alt']};
                border: 1px solid {C['border']};
                border-radius: 10px;
                padding: 8px;
                color: {C['text']};
            }}
            QComboBox {{
                min-height: 18px;
                padding-right: 30px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                background: {C['surface_soft']};
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {C['text']};
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {C['surface']};
                color: {C['text']};
                border: 1px solid {C['border']};
                outline: 0;
                selection-background-color: {C['surface_soft']};
                selection-color: {C['text']};
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 28px;
                padding: 6px 10px;
                background: transparent;
                color: {C['text']};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: {C['surface_soft']};
                color: {C['text']};
            }}
            QTextEdit#Console, QPlainTextEdit#Console {{
                background: {C['bg_alt']};
            }}
            QFrame {{
                background: transparent;
            }}
            QScrollArea#ScrollArea {{ border: 0; background: transparent; }}
            QScrollBar:vertical {{ background: {C['panel']}; width: 10px; border-radius: 5px; }}
            QScrollBar::handle:vertical {{ background: {C['surface_soft']}; min-height: 24px; border-radius: 5px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QCheckBox {{ spacing: 8px; font-weight: 700; }}
            """
        )

    def _card(self, object_name="Card"):
        card = QFrame()
        card.setObjectName(object_name)
        return card

    def _make_label(self, text, object_name):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName(object_name)
        return label

    def _button(self, text, primary=False):
        button = QPushButton(text)
        if primary:
            button.setStyleSheet(
                f"QPushButton {{background: {C['accent']}; color: {C['text']}; border-radius: 10px; padding: 10px 14px; font-weight: 800;}}"
                f"QPushButton:hover {{background: #7fa7ff;}}"
            )
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _show_page(self, key):
        for nav_key, button in self.nav_buttons.items():
            button.setChecked(nav_key == key)
        self.stack.setCurrentWidget(self.pages[key])
        if key == "reports" and self.reports_dirty:
            self._update_reports_text()

    def _update_email_counter(self):
        self.emails_summary.set_value(str(len(self._get_emails())))

    def _get_emails(self):
        return [line.strip() for line in self.txt_emails.toPlainText().splitlines() if line.strip()]

    def _on_device_combo_changed(self, value):
        self.selected_device_value = value

    def _append_global_log(self, msg, level="info"):
        timestamp = f"[{datetime.now():%H:%M}] "
        self.txt_log.append(f"{timestamp}{msg}")
        self.mini_log.append(f"{timestamp}{msg}")
        self._trim_console(self.txt_log, getattr(config, "MAX_LOG_LINES", 500))
        self._trim_console(self.mini_log, 20)

    def _append_instance_log(self, serial, msg, level="info"):
        window = self.instance_windows.get(serial)
        if window:
            window.log(msg, level)
        self.bus.global_log.emit(f"[{serial}] {msg}", level)

    def _trim_console(self, widget, max_lines):
        lines = widget.toPlainText().splitlines()
        if len(lines) > max_lines:
            widget.setPlainText("\n".join(lines[-max_lines:]))
            widget.moveCursor(QTextCursor.End)

    def _toggle_run(self):
        if self.is_running:
            self._stop()
        else:
            self._start()

    def _start(self):
        selected_serials = [serial for serial, card in self.device_cards.items() if card.is_checked()]
        if not selected_serials:
            QMessageBox.warning(self, "Aviso", "Selecione pelo menos uma instancia para iniciar.")
            return

        emails = self._get_emails()
        if not emails:
            QMessageBox.warning(self, "Aviso", "Informe pelo menos um email na barra lateral.")
            return

        try:
            devices = [device for device in self.device_manager.refresh() if device.serial in selected_serials]
        except Exception as exc:
            QMessageBox.critical(self, "Erro ADB", f"Falha ao listar dispositivos: {exc}")
            return

        if len(emails) < len(devices):
            QMessageBox.warning(self, "Faltam emails", f"Foram selecionados {len(devices)} dispositivos, mas existem apenas {len(emails)} emails preenchidos.")
            return

        configs = [
            InstanceConfig(serial=device.serial, model=device.model, email=emails[index])
            for index, device in enumerate(devices)
        ]

        self.is_running = True
        self.session_start = datetime.now()
        self.instance_stats = {}
        self.start_button.setText("Parar")
        self.start_button.setStyleSheet(
            f"QPushButton {{background: {C['danger']}; color: {C['text']}; border-radius: 10px; padding: 10px 14px; font-weight: 800;}}"
            f"QPushButton:hover {{background: #ff8c8c;}}"
        )
        self.status_badge.setText(f"{len(devices)} instancia(s) em execucao")
        self.bus.global_log.emit(f"Iniciando lote com {len(devices)} dispositivo(s).", "header")

        for index, config_item in enumerate(configs):
            serial = config_item.serial
            window = InstanceWindow(serial, config_item.model, config_item.email)
            window.move(70 + (index * 28), 70 + (index * 28))
            window.show()
            self.instance_windows[serial] = window

        try:
            self.orchestrator.start(configs, ultra_eco=self.ultra_eco_checkbox.isChecked())
        except Exception as exc:
            self.bus.global_log.emit(f"Falha ao iniciar orquestrador: {exc}", "error")
            self._on_all_finish()

    def _stop(self):
        if not self.is_running:
            return
        self.orchestrator.stop()
        self.status_badge.setText("Encerrando instancias...")
        self.bus.global_log.emit("Solicitando parada de todas as instancias...", "warning")

    def _store_instance_stats(self, serial, stats):
        self.instance_stats[serial] = stats
        window = self.instance_windows.get(serial)
        if window:
            window.update_stats(stats)
        self._update_aggregate_stats()

    def _update_aggregate_stats(self):
        cycles = sum(item.get("cycles", 0) for item in self.instance_stats.values())
        profit = sum(item.get("profit", 0) for item in self.instance_stats.values())
        self.last_profit = profit
        self.total_cycles_card.set_value(str(cycles))
        self.total_profit_card.set_value(f"+{profit:,}".replace(",", "."))
        brl = CryptoConverter.coins_to_brl(profit)
        self.total_brl_card.set_value(f"R$ {brl:,.4f}".replace(",", "X").replace(".", ",").replace("X", "."))
        if self.is_running:
            active_count = sum(1 for window in self.instance_windows.values() if window.is_active)
            self.status_badge.setText(f"{active_count} instancia(s) em execucao")
        self.setWindowTitle(f"SpinBot v{APP_VERSION} | {cycles} ciclos | +{profit:,}".replace(",", "."))

    def _on_instance_finish(self, serial):
        window = self.instance_windows.get(serial)
        if window:
            window.on_finish()
        if self.instance_windows and all(not item.is_active for item in self.instance_windows.values()):
            self._on_all_finish()

    def _on_all_finish(self):
        self.is_running = False
        self.start_button.setText("Iniciar")
        self.start_button.setStyleSheet(
            f"QPushButton {{background: {C['accent']}; color: {C['text']}; border-radius: 10px; padding: 10px 14px; font-weight: 800;}}"
            f"QPushButton:hover {{background: #7fa7ff;}}"
        )
        self.status_badge.setText("Processo finalizado")
        self.reports_dirty = True
        self.bus.global_log.emit("Todas as instancias foram finalizadas.", "header")

    def _refresh_devs(self):
        try:
            devices = self.device_manager.refresh()
        except Exception as exc:
            self.bus.global_log.emit(f"Falha ao atualizar dispositivos: {exc}", "error")
            devices = []

        self.devices_summary.set_value(str(len(devices)))

        while self.device_list_layout.count() > 1:
            item = self.device_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.device_cards = {}

        if not devices:
            empty = self._make_label("Nenhum dispositivo detectado. Verifique o ADB.", "WarnLabel")
            self.device_list_layout.insertWidget(0, empty)

        combo_values = []
        for device in devices:
            serial = device.serial
            model = device.model
            combo_values.append(f"{serial} | {model}")
            card = DeviceCard(serial, model, checked=True)
            self.device_cards[serial] = card
            self.device_list_layout.insertWidget(self.device_list_layout.count() - 1, card)

        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItems(combo_values)
        self.device_combo.blockSignals(False)
        if combo_values:
            self.selected_device_value = combo_values[0]
            self.device_combo.setCurrentIndex(0)

    def _connect_adb(self):
        address = self.adb_input.text().strip()
        if not address:
            return
        try:
            self.bus.global_log.emit(f"Conectando a {address}...", "action")
            result = self.device_manager.connect_remote(address)
            self.bus.global_log.emit(f"Resultado do ADB: {result}", "info")
            self._refresh_devs()
        except Exception as exc:
            self.bus.global_log.emit(str(exc), "error")

    def _start_calib(self):
        if not self.selected_device_value:
            QMessageBox.warning(self, "Erro", "Selecione um dispositivo nas configuracoes.")
            return
        serial = self.selected_device_value.split(" | ", 1)[0]

        def _calibrate():
            self.bus.global_log.emit(f"[{serial}] Iniciando calibracao...", "action")
            try:
                from adb_utils import connect_managed_device

                if calibrate_device(connect_managed_device(serial), serial):
                    self.bus.global_log.emit(f"[{serial}] Calibracao concluida com sucesso.", "success")
                else:
                    self.bus.global_log.emit(f"[{serial}] Calibracao nao concluida.", "warning")
            except Exception as exc:
                self.bus.global_log.emit(f"[{serial}] Erro na calibracao: {exc}", "error")

        threading.Thread(target=_calibrate, daemon=True).start()

    def _tick(self):
        if self.is_running and self.session_start:
            elapsed = str(datetime.now() - self.session_start).split(".")[0]
            self.total_time_card.set_value(elapsed)
            self._update_predictions(self.last_profit, elapsed)
        self._update_email_counter()

    def _update_predictions(self, profit, elapsed_str):
        try:
            total_seconds = parse_elapsed(elapsed_str)
            periods = {"1 Hora": 3600, "12 Horas": 43200, "1 Dia": 86400, "1 Semana": 604800, "1 Mes": 2592000}
            for label, duration in periods.items():
                value = project_profit(profit, total_seconds, duration)
                if value <= 0:
                    continue
                self.prediction_labels[label].setText(f"+{value:,}".replace(",", "."))
        except Exception:
            return

    def _update_reports_text(self):
        stats = manager.get_all_stats()
        total = sum(stats.values())
        lines = [f"Relatorio do dia {manager.data['last_reset']}", "=" * 42, ""]
        if not stats:
            lines.append("Nenhum dado registrado hoje.")
        else:
            for email, profit in stats.items():
                lines.append(f"Conta : {email}")
                lines.append(f"Pontos: +{profit:,}".replace(",", "."))
                lines.append("")
        lines.append("-" * 42)
        lines.append(f"TOTAL: +{total:,}".replace(",", "."))
        self.reports_text.setPlainText("\n".join(lines))
        self.reports_dirty = False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpinGUI()
    window.show()
    sys.exit(app.exec())
