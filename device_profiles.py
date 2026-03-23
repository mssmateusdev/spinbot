"""
Gerenciamento de perfis por dispositivo.
Salva calibração (screenshot + posição do contador de spins) para cada dispositivo.

NOTA: O app usa WebView/Flutter, então o uiautomator2 NÃO consegue
ver os contadores como elementos individuais. A calibração agora usa
proporções da tela + OCR para detectar as regiões automaticamente.
"""

import os
import json
import re
import time
import uiautomator2 as u2
from colorama import Fore, Style

PROFILES_DIR = "device_profiles"


def _safe_serial(serial: str) -> str:
    """Converte serial para nome de arquivo seguro."""
    return serial.replace(":", "_").replace(".", "_").replace("/", "_")


def get_profile_path(serial: str) -> str:
    """Retorna o caminho do perfil para um serial."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    return os.path.join(PROFILES_DIR, f"{_safe_serial(serial)}.json")


def load_profile(serial: str) -> dict:
    """Carrega o perfil salvo de um dispositivo."""
    path = get_profile_path(serial)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def save_profile(serial: str, profile: dict):
    """Salva o perfil de um dispositivo."""
    path = get_profile_path(serial)
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    print(f"{Fore.GREEN}  [PERFIL] Salvo em: {path}{Style.RESET_ALL}")


def calibrate_device(d: u2.Device, serial: str) -> dict:
    """
    Calibra um dispositivo usando PROPORÇÕES DA TELA + OCR.
    
    O app (WebView/Flutter) não expõe elementos individuais ao uiautomator2.
    Em vez disso, usamos proporções fixas baseadas no layout padrão do app:
    
    Layout do header:
    ┌──────────────────────────────────────────────┐
    │  [SpinIcon] [Spins]  [CoinIcon($)] [Moedas]  │  ← ~5% da altura
    └──────────────────────────────────────────────┘
    
    - Spins: 5%-35% da largura, 1%-6% da altura
    - Moedas: 45%-85% da largura, 1%-6% da altura
    """
    print(f"\n{Fore.CYAN}{'═'*60}")
    print(f"  🔧 CALIBRANDO DISPOSITIVO (Screenshot + OCR)")
    print(f"{'═'*60}{Style.RESET_ALL}\n")
    
    w, h = d.window_size()
    print(f"  📐 Tela: {w}x{h}")
    
    # Salvar screenshot
    screenshots_dir = os.path.join(PROFILES_DIR, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    screenshot_path = os.path.join(screenshots_dir, f"{_safe_serial(serial)}.png")
    d.screenshot(screenshot_path)
    print(f"  📸 Screenshot salva: {screenshot_path}")
    
    # Definir regiões por proporção da tela
    # A status bar do Android ocupa ~5.5% do topo (130px em 2400)
    # Os contadores ficam centralizados no header do app, abaixo da status bar
    # Layout: [hamburger]  ...  [SpinIcon] [Spins]  [CoinIcon($)] [Moedas]  [Level]
    
    # Região dos Spins (ícone verde + número)
    # Fica na metade direita do header
    spin_region = {
        "x1": int(w * 0.45),
        "y1": int(h * 0.055),
        "x2": int(w * 0.65),
        "y2": int(h * 0.10),
    }
    
    # Região das Moedas (ícone $ + número)
    # Fica mais à direita, após o spin
    coin_region = {
        "x1": int(w * 0.62),
        "y1": int(h * 0.055),
        "x2": int(w * 0.98),
        "y2": int(h * 0.10),
    }
    
    print(f"  🎯 Região Spins: ({spin_region['x1']},{spin_region['y1']}) → ({spin_region['x2']},{spin_region['y2']})")
    print(f"  🎯 Região Moedas: ({coin_region['x1']},{coin_region['y1']}) → ({coin_region['x2']},{coin_region['y2']})")
    
    # Testar OCR nas regiões
    try:
        from ocr_reader import read_coins_ocr, read_spins_ocr
        
        # Montar perfil temporário para teste
        test_profile = {
            "spin_counter": {"bounds_region": spin_region},
            "coin_counter": {"bounds_region": coin_region},
        }
        
        spins_val = read_spins_ocr(d, test_profile)
        coins_val = read_coins_ocr(d, test_profile)
        
        if spins_val >= 0:
            print(f"  {Fore.GREEN}✓ Spins lido via OCR: {spins_val}{Style.RESET_ALL}")
        else:
            print(f"  {Fore.YELLOW}⚠ OCR não conseguiu ler spins (tentará em runtime){Style.RESET_ALL}")
            
        if coins_val >= 0:
            print(f"  {Fore.GREEN}✓ Moedas lido via OCR: {coins_val}{Style.RESET_ALL}")
        else:
            print(f"  {Fore.YELLOW}⚠ OCR não conseguiu ler moedas (tentará em runtime){Style.RESET_ALL}")
            
    except Exception as e:
        print(f"  {Fore.YELLOW}⚠ Teste OCR falhou: {e}{Style.RESET_ALL}")
        spins_val = -1
        coins_val = -1
    
    # Montar perfil final
    profile = {
        "serial": serial,
        "screen_width": w,
        "screen_height": h,
        "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "screenshot": screenshot_path,
        "spin_counter": {
            "bounds_region": spin_region,
            "resource_id": "",
            "sample_value": spins_val if spins_val >= 0 else -1,
        },
        "coin_counter": {
            "bounds_region": coin_region,
            "resource_id": "",
            "sample_value": coins_val if coins_val >= 0 else -1,
        },
    }
    
    save_profile(serial, profile)
    return profile


def read_spins_with_profile(d: u2.Device, profile: dict) -> int:
    """
    Lê o número de spins usando o perfil calibrado.
    Tenta primeiro via uiautomator2 (texto), depois OCR.
    """
    if not profile or not profile.get("spin_counter"):
        return -1
    
    sc = profile["spin_counter"]
    region = sc["bounds_region"]
    
    # Estratégia 1: uiautomator2 por resource-id
    res_id = sc.get("resource_id", "")
    if res_id:
        try:
            elem = d(resourceId=res_id)
            if elem.exists(timeout=0.5):
                text = elem.get_text()
                clean = text.replace(",", "").replace(".", "").replace(" ", "")
                if clean.isdigit():
                    return int(clean)
        except:
            pass
    
    # Estratégia 2: OCR
    try:
        from ocr_reader import read_spins_ocr
        return read_spins_ocr(d, profile)
    except:
        pass
    
    return -1


def read_coins_with_profile(d: u2.Device, profile: dict) -> int:
    """
    Lê o saldo de moedas usando o perfil calibrado.
    Usa OCR como método primário.
    """
    if not profile or not profile.get("coin_counter"):
        return -1
    
    try:
        from ocr_reader import read_coins_ocr
        return read_coins_ocr(d, profile)
    except:
        pass
    
    return -1
