# ============================================================
# CONFIGURAÇÃO DO AUTOMADOR DE SPINS (v0.4.0 Otimizado)
# ============================================================

# --- Resolução do celular ---
SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 2400

# --- Seletores de texto dos elementos da UI ---
SPIN_BUTTON_TEXT = "SPIN"
AD_BUTTON_TEXT = "See an ad"
CLOSE_AD_TEXTS = ["×", "X", "Close", "Fechar", "✕", "╳", "Skip Ad", "Recompensa concedida", "Continuar", ">|", ">>", ">>|", "Skip"]

# --- Popup de aviso ---
POPUP_WARNING_TEXT = "Use all your spins before watching"
POPUP_CLOSE_TEXTS = ["Close", "close", "CLOSE", "OK", "Ok", "Fechar"]
PLAY_STORE_LOGIN_TEXTS = ["Confirme a sua identidade", "Inicie sessão", "Verify your identity", "Sign in", "Confirm sua identidade", "Verifique sua identidade", "Google Identity", "Account recovery"]

# --- Tempos de Operação (Reduzidos para Máxima Performance) ---
SPIN_WAIT = 3.2          # Tempo de animação da roleta
SPIN_WAIT_TIME = 3.2

AD_MAX_WAIT = 45         # Tempo máximo esperando anúncio
AD_CHECK_INTERVAL = 1.5   # Polling mais rápido
CLOSE_AD_WAIT = 1.5      # Espera após fechar
AD_LOAD_WAIT = 3.5       # Espera o anúncio abrir
AD_MIN_WAIT_FALLBACK = 15  # Tempo mínimo que esperamos antes de fechar ads sem timer

# --- Aplicativo ---
APP_PACKAGE = "com.spincoin.appmobile.top"
APP_LAUNCH_WAIT = 6.0
APP_REOPEN_TIMEOUT = 25
APP_REOPEN_WAIT = 5.0

# --- Otimização de Performance ---
MAX_CYCLES = None
DEBUG_MODE = False
ENABLE_MEMORY_OPTIMIZATION = True  # Ativado por padrão para liberar RAM
STATS_UPDATE_INTERVAL = 10         # Atualizar stats na GUI a cada X segundos (poupa CPU)
MAX_LOG_LINES = 500                # Limite de linhas no console para poupar RAM desktop

# --- Path do ADB ---
ADB_PATH = "adb.exe"
DEBUG_FOLDER = "debug_screenshots"

# --- Pacotes Seguros (Não fechar se app mudar para estes durante anúncio) ---
SAFE_AD_PACKAGES = [
    # "com.google.android.gms",   # Google Play Services (REMOVIDO: Interrompe com login)
    "com.google.android.webview", # Android System WebView
    "com.android.systemui",       # System UI
]
