# ============================================================
# CONFIGURAÇÃO DO SPINBOT
# ============================================================

APP_VERSION = "0.6.5"

# --- Resolução do celular ---
SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 2400

# --- Seletores de texto dos elementos da UI ---
SPIN_BUTTON_TEXT = "SPIN"
AD_BUTTON_TEXT = "See an ad"
CLOSE_AD_TEXTS = [">|", ">I", ">>", ">>|", "Continuar", "×", "X", "Close", "Fechar", "✕", "╳", "Skip Ad", "Recompensa concedida", "Skip"]

# --- Popup de aviso ---
POPUP_WARNING_TEXT = "Use all your spins before watching"
POPUP_CLOSE_TEXTS = ["CLOSE", "Close", "close", "OK", "Ok", "Fechar"]
PLAY_STORE_LOGIN_TEXTS = ["Confirme a sua identidade", "Inicie sessão", "Verify your identity", "Sign in", "Confirm sua identidade", "Verifique sua identidade", "Google Identity", "Account recovery"]

# --- Tempos de Operação (Reduzidos para Máxima Performance) ---
SPIN_WAIT = 2.8          # Reduzido de 3.2s para 2.8s (Fica no limite da animação)
SPIN_WAIT_TIME = 2.8
TURBO_CLICK_INTERVAL = 0.4 # Reduzido de 0.5s para 0.4s
TURBO_RESULT_CHECK_EVERY = 3
TURBO_COIN_UPDATE_EVERY = 5
PRE_AD_SPIN_CHECK_WAIT = 1.2
PRE_AD_CONFIRM_WAIT = 1.0

AD_MAX_WAIT = 40         # Reduzido de 45s
AD_CHECK_INTERVAL = 1.0   # Polling mais rápido (baixado de 1.5s)
CLOSE_AD_WAIT = 1.0      # Reduzido de 1.5s
AD_LOAD_WAIT = 2.5       # Reduzido de 3.5s
AD_MIN_WAIT_FALLBACK = 15  # Tempo mínimo que esperamos antes de fechar ads sem timer

# --- Aplicativo ---
APP_PACKAGE = "com.spincoin.appmobile.top"
APP_LAUNCH_WAIT = 4.0
APP_REOPEN_TIMEOUT = 25
APP_REOPEN_WAIT = 5.0

# --- Otimização de Performance ---
MAX_CYCLES = None
DEBUG_MODE = False
ENABLE_MEMORY_OPTIMIZATION = True  # Ativado por padrão para liberar RAM
STATS_UPDATE_INTERVAL = 10         # Atualizar stats na GUI a cada X segundos (poupa CPU)
MAX_LOG_LINES = 500                # Limite de linhas no console para poupar RAM desktop

# --- Controle ADB / Multi-instância ---
ADB_CONNECT_RETRIES = 3
ADB_RETRY_ATTEMPTS = 2
ADB_RETRY_BASE_BACKOFF = 0.25
ADB_RETRY_MAX_BACKOFF = 2.0
ADB_SLOW_OP_THRESHOLD = 1.2
UI_HIERARCHY_CACHE_TTL = 0.35
APP_CURRENT_CACHE_TTL = 0.25
WINDOW_SIZE_CACHE_TTL = 300.0
SCREENSHOT_CACHE_TTL = 0.35
VISUAL_CROSS_TAP = False
MEMORY_OPTIMIZATION_MIN_INTERVAL = 600
OCR_MIN_INTERVAL_SPINS = 0.8
OCR_MIN_INTERVAL_COINS = 2.0
STATS_SAVE_INTERVAL = 5.0

# --- Path do ADB ---
ADB_PATH = "adb.exe"
DEBUG_FOLDER = "debug_screenshots"

# --- Pacotes Seguros (Não fechar se app mudar para estes durante anúncio) ---
SAFE_AD_PACKAGES = [
    # "com.google.android.gms",   # Google Play Services (REMOVIDO: Interrompe com login)
    "com.google.android.webview", # Android System WebView
    "com.android.systemui",       # System UI
]
