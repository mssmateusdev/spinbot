import cv2
import numpy as np
import os
import uiautomator2 as u2
import logging
import config

# Configuração de logs para o detector visual
logging.basicConfig(level=logging.DEBUG if getattr(config, "DEBUG_MODE", False) else logging.WARNING)
logger = logging.getLogger("VisualDetector")
logger.setLevel(logging.DEBUG if getattr(config, "DEBUG_MODE", False) else logging.WARNING)

# Caminho para os templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "assets", "templates")
_template_cache = {}


def _load_template(template_name: str):
    """Carrega templates uma vez; evita I/O de disco em cada polling visual."""
    if template_name in _template_cache:
        return _template_cache[template_name]
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(template_path):
        logger.debug(f"Template não encontrado: {template_path}")
        _template_cache[template_name] = None
        return None
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    _template_cache[template_name] = template
    return template

def find_template_on_screen(device: u2.Device, template_name: str, threshold: float = 0.7, roi=None):
    """
    Tenta localizar um template (ícone) na tela do dispositivo.
    :param device: Instância do uiautomator2
    :param template_name: Nome do arquivo (ex: 'close_x.png')
    :param threshold: Nível de confiança (0 a 1)
    :param roi: Region of Interest (x1, y1, x2, y2). Se None, busca na tela toda.
    :return: Coordenadas (x, y) do centro ou None
    """
    try:
        # 1. Carregar template
        template = _load_template(template_name)
        if template is None: return None
        th, tw = template.shape[:2]

        # 2. Capturar screenshot
        try:
            screenshot_pil = device.screenshot(ttl=getattr(config, "SCREENSHOT_CACHE_TTL", 0.35))
        except TypeError:
            screenshot_pil = device.screenshot()
        screenshot_np = np.array(screenshot_pil)
        
        # Converter RGB para BGR (OpenCV) e depois para Grayscale
        screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
        screen_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)

        # 3. Aplicar ROI se existir
        if roi:
            x1, y1, x2, y2 = roi
            screen_gray = screen_gray[y1:y2, x1:x2]
        else:
            x1, y1 = 0, 0

        # 4. Busca Multi-Escala (Otimizada)
        best_match = None
        best_val = -1
        
        # Testar escalas: 0.8x (menor), 1.0x (normal), 1.2x (maior)
        # Mais escalas aumentam precisão, mas custam CPU.
        for scale in [0.8, 1.0, 1.2]:
            if scale == 1.0:
                scaled_template = template
            else:
                new_w = int(tw * scale)
                new_h = int(th * scale)
                if new_w <= 10 or new_h <= 10: continue
                scaled_template = cv2.resize(template, (new_w, new_h))
            
            sth, stw = scaled_template.shape[:2]
            if sth > screen_gray.shape[0] or stw > screen_gray.shape[1]: continue
            
            res = cv2.matchTemplate(screen_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            if max_val > best_val:
                best_val = max_val
                best_match = (max_loc, stw, sth)

        if best_val >= threshold:
            max_loc, sw, sh = best_match
            # Calcular centro global
            cx = max_loc[0] + sw // 2 + x1
            cy = max_loc[1] + sh // 2 + y1
            logger.info(f"Sucesso: {template_name} encontrado (Escala {best_val:.2f}) em ({cx}, {cy})")
            return (cx, cy)
        
        return None

    except Exception as e:
        logger.error(f"Erro na detecção visual: {e}")
        return None

def click_visual_element(device: u2.Device, template_name: str, threshold: float = 0.7, roi=None) -> bool:
    """Tenta achar e clicar em um elemento visual usando Super Clique."""
    pos = find_template_on_screen(device, template_name, threshold, roi)
    if pos:
        pts = [(0, 0)]
        if getattr(config, "VISUAL_CROSS_TAP", False):
            pts.extend([(-2, 0), (2, 0), (0, -2), (0, 2)])
        for dx, dy in pts:
            tx, ty = pos[0] + dx, pos[1] + dy
            try:
                device.click(tx, ty)
            except Exception:
                device.shell(f"input tap {tx} {ty}")
        try:
            device.invalidate_ui_cache()
        except Exception:
            pass
        return True
    return False
