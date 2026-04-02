"""
Leitura de valores numéricos da tela via OCR (Tesseract).
Substituto leve ao EasyOCR para reduzir consumo de memória.

Dependências: pytesseract, Pillow
Requer Tesseract-OCR instalado no sistema.
"""

import re
import os
from PIL import Image, ImageEnhance

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


def _screenshot_to_pil(device) -> Image.Image:
    """Captura screenshot do dispositivo e retorna como PIL Image."""
    return device.screenshot()


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
    if not pytesseract:
        print("  [OCR] pytesseract não instalado.")
        return -1
    if not TESSERACT_CMD:
        print("  [OCR] Tesseract executável não encontrado. Instale o Tesseract-OCR.")
        return -1

    if not profile or not profile.get("coin_counter"):
        return -1
    
    region = profile["coin_counter"]["bounds_region"]
    
    try:
        img = _screenshot_to_pil(device)
        cropped = _crop_region(img, region, margin=10)
        processed = _preprocess_for_ocr(cropped)
        
        # Configuração para números apenas
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789,$'
        
        text = pytesseract.image_to_string(processed, config=custom_config)
        value = _extract_number(text)
        
        if value >= 0:
            print(f"  [OCR] Moedas lidas: {value}")
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
    try:
        img = _screenshot_to_pil(device)
        cropped = _crop_region(img, region, margin=5)
        processed = _preprocess_for_ocr(cropped)
        
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
        text = pytesseract.image_to_string(processed, config=custom_config)
        value = _extract_number(text)
        
        if value >= 0:
            print(f"  [OCR] Spins lidos: {value}")
            return value
        return -1
    except:
        return -1
