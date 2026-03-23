"""
Módulo de leitura de tela otimizado (v0.4.0).
Reduz tráfego ADB e processamento local para máxima velocidade.
"""

import re
import uiautomator2 as u2
from colorama import Fore, Style
import config

# Cache local da hierarquia para evitar múltiplos dumps no mesmo ciclo
_last_hierarchy = None
_last_dump_time = 0

def _get_cached_hierarchy(d: u2.Device, ttl=0.5):
    """Obtém a hierarquia de UI, usando cache se estiver dentro do TTL."""
    global _last_hierarchy, _last_dump_time
    import time
    now = time.time()
    if _last_hierarchy is None or (now - _last_dump_time) > ttl:
        _last_hierarchy = d.dump_hierarchy()
        _last_dump_time = now
    return _last_hierarchy

def find_spin_button(d: u2.Device, profile: dict = None):
    # Seletores u2 já são relativamente rápidos e processados no device
    btn = d(text=config.SPIN_BUTTON_TEXT)
    if btn.exists(timeout=0.3): return btn
    
    # Fallback rápido se o texto falhar por delay de renderização
    btn = d(description=config.SPIN_BUTTON_TEXT)
    if btn.exists(timeout=0.2): return btn
    return None

def find_ad_button(d: u2.Device):
    # Busca direta pelo texto configurado
    btn = d(textContains=config.AD_BUTTON_TEXT)
    if btn.exists(timeout=0.5): return btn
    
    # Busca por texto curto (mais rápido no device)
    for text in ["+ 10 spins", "10 spins"]:
        btn = d(textContains=text)
        if btn.exists(timeout=0.2): return btn
    return None

def check_and_dismiss_popup(d: u2.Device) -> bool:
    # Checagem rápida de popup
    popup = d(textContains=config.POPUP_WARNING_TEXT)
    if popup.exists(timeout=0.2):
        for text in config.POPUP_CLOSE_TEXTS:
            btn = d(text=text)
            if btn.exists(timeout=0.1):
                btn.click()
                return True
        d.press("back")
        return True
    return False

def check_spins_status(d: u2.Device, profile: dict = None) -> str:
    # 1. Tenta ler o contador numérico
    spin_count = read_spin_count_from_ui(d, profile=profile)
    if spin_count == 0: return "NO_SPINS"
    if spin_count > 0: return "HAS_SPINS"
    
    # 2. Se a leitura do número falhar (-1), verifique se o botão de anúncio está visível.
    # No SpinCoin, se você tem spins, o botão de anúncio geralmente some ou muda.
    # Mas o botão de SPIN pode estar lá mesmo com 0.
    if d(textContains=config.AD_BUTTON_TEXT).exists(timeout=0.2):
         return "NO_SPINS"
         
    # 3. Salvaguarda final: se o botão SPIN existe e NÃO há botão de anúncio, supomos que tem spins.
    if d(text=config.SPIN_BUTTON_TEXT).exists(timeout=0.2):
        return "HAS_SPINS"
        
    return "UNKNOWN"

def read_spin_count_from_ui(d: u2.Device, profile: dict = None) -> int:
    """Lê número de spins usando processamento local da hierarquia (mais rápido)."""
    if profile:
        from device_profiles import read_spins_with_profile
        return read_spins_with_profile(d, profile)
    
    try:
        xml = d.dump_hierarchy()
        # Regex flexível: extrai texto (podendo conter vírgula/ponto) e bounds
        matches = re.findall(r'text="([\d.,]+)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        
        w, h = d.window_size()
        y_threshold = h * 0.15 # Top 15%
        x_start = w * 0.3
        x_end = w * 0.8
        
        candidates = []
        for val_str, x1, y1, x2, y2 in matches:
            # Limpa separadores
            val_clean = val_str.replace(',', '').replace('.', '')
            if not val_clean.isdigit(): continue
            
            val = int(val_clean)
            y_pos = int(y1)
            x_pos = int(x1)
            # Spins costumam ser o primeiro número no topo direito (antes das moedas)
            if y_pos < y_threshold and x_start < x_pos < x_end and val < 1000:
                candidates.append((val, x_pos))
        
        if candidates:
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]
    except Exception: pass
    return -1

def read_coin_count_from_ui(d: u2.Device, profile: dict = None) -> int:
    """Lê saldo total usando hierarquia (rápido) ou OCR (fallback)."""
    if profile:
        from device_profiles import read_coins_with_profile
        return read_coins_with_profile(d, profile)
    
    # 1. Tentar busca rápida na hierarquia
    try:
        xml = d.dump_hierarchy()
        # Busca por números que podem conter separadores (ex: 78,051)
        matches = re.findall(r'(?:text|content-desc)="([\d.,]+)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        
        w, h = d.window_size()
        y_max = h * 0.15 # Top 15% da tela
        x_min = w * 0.6  # Moedas ficam bem à direita
        
        candidates = []
        for val_str, x1, y1, x2, y2 in matches:
            val_clean = val_str.replace(',', '').replace('.', '')
            if not val_clean.isdigit(): continue
            
            val = int(val_clean)
            y_pos = int(y1)
            x_pos = int(x1)
            if y_pos < y_max and x_pos > x_min:
                candidates.append(val)
        
        if candidates:
            # O maior valor nessa área costuma ser o saldo (moedas)
            return max(candidates)
            
    except Exception: pass

    # 2. Fallback para OCR
    try:
        from ocr_reader import read_coins_ocr
        dummy_profile = {"coin_counter": {"bounds_region": {"x1": 500, "y1": 50, "x2": 1000, "y2": 150}}}
        res = read_coins_ocr(d, profile or dummy_profile)
        if res > 0: return res
    except Exception: pass
    
    return -1

def find_close_button(d: u2.Device):
    """
    Busca exaustiva por botões de fechar anúncios (X, fechar, skip, etc).
    Retorna o objeto do botão se encontrado, ou None.
    """
    # 1. Tentativa por texto exato e descrição (Configurados em config.py)
    for text in config.CLOSE_AD_TEXTS:
        btn = d(text=text)
        if btn.exists(timeout=0.1): return btn
        
        btn = d(description=text)
        if btn.exists(timeout=0.1): return btn
        
        # Símbolos curtos (X, ×, ✕)
        if len(text) <= 3:
            btn = d(textContains=text)
            if btn.exists(timeout=0.08): return btn

    # 2. Busca por Regex em descrições (Comum em botões circulares ou apenas ícones)
    regex_patterns = ["(?i).*close.*", "(?i).*fechar.*", "(?i).*dismiss.*", "(?i).*skip.*"]
    for pattern in regex_patterns:
        btn = d(descriptionMatches=pattern)
        if btn.exists(timeout=0.1): return btn

    # 3. Busca por IDs de recursos comuns em SDKs de anúncios (AdMob, Unity, AppLovin, etc.)
    common_rids = [
        "close_button", "close_button_v2", "dismiss_button", 
        "interstitial_close_button", "tt_video_ad_close_layout",
        "close-button", "closeicon", "close-icon", "close_icon",
        "mraid_close_button", "btn_close_ad", "native_ad_close"
    ]
    for rid in common_rids:
        btn = d(resourceIdMatches=f".*{rid}.*")
        if btn.exists(timeout=0.08): return btn
        
    return None

def is_main_screen(d: u2.Device) -> bool:
    # Verificação minimalista
    if d(text=config.SPIN_BUTTON_TEXT).exists(timeout=0.4): return True
    if d(textContains=config.AD_BUTTON_TEXT).exists(timeout=0.4): return True
    return False

def is_ad_screen(d: u2.Device) -> bool:
    if d(text=config.SPIN_BUTTON_TEXT).exists(timeout=0.2): return False
    # Indicadores comuns de anúncio que não aparecem na main
    for indicator in ["Instalar", "Install", "seg.", "segundos"]:
        if d(textContains=indicator).exists(timeout=0.2): return True
    return False

def get_ad_timer(d: u2.Device) -> int:
    """
    Lê o timer do anúncio. Retorna segundos restantes ou -1 se não encontrado.
    Otimizado para detectar números próximos ao 'X' e em balões isolados (pill).
    """
    try:
        xml = d.dump_hierarchy()
        if not xml: return -1
        
        # 1. Padrões com sufixos em text ou content-desc (seg, s, sec, etc)
        # Ex: "15 seg", "30s", "10 seconds", "8 seg. para fechar"
        timer_patterns = [
            r'(?:text|content-desc)="(\d+)\s*(?:seg|s|sec|second|segundo)[^"]*"',
            r'(?:text|content-desc)="[^"]*?\s*(\d+)\s*(?:seg|s|sec|second|segundo)[^"]*"',
            r'(?:text|content-desc)="[^"]*?reward[^"]*?(\d+)[^"]*"',
        ]
        
        for pat in timer_patterns:
            match = re.search(pat, xml, re.I)
            if match:
                val = int(match.group(1))
                if 0 <= val <= 90: return val

        # 2. Números isolados (1-60) no topo da tela
        # Comum em novos tipos de ads que mostram apenas o número ao lado do X
        matches = re.finditer(r'(?:text|content-desc)="(\d+)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        w, h = d.window_size()
        y_threshold = h * 0.20 # Top 20%
        
        for match in matches:
            val = int(match.group(1))
            if 0 <= val <= 60:
                y1 = int(match.group(3))
                # Se estiver na parte superior da tela
                if y1 < y_threshold:
                    return val
                    
    except Exception: pass
    return -1

# Funções de login mantidas simplificadas
def find_getting_started_button(d: u2.Device):
    return d(textContains="Getting").exists(timeout=0.5) and d(textContains="Getting")

def find_email_field(d: u2.Device):
    return d(className="android.widget.EditText").exists(timeout=0.5) and d(className="android.widget.EditText")

def find_login_button(d: u2.Device):
    return d(textContains="Login").exists(timeout=0.5) and d(textContains="Login")

def get_spin_result(d: u2.Device) -> int:
    """Tenta ler o valor ganho no spin (ex: '+ 50' ou '+100')."""
    try:
        xml = d.dump_hierarchy()
        # Busca por padrões de ganho: "+ 100", "+1.000", etc.
        # Aceita text ou content-desc
        matches = re.findall(r'(?:text|content-desc)="\+\s*([\d.,]+)"', xml)
        
        if matches:
            values = []
            for v in matches:
                clean = v.replace(',', '').replace('.', '')
                if clean.isdigit():
                    values.append(int(clean))
            
            if values:
                return max(values)
    except Exception: pass
    return 0
