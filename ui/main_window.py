import os
import sys
import threading
from html import escape
from datetime import datetime

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
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
from models.automation import InstanceConfig, InstanceStatus
from services.paths import resource_path
from stats_manager import manager


APP_VERSION = getattr(config, "APP_VERSION", "0.6.5")


C = {
    "bg": "#0d1015",
    "bg_alt": "#111720",
    "panel": "#10161f",
    "panel_alt": "#151d28",
    "surface": "#161d27",
    "surface_alt": "#1b2430",
    "surface_soft": "#263241",
    "surface_hover": "#2e3b4c",
    "console": "#0b0f14",
    "text": "#f3f7fb",
    "muted": "#99a7b7",
    "muted_2": "#6f7f91",
    "accent": "#60c8b7",
    "accent_hover": "#74d8c8",
    "points": "#9bb8ff",
    "profit": "#55d991",
    "warning": "#f4c95d",
    "danger": "#ff6f7d",
    "danger_hover": "#ff8793",
    "debug": "#a8b3c5",
    "border": "#2a3544",
    "border_soft": "#202936",
}

LEVEL_COLORS = {
    "info": C["muted"],
    "success": C["profit"],
    "warning": C["warning"],
    "error": C["danger"],
    "action": C["accent"],
    "debug": C["debug"],
    "header": C["text"],
}

NAV_ITEMS = [
    ("welcome", "IN", "Inicio"),
    ("home", "DB", "Dashboard"),
    ("predictions", "PR", "Projecoes"),
    ("reports", "RP", "Relatorios"),
    ("settings", "CF", "Configuracoes"),
    ("console", "LG", "Console"),
]

STATUS_STYLES = {
    "online": ("Online", C["accent"], "rgba(96, 200, 183, 0.14)"),
    "working": ("Trabalhando", C["profit"], "rgba(85, 217, 145, 0.16)"),
    "paused": ("Pausado", C["warning"], "rgba(244, 201, 93, 0.14)"),
    "error": ("Erro", C["danger"], "rgba(255, 111, 125, 0.15)"),
    "offline": ("Offline", C["muted_2"], "rgba(111, 127, 145, 0.13)"),
}


class UiBus(QObject):
    global_log = Signal(str, str)
    instance_log = Signal(str, str, str)
    instance_stats = Signal(str, dict)
    instance_finished = Signal(str)


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def add_shadow(widget, blur=18, offset=6, alpha=70):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, offset)
    shadow.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(shadow)


class StatCard(QFrame):
    def __init__(self, title, value="0", color=C["accent"], priority="low", hint=""):
        super().__init__()
        self.setObjectName("StatCard")
        self.setProperty("priority", priority)
        self._last_value = str(value)
        add_shadow(self, blur=16, offset=5, alpha=55)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        accent_line = QFrame()
        accent_line.setObjectName("KpiAccent")
        accent_line.setFixedHeight(3)
        accent_line.setStyleSheet(f"background: {color}; border-radius: 1px;")
        title_label = QLabel(title.upper())
        title_label.setObjectName("CardCaption")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.value_label.setStyleSheet(f"color: {color};")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("CardHint")
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(accent_line)
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.hint_label)

    def set_value(self, value):
        value = str(value)
        if value == self._last_value:
            return
        self._last_value = value
        self.value_label.setText(value)
        self.setProperty("pulse", "on")
        repolish(self)
        QTimer.singleShot(260, self._clear_pulse)

    def _clear_pulse(self):
        self.setProperty("pulse", "off")
        repolish(self)


class StatusChip(QWidget):
    def __init__(self, status="online"):
        super().__init__()
        self.setObjectName("StatusChip")
        self.dot = QLabel()
        self.dot.setObjectName("StatusDot")
        self.dot.setFixedSize(8, 8)
        self.label = QLabel()
        self.label.setObjectName("StatusText")
        self._pulse_on = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(720)
        self._pulse_timer.timeout.connect(self._toggle_pulse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 5, 9, 5)
        layout.setSpacing(7)
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.set_status(status)

    def set_status(self, status):
        self.status = status if status in STATUS_STYLES else "offline"
        text, color, bg = STATUS_STYLES[self.status]
        self.label.setText(text.upper())
        self.setStyleSheet(
            f"QWidget#StatusChip {{ background: {bg}; border: 1px solid {color}; border-radius: 8px; }}"
            f"QLabel#StatusText {{ color: {color}; font-size: 10px; font-weight: 800; letter-spacing: 0px; }}"
        )
        self._set_dot(color)
        if self.status == "working":
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
            self._pulse_on = False

    def _set_dot(self, color):
        self.dot.setStyleSheet(f"background: {color}; border-radius: 4px;")

    def _toggle_pulse(self):
        self._pulse_on = not self._pulse_on
        self._set_dot(C["accent"] if self._pulse_on else C["profit"])


class LogView(QTextEdit):
    LEVEL_LABELS = {
        "info": "INFO",
        "success": "SUCCESS",
        "warning": "WARNING",
        "error": "ERROR",
        "action": "ACTION",
        "debug": "DEBUG",
        "header": "EVENT",
    }

    def __init__(self, compact=False):
        super().__init__()
        self.compact = compact
        self.setReadOnly(True)
        self.setObjectName("Console")
        self.setAcceptRichText(True)

    def append_log(self, msg, level="info", source=None):
        level = (level or "info").lower()
        color = LEVEL_COLORS.get(level, C["muted"])
        label = self.LEVEL_LABELS.get(level, level.upper())
        timestamp = datetime.now().strftime("%H:%M")
        source_html = ""
        if source:
            source_html = f"<span style='color:{C['muted_2']}; font-weight:700;'>{escape(source)}</span> "
        row_bg = "rgba(255,255,255,0.035)" if level == "header" else "transparent"
        html = (
            f"<div style='background:{row_bg}; padding:5px 0; line-height:1.45;'>"
            f"<span style='color:{C['muted_2']}; font-size:11px;'>[{timestamp}]</span> "
            f"<span style='color:{color}; font-size:10px; font-weight:800;'>[{label}]</span> "
            f"{source_html}<span style='color:{C['text']};'>{escape(str(msg))}</span>"
            f"</div>"
        )
        self.append(html)
        self.moveCursor(QTextCursor.End)

    def trim_blocks(self, max_lines):
        doc = self.document()
        while doc.blockCount() > max_lines:
            cursor = QTextCursor(doc.firstBlock())
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
        self.moveCursor(QTextCursor.End)


class NavButton(QPushButton):
    def __init__(self, index_text, text):
        super().__init__(f"{index_text}   {text}")
        self.setCheckable(True)
        self.setObjectName("NavButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)


class DeviceCard(QFrame):
    def __init__(self, serial, model, checked=True):
        super().__init__()
        self.serial = serial
        self.model = model
        self.setObjectName("DeviceCard")
        self.setProperty("status", "online")
        add_shadow(self, blur=14, offset=4, alpha=45)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked)
        self.checkbox.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self.checkbox)
        title_stack = QVBoxLayout()
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(2)
        self.model_label = QLabel(model)
        self.model_label.setObjectName("DeviceName")
        self.serial_label = QLabel(serial)
        self.serial_label.setObjectName("DeviceSerial")
        title_stack.addWidget(self.model_label)
        title_stack.addWidget(self.serial_label)
        top.addLayout(title_stack, 1)
        top.addStretch()
        self.status_chip = StatusChip("online")
        top.addWidget(self.status_chip)

        layout.addLayout(top)

    def is_checked(self):
        return self.checkbox.isChecked()

    def set_status(self, status):
        status = status if status in STATUS_STYLES else "offline"
        self.setProperty("status", status)
        self.status_chip.set_status(status)
        repolish(self)


class InstanceWindow(QMainWindow):
    def __init__(self, serial, model, email):
        super().__init__()
        self.serial = serial
        self.model = model
        self.email = email
        self.is_active = True

        self.setWindowTitle(model)
        self.resize(430, 560)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("Card")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        header_layout.setSpacing(8)
        header_top = QHBoxLayout()
        header_top.setContentsMargins(0, 0, 0, 0)
        header_top.addWidget(self._label(model, "Title"), 1)
        self.status_chip = StatusChip("working")
        header_top.addWidget(self.status_chip)
        header_layout.addLayout(header_top)
        header_layout.addWidget(self._label(email, "AccentLabel"))
        header_layout.addWidget(self._label(serial, "DeviceSerial"))

        stats_wrap = QWidget()
        stats = QGridLayout(stats_wrap)
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setHorizontalSpacing(10)
        stats.setVerticalSpacing(10)
        self.brl_card = StatCard("Lucro BRL", "R$ 0,00", C["profit"], priority="primary", hint="resultado estimado")
        self.profit_card = StatCard("Pontos Hoje", "+0", C["points"], priority="secondary", hint="saldo do dia")
        self.cycles_card = StatCard("Ciclos", "0", C["accent"], priority="low")
        self.time_card = StatCard("Tempo", "00:00:00", C["muted"], priority="low")
        stats.addWidget(self.brl_card, 0, 0, 1, 2)
        stats.addWidget(self.profit_card, 1, 0, 1, 2)
        stats.addWidget(self.cycles_card, 2, 0)
        stats.addWidget(self.time_card, 2, 1)

        self.status_label = self._label("Instancia em aquecimento", "DimLabel")
        self.console = LogView(compact=True)

        root.addWidget(header)
        root.addWidget(stats_wrap)
        root.addWidget(self.status_label)
        root.addWidget(self.console, 1)

    def _label(self, text, object_name):
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    def log(self, msg, level="info"):
        self.console.append_log(msg, level, self.serial)
        self.console.trim_blocks(240)

    def update_stats(self, stats):
        profit = stats.get("profit", 0)
        brl = CryptoConverter.coins_to_brl(profit)
        self.cycles_card.set_value(str(stats.get("cycles", 0)))
        self.profit_card.set_value(f"+{profit:,}".replace(",", "."))
        self.time_card.set_value(stats.get("elapsed", "00:00:00"))
        self.brl_card.set_value(f"R$ {brl:,.4f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.status_label.setText("Instancia trabalhando")
        self.status_chip.set_status("working")

    def on_finish(self):
        self.is_active = False
        self.status_label.setText("Instancia finalizada")
        self.status_chip.set_status("offline")


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
        content_layout.setContentsMargins(18, 18, 18, 18)
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
        sidebar.setFixedWidth(272)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        brand = self._card("BrandCard")
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(18, 18, 18, 18)
        brand_layout.setSpacing(8)
        brand_layout.addWidget(self._make_label("SpinBot", "HeroTitle"))
        brand_layout.addWidget(self._make_label("Centro de operacao multi-instancia", "DimLabel"))
        brand_layout.addWidget(StatusChip("online"), 0, Qt.AlignLeft)
        layout.addWidget(brand)

        stats_row = QWidget()
        stats = QGridLayout(stats_row)
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setHorizontalSpacing(6)
        self.devices_summary = StatCard("Dispositivos", "0", C["accent"], priority="micro")
        self.emails_summary = StatCard("Emails", "0", C["points"], priority="micro")
        stats.addWidget(self.devices_summary, 0, 0)
        stats.addWidget(self.emails_summary, 0, 1)
        layout.addWidget(stats_row)

        nav_card = self._card()
        nav_layout = QVBoxLayout(nav_card)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(6)
        self.nav_buttons = {}
        for key, index_text, text in NAV_ITEMS:
            button = NavButton(index_text, text)
            button.clicked.connect(lambda checked=False, item=key: self._show_page(item))
            nav_layout.addWidget(button)
            self.nav_buttons[key] = button
        layout.addWidget(nav_card)

        emails_card = self._card()
        emails_layout = QVBoxLayout(emails_card)
        emails_layout.setContentsMargins(14, 14, 14, 14)
        emails_layout.setSpacing(10)
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
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 6)
        grid.setRowStretch(2, 1)

        hero = self._card()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 18, 18, 18)
        hero_layout.setSpacing(12)
        hero_layout.addWidget(self._make_label("Operacao Central", "SectionTitle"))
        hero_layout.addWidget(self._make_label("Controle o lote atual, acompanhe progresso e mantenha cada instancia visivel.", "DimLabel"))

        actions = QHBoxLayout()
        self.start_button = self._button("Iniciar", primary=True)
        self.start_button.clicked.connect(self._toggle_run)
        self.refresh_button = self._button("Atualizar")
        self.refresh_button.clicked.connect(self._refresh_devs)
        self.ultra_eco_checkbox = QCheckBox("Ultra-eco")
        self.ultra_eco_checkbox.setCursor(Qt.PointingHandCursor)
        actions.addWidget(self.start_button)
        actions.addWidget(self.refresh_button)
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
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.total_brl_card = StatCard("Lucro BRL", "R$ 0,00", C["profit"], priority="primary", hint="estimativa financeira")
        self.total_profit_card = StatCard("Pontos Hoje", "+0", C["points"], priority="secondary", hint="soma das contas")
        self.total_cycles_card = StatCard("Ciclos", "0", C["accent"], priority="low")
        self.total_time_card = StatCard("Tempo", "00:00:00", C["muted"], priority="low")
        metrics.addWidget(self.total_brl_card, 0, 0, 1, 2)
        metrics.addWidget(self.total_profit_card, 1, 0, 1, 2)
        metrics.addWidget(self.total_cycles_card, 2, 0)
        metrics.addWidget(self.total_time_card, 2, 1)
        grid.addWidget(metrics_wrap, 1, 0)

        activity = self._card()
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(18, 18, 18, 18)
        activity_layout.setSpacing(10)
        activity_layout.addWidget(self._make_label("Atividades", "SectionTitle"))
        self.mini_log = LogView(compact=True)
        activity_layout.addWidget(self.mini_log, 1)
        grid.addWidget(activity, 2, 0)

        instances = self._card()
        instances_layout = QVBoxLayout(instances)
        instances_layout.setContentsMargins(18, 18, 18, 18)
        instances_layout.setSpacing(10)
        instances_layout.addWidget(self._make_label("Instancias", "SectionTitle"))
        instances_layout.addWidget(self._make_label("Status, serial e selecao dos dispositivos conectados.", "DimLabel"))
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
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(10)
        card_layout.addWidget(self._make_label("Projecoes", "SectionTitle"))
        card_layout.addWidget(self._make_label("Estimativas baseadas no ritmo atual da sessao.", "DimLabel"))
        self.prediction_labels = {}
        for label_text in ["1 Hora", "12 Horas", "1 Dia", "1 Semana", "1 Mes"]:
            row = self._card("InnerCard")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 12, 14, 12)
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
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(10)
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
        connection_layout.setContentsMargins(18, 18, 18, 18)
        connection_layout.setSpacing(10)
        connection_layout.addWidget(self._make_label("Conexao e Dispositivo", "SectionTitle"))
        connection_layout.addWidget(self._make_label("Atualize a lista local ou conecte um ADB remoto sem sair do painel.", "DimLabel"))
        connection_layout.addWidget(self._make_label("Dispositivo padrao", "BodyLabel"))

        combo_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.currentTextChanged.connect(self._on_device_combo_changed)
        combo_row.addWidget(self.device_combo, 1)
        self.settings_refresh_button = self._button("Atualizar")
        self.settings_refresh_button.clicked.connect(self._refresh_devs)
        combo_row.addWidget(self.settings_refresh_button)
        connection_layout.addLayout(combo_row)

        connection_layout.addWidget(self._make_label("ADB remoto (IP:porta)", "BodyLabel"))
        adb_row = QHBoxLayout()
        self.adb_input = QLineEdit("127.0.0.1:5555")
        self.adb_input.setObjectName("LineInput")
        adb_row.addWidget(self.adb_input, 1)
        connect_button = self._button("Conectar", primary=True)
        self.connect_button = connect_button
        self.connect_button.clicked.connect(self._connect_adb)
        adb_row.addWidget(self.connect_button)
        connection_layout.addLayout(adb_row)

        tools = self._card()
        tools_layout = QVBoxLayout(tools)
        tools_layout.setContentsMargins(18, 18, 18, 18)
        tools_layout.setSpacing(10)
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
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(10)
        card_layout.addWidget(self._make_label("Console Consolidado", "SectionTitle"))
        card_layout.addWidget(self._make_label("Logs completos das automacoes em execucao.", "DimLabel"))
        self.txt_log = LogView()
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
                background: {C['panel']};
                border-right: 1px solid {C['border_soft']};
            }}
            #Card, #BrandCard, #StatCard, #DeviceCard, #InnerCard, #WelcomeCard {{
                background: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 8px;
            }}
            #Card:hover, #InnerCard:hover {{
                border-color: {C['surface_soft']};
            }}
            #InnerCard {{
                background: {C['surface_alt']};
            }}
            #WelcomeCard {{
                background: {C['surface_alt']};
            }}
            #BrandCard {{
                background: {C['panel_alt']};
                border-color: {C['surface_soft']};
            }}
            QFrame#StatCard[priority="primary"] {{
                background: {C['surface_alt']};
                border: 1px solid {C['profit']};
            }}
            QFrame#StatCard[priority="secondary"] {{
                background: {C['surface']};
                border: 1px solid {C['surface_soft']};
            }}
            QFrame#StatCard[priority="low"], QFrame#StatCard[priority="micro"] {{
                background: {C['surface']};
                border-color: {C['border_soft']};
            }}
            QFrame#StatCard[pulse="on"] {{
                border-color: {C['accent_hover']};
                background: {C['surface_alt']};
            }}
            QFrame#KpiAccent {{
                border: 0;
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
                padding: 10px 12px;
                border: 0;
                border-radius: 8px;
                background: transparent;
                color: {C['muted']};
                font-weight: 700;
            }}
            #NavButton:hover {{
                background: {C['surface']};
                color: {C['text']};
            }}
            #NavButton:checked {{
                background: {C['surface_alt']};
                color: {C['text']};
                border-left: 3px solid {C['accent']};
            }}
            QLabel#HeroTitle {{ font-size: 30px; font-weight: 900; color: {C['text']}; }}
            QLabel#WelcomeTitle {{ font-size: 42px; font-weight: 800; color: {C['text']}; }}
            QLabel#WelcomeSubtitle {{ font-size: 14px; color: {C['muted']}; }}
            QLabel#SectionTitle {{ font-size: 20px; font-weight: 900; }}
            QLabel#Title {{ font-size: 18px; font-weight: 900; }}
            QLabel#StatValue {{ font-size: 28px; font-weight: 800; }}
            QFrame#StatCard[priority="primary"] QLabel#StatValue {{ font-size: 34px; font-weight: 900; }}
            QFrame#StatCard[priority="secondary"] QLabel#StatValue {{ font-size: 30px; font-weight: 900; }}
            QFrame#StatCard[priority="micro"] QLabel#StatValue {{ font-size: 22px; }}
            QLabel#CardCaption, QLabel#DimLabel {{ color: {C['muted']}; }}
            QLabel#CardHint {{ color: {C['muted_2']}; font-size: 11px; }}
            QLabel#BodyLabel {{ color: {C['text']}; font-weight: 700; }}
            QLabel#AccentLabel {{ color: {C['accent']}; font-weight: 800; }}
            QLabel#WarnLabel {{ color: {C['warning']}; font-weight: 800; }}
            QLabel#DeviceName {{ color: {C['text']}; font-weight: 900; font-size: 13px; }}
            QLabel#DeviceSerial {{ color: {C['muted_2']}; font-family: 'Cascadia Mono', 'Consolas'; font-size: 11px; }}
            QLabel#StatusBadge {{ background: {C['surface_soft']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 7px 12px; font-weight: 800; }}
            QPushButton#AppButton {{
                background: {C['surface_soft']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 10px 16px;
                font-weight: 900;
            }}
            QPushButton#AppButton:hover {{ background: {C['surface_hover']}; border-color: {C['accent']}; }}
            QPushButton#AppButton:pressed {{ background: {C['surface_alt']}; padding-top: 11px; padding-bottom: 9px; }}
            QPushButton#AppButton:focus {{ border: 1px solid {C['accent_hover']}; }}
            QPushButton#AppButton[variant="primary"] {{ background: {C['accent']}; color: #08110f; border-color: {C['accent']}; }}
            QPushButton#AppButton[variant="primary"]:hover {{ background: {C['accent_hover']}; }}
            QPushButton#AppButton[variant="danger"] {{ background: {C['danger']}; color: #16080a; border-color: {C['danger']}; }}
            QPushButton#AppButton[variant="danger"]:hover {{ background: {C['danger_hover']}; }}
            QPushButton#AppButton[variant="loading"] {{ background: {C['surface_alt']}; color: {C['muted']}; border-color: {C['warning']}; }}
            QLineEdit#LineInput, QPlainTextEdit#InputArea, QPlainTextEdit#Console, QTextEdit#Console, QComboBox {{
                background: {C['console']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 9px;
                color: {C['text']};
                selection-background-color: {C['accent']};
                selection-color: #07100e;
            }}
            QComboBox {{
                min-height: 22px;
                padding-right: 30px;
                background: {C['surface_alt']};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                background: {C['surface_soft']};
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
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
                background: {C['console']};
                font-family: 'Cascadia Mono', 'Consolas';
                font-size: 11px;
            }}
            QFrame#DeviceCard[status="working"] {{ border-color: {C['profit']}; background: {C['surface_alt']}; }}
            QFrame#DeviceCard[status="paused"] {{ border-color: {C['warning']}; }}
            QFrame#DeviceCard[status="error"] {{ border-color: {C['danger']}; }}
            QFrame#DeviceCard[status="offline"] {{ border-color: {C['border_soft']}; }}
            QFrame {{
                background: transparent;
            }}
            QScrollArea#ScrollArea {{ border: 0; background: transparent; }}
            QScrollBar:vertical {{ background: {C['panel']}; width: 9px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {C['surface_soft']}; min-height: 26px; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {C['surface_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QCheckBox {{ spacing: 8px; font-weight: 800; color: {C['text']}; }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 5px;
                border: 1px solid {C['border']};
                background: {C['surface_alt']};
            }}
            QCheckBox::indicator:checked {{
                background: {C['accent']};
                border-color: {C['accent']};
            }}
            """
        )

    def _card(self, object_name="Card"):
        card = QFrame()
        card.setObjectName(object_name)
        add_shadow(card, blur=22, offset=8, alpha=80)
        return card

    def _make_label(self, text, object_name):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName(object_name)
        return label

    def _button(self, text, primary=False):
        button = QPushButton(text)
        button.setObjectName("AppButton")
        button.setProperty("variant", "primary" if primary else "default")
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _set_button_variant(self, button, variant, text=None, enabled=True):
        if text is not None:
            button.setText(text)
        button.setEnabled(enabled)
        button.setProperty("variant", variant)
        repolish(button)

    def _flash_button_text(self, button, text, ms=900):
        original = button.text()
        button.setText(text)
        QTimer.singleShot(ms, lambda: button.setText(original))

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
        source = None
        body = msg
        if isinstance(msg, str) and msg.startswith("[") and "] " in msg:
            idx = msg.find("] ")
            source = msg[1:idx]
            body = msg[idx + 2:]
        self.txt_log.append_log(body, level, source)
        self.mini_log.append_log(body, level, source)
        self._trim_console(self.txt_log, getattr(config, "MAX_LOG_LINES", 500))
        self._trim_console(self.mini_log, 20)

    def _append_instance_log(self, serial, msg, level="info"):
        window = self.instance_windows.get(serial)
        if window:
            window.log(msg, level)
        self.bus.global_log.emit(f"[{serial}] {msg}", level)

    def _trim_console(self, widget, max_lines):
        if hasattr(widget, "trim_blocks"):
            widget.trim_blocks(max_lines)
            return
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
        self._set_button_variant(self.start_button, "danger", "Parar")
        self.status_badge.setText(f"{len(devices)} instancia(s) em execucao")
        self.bus.global_log.emit(f"Iniciando lote com {len(devices)} dispositivo(s).", "header")

        for index, config_item in enumerate(configs):
            serial = config_item.serial
            window = InstanceWindow(serial, config_item.model, config_item.email)
            window.move(70 + (index * 28), 70 + (index * 28))
            window.show()
            self.instance_windows[serial] = window
            card = self.device_cards.get(serial)
            if card:
                card.set_status("working")

        try:
            self.orchestrator.start(configs, ultra_eco=self.ultra_eco_checkbox.isChecked())
        except Exception as exc:
            self.bus.global_log.emit(f"Falha ao iniciar orquestrador: {exc}", "error")
            self._on_all_finish()

    def _stop(self):
        if not self.is_running:
            return
        self.orchestrator.stop()
        self._set_button_variant(self.start_button, "loading", "Parando...", enabled=False)
        self.status_badge.setText("Encerrando instancias...")
        self.bus.global_log.emit("Solicitando parada de todas as instancias...", "warning")
        for card in self.device_cards.values():
            if card.is_checked():
                card.set_status("paused")

    def _store_instance_stats(self, serial, stats):
        self.instance_stats[serial] = stats
        window = self.instance_windows.get(serial)
        if window:
            window.update_stats(stats)
        card = self.device_cards.get(serial)
        if card:
            card.set_status("working")
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
        card = self.device_cards.get(serial)
        if card:
            snapshot = self.orchestrator.snapshot().get(serial)
            if snapshot and snapshot.status == InstanceStatus.FAILED:
                card.set_status("error")
            elif snapshot and snapshot.status == InstanceStatus.STOPPED:
                card.set_status("paused")
            else:
                card.set_status("offline")
        if self.instance_windows and all(not item.is_active for item in self.instance_windows.values()):
            self._on_all_finish()

    def _on_all_finish(self):
        self.is_running = False
        self._set_button_variant(self.start_button, "primary", "Iniciar", enabled=True)
        self.status_badge.setText("Processo finalizado")
        self.reports_dirty = True
        self.bus.global_log.emit("Todas as instancias foram finalizadas.", "header")

    def _refresh_devs(self):
        for button in (getattr(self, "refresh_button", None), getattr(self, "settings_refresh_button", None)):
            if button:
                self._flash_button_text(button, "Atualizando...")
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
            card.set_status("online")
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
            self._set_button_variant(self.connect_button, "loading", "Conectando...", enabled=False)
            result = self.device_manager.connect_remote(address)
            self.bus.global_log.emit(f"Resultado do ADB: {result}", "info")
            self._refresh_devs()
        except Exception as exc:
            self.bus.global_log.emit(str(exc), "error")
        finally:
            self._set_button_variant(self.connect_button, "primary", "Conectar", enabled=True)

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
