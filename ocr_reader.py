"""
Leitura de valores numéricos da tela via OCR (Tesseract).
Substituto leve ao EasyOCR para reduzir consumo de memória.

Dependências: pytesseract, Pillow
Requer Tesseract-OCR instalado no sistema.
"""

import re
import os
import threading
import time
from PIL import Image, ImageEnhance

import config

# Tentar importar pytesseract
try:
    import pytesseract
except ImportError:
    pytesseract = None

# Configuração do caminho do Tesseract (se não estiver no PATH)
# Tenta caminhos padrões do Windows
possible_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.join(os.getcwd(), "tesseract", "tesseract.exe"), # Versão portátil local
]

TESSERACT_CMD = None
for p in possible_paths:
    if os.path.exists(p):
        TESSERACT_CMD = p
        break

if pytesseract and TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

_ocr_cache = {}
_ocr_lock = threading.RLock()
_warned_missing_tesseract = False


def _screenshot_to_pil(device) -> Image.Image:
    """Captura screenshot do dispositivo e retorna como PIL Image."""
    try:
        return device.screenshot(ttl=getattr(config, "SCREENSHOT_CACHE_TTL", 0.35))
    except TypeError:
        return device.screenshot()


def _device_key(device):
    return getattr(device, "serial", None) or getattr(device, "_serial", None) or id(device)


def _region_key(kind: str, device, region: dict):
    return (
        kind,
        _device_key(device),
        region.get("x1"), region.get("y1"), region.get("x2"), region.get("y2"),
    )


def _get_cached_ocr(key, ttl: float):
    now = time.time()
    with _ocr_lock:
        ts, value = _ocr_cache.get(key, (0, None))
        if value is not None and (now - ts) <= ttl:
            return value
    return None


def _set_cached_ocr(key, value: int):
    with _ocr_lock:
        _ocr_cache[key] = (time.time(), value)


def _crop_region(img: Image.Image, region: dict, margin: int = 10) -> Image.Image:
    x1 = max(0, region["x1"] - margin)
    y1 = max(0, region["y1"] - margin)
    x2 = min(img.width, region["x2"] + margin)
    y2 = min(img.height, region["y2"] + margin)
    return img.crop((x1, y1, x2, y2))


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """
    Pré-processa a imagem p/ Tesseract.
    Retorna PIL Image (Tesseract aceita PIL direto).
    """
    # Redimensionar 3x
    w, h = img.size
    img = img.resize((w * 3, h * 3), Image.LANCZOS)
    
    # Escala de cinza
    img = img.convert("L")
    
    # Aumentar contraste
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    
    # Binarização simples (threshold)
    # Tesseract gosta de texto preto em fundo branco ou vice-versa bem definido
    img = img.point(lambda x: 0 if x < 128 else 255, '1')
    
    return img


def _extract_number(text: str) -> int:
    """Extrai apenas dígitos."""
    clean = text.replace(",", "").replace(".", "").replace(" ", "")
    clean = re.sub(r'[^\d]', '', clean)
    if clean:
        return int(clean)
    return -1


def read_coins_ocr(device, profile: dict) -> int:
    global _warned_missing_tesseract
    if not pytesseract:
        if not _warned_missing_tesseract:
            print("  [OCR] pytesseract não instalado.")
            _warned_missing_tesseract = True
        return -1
    if not TESSERACT_CMD:
        if not _warned_missing_tesseract:
            print("  [OCR] Tesseract executável não encontrado. Instale o Tesseract-OCR.")
            _warned_missing_tesseract = True
        return -1

    if not profile or not profile.get("coin_counter"):
        return -1
    
    region = profile["coin_counter"]["bounds_region"]
    cache_key = _region_key("coins", device, region)
    cached = _get_cached_ocr(cache_key, getattr(config, "OCR_MIN_INTERVAL_COINS", 2.0))
    if cached is not None:
        return cached
    
    try:
        img = _screenshot_to_pil(device)
        cropped = _crop_region(img, region, margin=10)
        processed = _preprocess_for_ocr(cropped)
        
        # Configuração para números apenas
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789,$'
        
        text = pytesseract.image_to_string(processed, config=custom_config)
        value = _extract_number(text)
        
        if value >= 0:
            if getattr(config, "DEBUG_MODE", False):
                print(f"  [OCR] Moedas lidas: {value}")
            _set_cached_ocr(cache_key, value)
            return value
        
        return -1
        
    except Exception as e:
        print(f"  [OCR] Erro: {e}")
        return -1


def read_spins_ocr(device, profile: dict) -> int:
    # Mesmo processo para spins
    if not pytesseract or not TESSERACT_CMD: return -1
    if not profile or not profile.get("spin_counter"): return -1
    
    region = profile["spin_counter"]["bounds_region"]
    cache_key = _region_key("spins", device, region)
    cached = _get_cached_ocr(cache_key, getattr(config, "OCR_MIN_INTERVAL_SPINS", 0.8))
    if cached is not None:
        return cached
    try:
        img = _screenshot_to_pil(device)
        cropped = _crop_region(img, region, margin=5)
        processed = _preprocess_for_ocr(cropped)
        
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
        text = pytesseract.image_to_string(processed, config=custom_config)
        value = _extract_number(text)
        
        if value >= 0:
            if getattr(config, "DEBUG_MODE", False):
                print(f"  [OCR] Spins lidos: {value}")
            _set_cached_ocr(cache_key, value)
            return value
        return -1
    except:
        return -1
