"""
Módulo de leitura de tela otimizado (v0.4.0).
Reduz tráfego ADB e processamento local para máxima velocidade.

v0.4.1 - CORREÇÕES ROBUSTAS:
- Estratégia em camadas para botões (Semântica → Ancestral → Texto+Ícone → Fallback)
- Normalização de texto (acentos, variações, maiúsculas/minúsculas)
- Detecção avançada de ancestral clicável
- Logs detalhados e tratamento de exceções
"""

import re
import time
import unicodedata
import uiautomator2 as u2
import config
import visual_detector
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ScreenReader")

# Cache local da hierarquia para evitar múltiplos dumps no mesmo ciclo
_last_hierarchy = None
_last_dump_time = 0


def normalize_text(text: str) -> str:
    """
    Normaliza texto para busca robusta:
    - Remove acentos
    - Converte para minúsculas
    - Remove espaços extras
    """
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'\s+', ' ', text)
    return text


def normalize_for_match(text: str) -> str:
    """Versão mais agressiva para matching."""
    return normalize_text(text).replace('í', 'i').replace('á', 'a').replace('é', 'e').replace('ó', 'o').replace('ú', 'u')


# Mapeamento de variações de texto comuns em botões
BUTTON_TEXT_VARIATIONS = {
    "continuar": ["continuar", "continue", "continuar2", "prosseguir", "avançar"],
    "confirmar": ["confirmar", "confirm", "ok", "sim", "yes"],
    "fechar": ["fechar", "close", "x", "×", "✕", "╳", "dismiss"],
    "pular": ["pular", "skip", "skip ad", "pular anúncio"],
    "retomar": ["retomar", "retomar vídeo", "retomar"],
}

class VirtualUiObject:
    """Wrapper robusto para simular UiObject com clique seguro."""
    
    def __init__(self, d, x1, y1, x2, y2, text="X", desc=""):
        self.d = d
        x1, y1, x2, y2 = max(0, x1), max(0, y1), max(0, x2), max(0, y2)
        self.info = {
            "bounds": {"left": x1, "top": y1, "right": x2, "bottom": y2},
            "text": text,
            "description": desc,
            "displayId": 0,
            "visibleBounds": {"left": x1, "top": y1, "right": x2, "bottom": y2}
        }
        self.center_x = (x1 + x2) // 2
        self.center_y = (y1 + y2) // 2
        self.selector = {"text": text}
        self._click_attempts = 0
        self._max_clicks = 3

    def _ensure_visible(self):
        """Garante que a área do elemento esteja visível na viewport."""
        try:
            w, h = self.d.window_size()
            x1 = self.info["bounds"]["left"]
            y1 = self.info["bounds"]["top"]
            x2 = self.info["bounds"]["right"]
            y2 = self.info["bounds"]["bottom"]
            
            # Se elemento está muito abaixo, rola a tela
            if y2 > h * 0.9:
                scroll_down = int((y2 - h * 0.7))
                self.d.shell(f"input swipe {w//2} {h//2} {w//2} {h//2 - scroll_down} 300")
                time.sleep(0.5)
                logger.debug(f"[CLICK] Scroll realizado para expor elemento")
        except Exception as e:
            logger.debug(f"[CLICK] Erro ao verificar visibilidade: {e}")

    def _check_overlay(self):
        """Verifica se há overlay bloqueando o clique (diálogos, ads, etc)."""
        try:
            xml = self.d.dump_hierarchy()
            
            # Verifica diálogos comuns que podem bloquear
            blockers = ["android.widget.PopupWindow", "android.app.Dialog", "android.widget.FrameLayout"]
            for blocker in blockers:
                if blocker in xml:
                    # Tenta encontrar o diálogo
                    dialog_match = re.search(r'<([^>]*?Dialog[^>]*?)>', xml, re.I)
                    if dialog_match:
                        logger.debug(f"[CLICK] Diálogo detectado potencialmente bloqueando")
                        return True
            
            return False
        except:
            return False

    def click(self, timeout=None, force=False):
        """
        Clique robusto com múltiplas tentativas e validações.
        
        Args:
            timeout: Tempo de espera (não usado, mant compatibility)
            force: Se True, força clique mesmo com overlays detectados
        
        Returns:
            bool: True se clique foi executado
        """
        import random
        
        for attempt in range(self._max_clicks):
            self._click_attempts += 1
            
            try:
                # Verifica visibilidade antes do clique
                self._ensure_visible()
                
                # Verifica overlays (a menos que force=True)
                if not force and self._check_overlay():
                    logger.warning(f"[CLICK] Overlay detectado, tentando pressionar BACK primeiro")
                    self.d.press("back")
                    time.sleep(0.5)
                    continue
                
                # Coordenadas com jitter humano
                tx = self.center_x + random.randint(-2, 2)
                ty = self.center_y + random.randint(-2, 2)
                
                # Método primário: ADB shell tap (mais eficaz contra ads sobrepostos)
                self.d.shell(f"input tap {tx} {ty}")
                logger.info(f"[CLICK] ✓ Clique executado em ({tx}, {ty}) [tentativa {attempt + 1}]")
                return True
                
            except Exception as e:
                logger.warning(f"[CLICK] Erro no clique primário: {e}")
                
                # Fallback 1: Driver do uiautomator2
                try:
                    self.d.click(self.center_x, self.center_y)
                    logger.info(f"[CLICK] ✓ Fallback driver executado")
                    return True
                except:
                    pass
                
                # Fallback 2: Clique por coordenadas via driver
                try:
                    self.d.shell(f"input tap {self.center_x} {self.center_y}")
                    return True
                except:
                    pass
        
        logger.error(f"[CLICK] ✗ Todas as {self._max_clicks} tentativas falharam")
        return False

    def click_center(self):
        """Clique simples no centro do elemento (alias para compatibilidade)."""
        return self.click()

    def exists(self, timeout=None):
        return True

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

def check_and_dismiss_warning_popup(d: u2.Device) -> bool:
    """Busca popups específicos de aviso do app (como 'Use all spins')."""
    xml = _get_cached_hierarchy(d, ttl=0.1)
    if not xml: return False
    
    # Checamos um texto mais curto para evitar falhas por quebra de linha (&#10;)
    if "Use all your spins" in xml or config.POPUP_WARNING_TEXT in xml:
        for text in config.POPUP_CLOSE_TEXTS:
            # Busca menos estrita: aceita content-desc e espaços dentro do atributo
            match = re.search(fr'(?:text|content-desc)="[^"]*{text}[^"]*"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml, re.I)
            if match:
                x1, y1, x2, y2 = map(int, match.groups())
                d.click((x1 + x2) // 2, (y1 + y2) // 2)
                return True
        d.press("back")
        return True
    return False

def check_and_dismiss_generic_close(d: u2.Device) -> bool:
    """Busca e fecha botões genéricos de CLOSE/FECHAR em qualquer lugar."""
    xml = _get_cached_hierarchy(d, ttl=0.2)
    if not xml: return False
    
    close_pattern = r'(?i)(?:text|content-desc)=".*(CLOSE|FECHAR|QUIT|CANCELAR|DISMISS).*"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    match = re.search(close_pattern, xml)
    if match:
        x1, y1, x2, y2 = map(int, match.groups()[1:])
        d.click((x1 + x2) // 2, (y1 + y2) // 2)
        return True
    
    # Fallback Visual (Abrangente para ambos os cantos superiores)
    w, h = d.window_size()
    # ROI: 15% superior da tela inteira
    roi_topo = (0, 0, w, int(h * 0.15))
    
    # 1. Tenta no lado DIREITO (Threshold normal)
    if visual_detector.click_visual_element(d, "close_x.png", threshold=0.85, roi=(int(w*0.5), 0, w, roi_topo[3])):
        return True
    
    # 2. Tenta no lado ESQUERDO (Threshold mais alto para evitar menus)
    if visual_detector.click_visual_element(d, "close_x.png", threshold=0.92, roi=(0, 0, int(w*0.5), roi_topo[3])):
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
    except Exception: pass

    return -1

def find_close_button(d: u2.Device, max_retries=3, timeout_per_retry=2.0):
    """
    Encontra botão de fechar/continuar/skip em anúncios.
    
    USA A NOVA LÓGICA ROBUSTA que evita o botão de voltar do sistema!
    
    FLUXO:
    1. Primeiro tenta clicar no ícone ao lado de "Continuar" (caso comum em SDKs de ads)
    2. Se falhar, usa a lógica padrão de busca do X
    """
    # ========== TENTATIVA ESPECIAL: Ícone ao lado de "Continuar" ==========
    logger.info("[FIND-CLOSE] Verificando botão 'Continuar' com ícone lateral...")
    
    # Verifica se existe texto "Continuar" na tela (variações maiúsculas/minúsculas)
    continuar_found = False
    for text_var in ["Continuar", "continuar", "CONTINUAR"]:
        if d(textContains=text_var).exists(timeout=0.3):
            continuar_found = True
            logger.info(f"[FIND-CLOSE] Texto '{text_var}' detectado!")
            break
    
    if continuar_found:
        logger.info("[FIND-CLOSE] ► Tentando clicar no ícone ao lado...")
        if click_icon_next_to_continuar(d, max_retries=2):
            logger.info("[FIND-CLOSE] ✓ Sucesso ao clicar no ícone ao lado de Continuar!")
            class FakeResult:
                def __init__(self):
                    self.info = {'text': 'Continuar-icon-clicked', 'description': 'continuar-icon'}
                    self.center_x = 0
                    self.center_y = 0
                def click(self, **kwargs):
                    return True
            return FakeResult()
        else:
            logger.warning("[FIND-CLOSE] ✗ Não foi possível clicar no ícone, tentando lógica padrão...")
    
    # ========== LÓGICA PADRÃO: Busca robusta do X de anúncio ==========
    return find_ad_close_button(d, max_retries=max_retries, timeout_per_retry=timeout_per_retry)


def find_ad_close_button(d: u2.Device, max_retries=3, timeout_per_retry=2.0):
    """
    NOVA LÓGICA ROBUSTA para encontrar o botão "X" de fechar anúncios.
    
    DIFERENÇA CRÍTICA: Evita clicar no botão de voltar do sistema!
    
    Estratégia em camadas:
    1. Busca por content-desc específico de fechar
    2. Busca por resource-id de botão de fechar
    3. Busca por texto em container clicável (NÃO texto solto)
    4. Heurística: menor bounding box no canto direito do anúncio
    5. Fallback visual (após validar que não é botão do sistema)
    
    Args:
        d: Instância uiautomator2
        max_retries: Tentativas
        timeout_per_retry: Timeout por tentativa
    
    Returns:
        VirtualUiObject ou None
    """
    logger.info("[AD-X-BUTTON] ========== NOVA LÓGICA: Busca robusta do X de anúncio ==========")
    
    for attempt in range(max_retries):
        logger.info(f"[AD-X-BUTTON] Tentativa {attempt + 1}/{max_retries}")
        
        try:
            # Obtém hierarquia e tamanho da tela
            xml = _get_cached_hierarchy(d, ttl=0.05)
            if not xml:
                time.sleep(0.3)
                continue
                
            w, h = d.window_size()
            
            # ===== CAMADA 1: Buscar por content-desc específico =====
            result = _find_x_by_content_desc(d, xml, w, h)
            if result:
                logger.info("[AD-X-BUTTON] ✓ Camada 1: Encontrado por content-desc")
                return result
            
            # ===== CAMADA 2: Buscar por resource-id específico =====
            result = _find_x_by_resource_id(d, xml, w, h)
            if result:
                logger.info("[AD-X-BUTTON] ✓ Camada 2: Encontrado por resource-id")
                return result
            
            # ===== CAMADA 3: Buscar por texto em container clicável =====
            result = _find_x_by_text_in_clickable(d, xml, w, h)
            if result:
                logger.info("[AD-X-BUTTON] ✓ Camada 3: Encontrado por texto em container clicável")
                return result
            
            # ===== CAMADA 4: Heurística de posição (menor no canto direito) =====
            result = _find_x_by_position_heuristic(d, xml, w, h)
            if result:
                logger.info("[AD-X-BUTTON] ✓ Camada 4: Encontrado por heurística de posição")
                return result
            
            # ===== CAMADA 5: Fallback visual =====
            result = _find_x_visual_fallback(d, w, h)
            if result:
                logger.info("[AD-X-BUTTON] ✓ Camada 5: Encontrado por fallback visual")
                return result
            
        except Exception as e:
            logger.error(f"[AD-X-BUTTON] Erro na tentativa {attempt + 1}: {e}")
        
        time.sleep(timeout_per_retry * (attempt + 1) / 3)
    
    logger.error("[AD-X-BUTTON] ✗ Todas as tentativas esgotadas")
    return None


def _is_system_button(d: u2.Device, x1: int, y1: int, x2: int, y2: int, xml: str) -> bool:
    """
    VERIFICA SE O BOTÃO É DO SISTEMA (botão de voltar nativo).
    
    Regras de bloqueio:
    1. Se resource-id contém: back, navigateUp, system, android:id/
    2. Se está na barra de navegação (Y muito pequeno, típico da navbar)
    3. Se não tem ancestral clicável (é elemento solto do sistema)
    4. Se está em região de navegação do sistema
    """
    try:
        w, h = d.window_size()
        
        # Regra 1: Coordenadas típicas da navbar do Android
        # A navbar do sistema fica nos primeiros ~80dp da tela
        navbar_threshold = int(h * 0.04)  # ~4% da altura
        
        # Botões do sistema geralmente estão muito próximos às bordas
        if y1 < navbar_threshold and x1 < int(w * 0.15):
            # Possível botão de voltar (canto inferior/esquerdo ou topo)
            # Vamos verificar se é realmente da navbar
            logger.debug(f"[SYSTEM-CHECK] Posição suspeita: Y={y1} < {navbar_threshold} (navbar threshold)")
            return True
        
        # Regra 2: Verificar resource-id
        # Procura se este elemento tem um id de sistema
        element_pattern = rf'bounds="\[{x1},{y1}\]\[{x2},{y2}\]"[^>]*?resource-id="([^"]*)"'
        match = re.search(element_pattern, xml)
        if match:
            rid = match.group(1).lower()
            system_id_patterns = ['back', 'navigateup', 'navigate_up', 'home', 'system', 
                                  'android:id/', 'action_bar', 'toolbar', 'navigation']
            if any(p in rid for p in system_id_patterns):
                logger.debug(f"[SYSTEM-CHECK] ID de sistema detectado: {rid}")
                return True
        
        # Regra 3: Verificar se está dentro de apppackage (não é do sistema)
        # O anúncio deve estar no pacote do app ou em webview
        # Se o elemento é filhos directos de decorView ou similar, é do sistema
        if 'android.widget.FrameLayout' in xml and 'id/content' in xml:
            # Verifica se está na hierarquia do sistema
            pass  # дальше
        
        return False
        
    except Exception as e:
        logger.debug(f"[SYSTEM-CHECK] Erro: {e}")
        return False  # Em caso de dúvida, não bloquear


def _find_x_by_content_desc(d: u2.Device, xml: str, w: int, h: int):
    """CAMADA 1: Busca por content-desc contendo palavras de fechar."""
    try:
        # Padrões específicos para botão de fechar
        close_patterns = [
            'close', 'fechar', 'dismiss', 'exit', 'x', '×', '✕', 'cancel',
            'ad_close', 'close_ad', 'btn_close', 'close_btn', 'close_button',
            'skip', 'next', 'forward', '>', '>|', '>>', '>i', '>l'
        ]
        
        # Regex para encontrar elementos com content-desc
        desc_regex = r'<node[^>]*?content-desc="([^"]*?)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        
        candidates = []
        for match in re.finditer(desc_regex, xml, re.IGNORECASE):
            content_desc = match.group(1).lower()
            x1, y1, x2, y2 = map(int, match.groups()[2:])
            
            # Verifica se o content-desc contém alguma palavra de fechar
            if any(p in content_desc for p in close_patterns):
                # Valida que NÃO é botão do sistema
                if not _is_system_button(d, x1, y1, x2, y2, xml):
                    candidates.append({
                        'text': match.group(1),
                        'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                        'width': x2 - x1,
                        'height': y2 - y1,
                        'area': (x2 - x1) * (y2 - y1)
                    })
                    logger.debug(f"[LAYER1] Content-desc válido: '{content_desc}' em ({x1},{y1})-({x2},{y2})")
        
        if candidates:
            # Prioriza: menor área (botão mais provável de ser X)
            candidates.sort(key=lambda x: x['area'])
            best = candidates[0]
            logger.info(f"[LAYER1] Selecionado: área={best['area']}, texto='{best['text']}'")
            return VirtualUiObject(d, best['x1'], best['y1'], best['x2'], best['y2'], 
                                   text=best['text'], desc=best['text'])
            
    except Exception as e:
        logger.error(f"[LAYER1] Erro: {e}")
    return None


def _find_x_by_resource_id(d: u2.Device, xml: str, w: int, h: int):
    """CAMADA 2: Busca por resource-id específico de botão de fechar."""
    try:
        # IDs que indicam botão de fechar de anúncio
        close_rids = [
            'close', 'dismiss', 'skip', 'close_ad', 'ad_close', 'btn_close', 
            'close_button', 'closebtn', 'iv_close', 'img_close', 'icon_close',
            'close_icon', 'closeImage', 'ad_close', 'interstitial_close'
        ]
        
        rid_pattern = '|'.join(close_rids)
        rid_regex = rf'resource-id="[^"]*?({rid_pattern})[^"]*"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        
        candidates = []
        for match in re.finditer(rid_regex, xml, re.IGNORECASE):
            rid = match.group(1)
            x1, y1, x2, y2 = map(int, match.groups()[2:])
            
            # Valida que NÃO é botão do sistema
            if not _is_system_button(d, x1, y1, x2, y2, xml):
                candidates.append({
                    'rid': rid,
                    'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                    'area': (x2 - x1) * (y2 - y1)
                })
                logger.debug(f"[LAYER2] ID válido: {rid} em ({x1},{y1})-({x2},{y2})")
        
        if candidates:
            candidates.sort(key=lambda x: x['area'])
            best = candidates[0]
            logger.info(f"[LAYER2] Selecionado por ID: {best['rid']}")
            return VirtualUiObject(d, best['x1'], best['y1'], best['x2'], best['y2'], 
                                   desc=best['rid'])
            
    except Exception as e:
        logger.error(f"[LAYER2] Erro: {e}")
    return None


def _find_x_by_text_in_clickable(d: u2.Device, xml: str, w: int, h: int):
    """
    CAMADA 3: Busca texto de fechar DENTRO de um container clicável.
    
    CRÍTICO: O texto "X" ou "Fechar" deve estar DENTRO de um elemento clicável,
    não solto no layout. Isso evita capturar elementos do sistema.
    """
    try:
        close_texts = ['x', '×', '✕', 'close', 'fechar', 'dismiss', 'skip', 'next', 'forward', '>', '>|', '>>', '>i', '>l']
        
        # Primeiro, encontra todos os containers clicáveis
        clickable_containers = {}
        for match in re.finditer(r'<node[^>]*?clickable="true"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
            cx1, cy1, cx2, cy2 = map(int, match.groups())
            clickable_containers[(cx1, cy1, cx2, cy2)] = match.group(0)
        
        # Agora busca textos de fechar que estejam DENTRO desses containers
        for text_match in re.finditer(r'<node[^>]*?text="([^"]*?)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
            text = text_match.group(1).lower()
            tx1, ty1, tx2, ty2 = map(int, text_match.groups()[2:])
            
            match_found = False
            for t in close_texts:
                if t in ['>', '>|', '>>', '>i', '>l']:
                    if t == text.strip():
                        match_found = True
                        break
                elif t in text:
                    match_found = True
                    break
            if match_found:
                # Verifica se está dentro de um container clicável
                for (cx1, cy1, cx2, cy2), container_xml in clickable_containers.items():
                    if cx1 <= tx1 and cy1 <= ty1 and cx2 >= tx2 and cy2 >= ty2:
                        # Está dentro de um container clicável - VALIDAR
                        if not _is_system_button(d, cx1, cy1, cx2, cy2, xml):
                            logger.info(f"[LAYER3] Texto '{text}' encontrado em container clicável ({cx1},{cy1})-({cx2},{cy2})")
                            return VirtualUiObject(d, cx1, cy1, cx2, cy2, text=text)
                
                # Se o texto está solto (sem container clicável), mas é clicável diretamente
                if "clickable=\"true\"" in text_match.group(0):
                    if not _is_system_button(d, tx1, ty1, tx2, ty2, xml):
                        logger.info(f"[LAYER3] Texto '{text}' clicável direto")
                        return VirtualUiObject(d, tx1, ty1, tx2, ty2, text=text)
        
    except Exception as e:
        logger.error(f"[LAYER3] Erro: {e}")
    return None


def _find_x_by_position_heuristic(d: u2.Device, xml: str, w: int, h: int):
    """
    CAMADA 4: Heurística de posição.
    
    O X do anúncio tipicamente:
    - Está no canto direito superior (mas não na navbar)
    - Tem bounding box pequeno (20-80dp)
    - Está dentro de um container de anúncio
    """
    try:
        # Área válida para X de anúncio: 
        # - Direita da tela (X > 70% da largura)
        # - Acima de 5% da tela (acima da navbar)
        # - Abaixo de 30% da tela (não é da status bar)
        
        valid_x_region = int(w * 0.70)  # X deve estar após 70% da largura
        min_y = int(h * 0.05)  # Acima de 5% da altura (evita navbar)
        max_y = int(h * 0.35)  # Abaixo de 35% da altura
        
        # Busca todos os elementos clicáveis
        all_clickables = re.findall(
            r'<node[^>]*?clickable="true"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml
        )
        
        candidates = []
        for cb in all_clickables:
            cx1, cy1, cx2, cy2 = map(int, cb)
            
            # Valida região válida
            if cx1 < valid_x_region:
                continue  # Não está na região direita
            if cy1 < min_y or cy2 > max_y:
                continue  # Fora da faixa vertical válida
                
            # Valida que não é botão do sistema
            if _is_system_button(d, cx1, cy1, cx2, cy2, xml):
                continue
            
            # Calcula área (X típico é pequeno)
            area = (cx2 - cx1) * (cy2 - cy1)
            width = cx2 - cx1
            height = cy2 - cy1
            
            # X típico: pequeno (menos de 100dp de área) e aproximadamente quadrado
            if area < 10000 and width < 150 and height < 150:
                candidates.append({
                    'x1': cx1, 'y1': cy1, 'x2': cx2, 'y2': cy2,
                    'area': area,
                    'center_x': (cx1 + cx2) // 2
                })
        
        if candidates:
            # Prioriza o mais à direita (mais provável de ser X de anúncio)
            candidates.sort(key=lambda x: (-x['center_x'], x['area']))
            best = candidates[0]
            logger.info(f"[LAYER4] Heurística: candidato ({best['x1']},{best['y1']})-({best['x2']},{best['y2']}) área={best['area']}")
            return VirtualUiObject(d, best['x1'], best['y1'], best['x2'], best['y2'], text="Heuristic-X")
        
    except Exception as e:
        logger.error(f"[LAYER4] Erro: {e}")
    return None


def _find_x_visual_fallback(d: u2.Device, w: int, h: int):
    """
    CAMADA 5: Fallback visual para detectar X quando nenhuma outra camada funcionou.
    
    ÚLTIMO RECURSO - só executa após validar que não há botão do sistema.
    """
    try:
        # ROI: Canto superior direito (onde обычно fica o X de anúncio)
        # Evita a região da navbar do sistema
        roi_x = (int(w * 0.60), int(h * 0.08), w, int(h * 0.30))
        
        # Tenta template de X
        pos = visual_detector.find_template_on_screen(
            d, "close_x.png", threshold=0.80, roi=roi_x
        )
        
        # Se não achou o X, tenta pelo novo ícone de "Pular" (>|)
        if not pos:
            pos = visual_detector.find_template_on_screen(
                d, "skip_icon.png", threshold=0.80, roi=roi_x
            )
            
        if pos:
            # Valida que a posição não é na navbar (Y muito pequeno)
            if pos[1] > int(h * 0.05):  # Acima de 5% da tela
                logger.info(f"[LAYER5] Visual fallback: Ícone (X ou Skip) encontrado em ({pos[0]}, {pos[1]})")
                return VirtualUiObject(d, pos[0]-25, pos[1]-25, pos[0]+25, pos[1]+25, text="Visual-X-Skip")
        
    except Exception as e:
        logger.error(f"[LAYER5] Erro: {e}")
    return None


# ============================================================
# FUNÇÃO ESPECIAL: CLIQUE NO ÍCONE AO LADO DO BOTÃO "CONTINUAR"
# ============================================================

def click_icon_next_to_continuar(d: u2.Device, max_retries=2):
    """
    Clica EXATAMENTE no ícone '>|' que fica ao lado direito do texto 'Continuar',
    calculando as relativas posições sem precisar de template de imagem!
    """
    logger.info("[CONTINUAR-ICON] Calculando posição do ícone ao lado de 'Continuar'...")
    for attempt in range(max_retries):
        try:
            continuar_texts = [
                "Continuar", "continuar", "CONTINUAR", 
                "Continue", "continue", "CONTINUE",
                "seg. até o", "até o prêmio", "reward in", "seconds"
            ]
            continuar_elem = None
            
            for text in continuar_texts:
                elem = d(textContains=text)
                if elem.exists(timeout=0.3):
                    continuar_elem = elem
                    logger.info(f"[CONTINUAR-ICON] ✓ Texto/Timer '{text}' encontrado na tela.")
                    break
            
            if not continuar_elem:
                continue
            
            # Obter coordenadas APENAS da caixa de texto
            cont_info = continuar_elem.info
            cont_bounds = cont_info.get('bounds', {})
            cont_x = cont_bounds.get('left', 0)
            cont_y = cont_bounds.get('top', 0)
            cont_right = cont_bounds.get('right', 0)
            cont_bottom = cont_bounds.get('bottom', 0)
            
            # A altura real do texto ajuda a estimar a proporção do botão
            height = cont_bottom - cont_y
            
            # O ÍCONE está FORA e à DIREITA da palavra Continuar.
            # O texto acaba em "cont_right". O ícone circular tem aproximadamente a mesma altura da caixa.
            # Então se saltarmos metade ou até a altura completa para a direita,
            # cairemos exatamente no meio do círculo branco com o símbolo >| !
            offset_x = int(height * 0.9) # Pulo para a direita do texto baseado na altura
            
            tap_x = cont_right + offset_x
            tap_y = (cont_y + cont_bottom) // 2
            
            logger.info(f"[CONTINUAR-ICON] Texto termina em X={cont_right}. Clicando NO ÍCONE circular em X={tap_x}, Y={tap_y}")
            d.shell(f"input tap {tap_x} {tap_y}")
            return True
            
        except Exception as e:
            logger.error(f"[CONTINUAR-ICON] Erro na lógica de posição: {e}")
            time.sleep(0.5)
            
    logger.error("[CONTINUAR-ICON] ✗ Não foi possível calcular ou clicar no ícone ao lado de Continuar.")
    return False


def _find_small_clickable_elements(xml: str, ref_x: float, ref_y: float):
    """
    FALLBACK: Encontra qualquer elemento pequeno clicável na tela.
    
    Útil quando o anúncios está em WebView ou estrutura XML diferente.
    
    Args:
        xml: Hierarquia XML
        ref_x: Coordenada X de referência (centro do texto Continuar)
        ref_y: Coordenada Y de referência (centro do texto Continuar)
    
    Returns:
        Lista de candidatos ordenados por distância
    """
    candidates = []
    
    # Encontrar todos os elementos clicáveis
    clickable_regex = r'<node[^>]*?clickable="true"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    
    for match in re.finditer(clickable_regex, xml):
        x1, y1, x2, y2 = map(int, match.groups())
        w = x2 - x1
        h = y2 - y1
        
        # Só considera elementos pequenos (possíveis ícones)
        if w > 5 and h > 5 and w < 150 and h < 150:
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            distance = ((center_x - ref_x)**2 + (center_y - ref_y)**2)**0.5
            
            candidates.append({
                'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                'w': w, 'h': h,
                'center_x': center_x, 'center_y': center_y,
                'area': w * h,
                'distance': distance,
                'is_clickable': True,
                'elem_str': match.group(0)
            })
    
    # Ordena por distância
    candidates.sort(key=lambda x: x['distance'])
    return candidates

def find_robust_action_button(d: u2.Device, patterns=None, max_retries=3, timeout_per_retry=2.0):
    """
    Implementação da Estratégia de Busca em Camadas (Layered Strategy) ROBUSTA.
    
    Focada em:
    - Estabilidade: retry com timeout progressivo
    - Acessibilidade: role, aria, text normalizado
    - Ancestral clicável: sobe para container pai quando necessário
    - Texto + Ícone: detecta ambos como parte do mesmo botão
    - Fallback visual: último recurso
    
    Args:
        d: Instância do uiautomator2
        patterns: Lista de padrões de texto para buscar (default: Common button texts)
        max_retries: Número máximo de tentativas
        timeout_per_retry: Timeout base por tentativa (aumenta progressivamente)
    
    Returns:
        VirtualUiObject ou None
    """
    if patterns is None:
        patterns = ["continuar", "confirmar", "próximo", "next", "ok", "entendi", "fechar", "pular", "skip"]
    
    # Log de início
    logger.info(f"[ROBUST-BUTTON] Iniciando busca por: {patterns}")
    
    # Retry com timeout progressivo
    for attempt in range(max_retries):
        attempt_start = time.time()
        timeout = timeout_per_retry * (attempt + 1)  # Progressivo: 2s, 4s, 6s
        
        logger.info(f"[ROBUST-BUTTON] Tentativa {attempt + 1}/{max_retries} (timeout: {timeout}s)")
        
        while (time.time() - attempt_start) < timeout:
            if d.app_current().get("package") != config.APP_PACKAGE:
                logger.warning("[ROBUST-BUTTON] App mudou durante busca, abortando")
                return None
            
            # ===== CAMADA 1: Busca Semântica e Acessível =====
            result = _layer1_semantic_search(d, patterns)
            if result:
                logger.info(f"[ROBUST-BUTTON] ✓ Camada 1: Encontrado via busca semântica")
                return result
            
            # ===== CAMADA 2: Ancestral Clicável (Parent Climbing) =====
            result = _layer2_parent_climbing(d, patterns)
            if result:
                logger.info(f"[ROBUST-BUTTON] ✓ Camada 2: Encontrado via ancestral clicável")
                return result
            
            # ===== CAMADA 3: Texto + Ícone no mesmo container =====
            result = _layer3_text_icon_container(d, patterns)
            if result:
                logger.info(f"[ROBUST-BUTTON] ✓ Camada 3: Encontrado via texto+ícone")
                return result
            
            # Pequena pausa antes de retry
            time.sleep(0.3)
        
        logger.warning(f"[ROBUST-BUTTON] Tentativa {attempt + 1} expirou, tentando novamente...")
    
    # ===== CAMADA 4: Fallback Robusto (IDs e Visual) =====
    logger.info("[ROBUST-BUTTON] Tentando fallback (IDs + Visual)...")
    result = _layer4_fallback(d)
    if result:
        logger.info(f"[ROBUST-BUTTON] ✓ Camada 4: Encontrado via fallback")
        return result
    
    logger.error(f"[ROBUST-BUTTON] ✗ Botão não encontrado após {max_retries} tentativas")
    return None


def _layer1_semantic_search(d: u2.Device, patterns):
    """
    CAMADA 1: Busca semântica por texto, description, content-desc normalizados.
    """
    try:
        xml = _get_cached_hierarchy(d, ttl=0.05)
        if not xml:
            logger.debug("[LAYER1] XML vazio")
            return None
        
        for p in patterns:
            norm_pattern = normalize_for_match(p)
            
            # Busca por texto ou description normalizado
            # Aceita variações: maiúsculas/minúsculas, acentos
            regex = rf'<(node|view)[^>]*?(?:text|content-desc)="([^"]*?)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?>'
            
            for match in re.finditer(regex, xml, re.IGNORECASE):
                full_text = match.group(2)
                norm_text = normalize_for_match(full_text)
                
                # Verifica se o texto contém o padrão (permite variações)
                if norm_pattern in norm_text or norm_text in norm_pattern:
                    x1, y1, x2, y2 = map(int, match.groups()[2:])
                    
                    # Verifica se o elemento já é clicável
                    node_start = match.start()
                    node_end = xml.find('>', node_start)
                    node_str = xml[node_start:node_end]
                    
                    if "clickable=\"true\"" in node_str:
                        # Já é clicável, retorna com margem para ícone
                        logger.debug(f"[LAYER1] Encontrado clicável: '{full_text}' em ({x1},{y1})-({x2},{y2})")
                        return VirtualUiObject(d, x1, y1, x2 + 50, y2, text=f"Layer1-{full_text}")
                    else:
                        # Não clicável, marca para subir no parent
                        logger.debug(f"[LAYER1] Texto encontrado, mas não clicável: '{full_text}'")
                        return None  # Irá para camada 2
        
    except Exception as e:
        logger.error(f"[LAYER1] Erro: {e}")
    
    return None


def _layer2_parent_climbing(d: u2.Device, patterns):
    """
    CAMADA 2: Busca texto e sobe para ancestral clicável.
    """
    try:
        xml = _get_cached_hierarchy(d, ttl=0.05)
        if not xml:
            return None
        
        for p in patterns:
            norm_pattern = normalize_for_match(p)
            
            # Regex para encontrar elemento com texto
            regex = rf'(<node[^>]*?(?:text|content-desc)="([^"]*?)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?>)'
            
            for match in re.finditer(regex, xml, re.IGNORECASE):
                full_match = match.group(1)
                full_text = match.group(2)
                x1, y1, x2, y2 = map(int, match.groups()[3:])
                
                norm_text = normalize_for_match(full_text)
                if norm_pattern not in norm_text and norm_text not in norm_pattern:
                    continue
                
                # Verifica se o elemento é clicável
                if "clickable=\"true\"" in full_match:
                    logger.debug(f"[LAYER2] Elemento já clicável: '{full_text}'")
                    return VirtualUiObject(d, x1, y1, x2 + 50, y2, text=f"Layer2-{full_text}")
                
                # Precisa subir para ancestral clicável
                pos = match.start()
                
                # Busca container pai clicável nas proximidades (2000 chars antes)
                prefix = xml[max(0, pos-2000):pos]
                
                # Encontra todos os nós clicáveis no prefixo
                parent_regex = r'<node[^>]*?clickable="true"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
                parents = list(re.finditer(parent_regex, prefix))
                
                if parents:
                    # Pega o último (mais próximo do texto)
                    px1, py1, px2, py2 = map(int, parents[-1].groups())
                    
                    # Valida que o parent envolve o texto (y1 deve estar entre py1 e py2)
                    if py1 <= y1 <= py2:
                        # Expande para direita para incluir ícone (comum em botões "Continuar" com ícone)
                        expand_right = 80 if (px2 - px1) < 150 else 30
                        logger.debug(f"[LAYER2] Ancestral clicável encontrado: texto='{full_text}' parent=({px1},{py1})-({px2},{py2})")
                        return VirtualUiObject(d, px1, py1, px2 + expand_right, py2, text=f"Layer2-Parent-{full_text}")
        
    except Exception as e:
        logger.error(f"[LAYER2] Erro: {e}")
    
    return None


def _layer3_text_icon_container(d: u2.Device, patterns):
    """
    CAMADA 3: Detecta texto + ícone no mesmo container visual.
    Específico parabotões como "Continuar" com ícone circular à direita.
    """
    try:
        xml = _get_cached_hierarchy(d, ttl=0.05)
        if not xml:
            return None
        
        # Busca por container que contenha tanto texto quanto possíveis ícones
        # Um botão típico com ícone tem: text="Continuar" +filhos com drawable/bitmap
        
        for p in patterns:
            norm_pattern = normalize_for_match(p)
            
            # Encontra o nó com o texto
            text_regex = rf'<(node|view)[^>]*?(?:text|content-desc)="([^"]*?)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            
            for text_match in re.finditer(text_regex, xml, re.IGNORECASE):
                full_text = text_match.group(2)
                x1, y1, x2, y2 = map(int, text_match.groups()[3:])
                
                norm_text = normalize_for_match(full_text)
                if norm_pattern not in norm_text and norm_text not in norm_pattern:
                    continue
                
                # O nó de texto pode ser interno - busca o container pai mais próximo
                pos = text_match.start()
                
                # Procura container que contenha o texto e seja "grande o suficiente" para ter ícone
                prefix = xml[max(0, pos-2500):pos]
                
                # Encontra containers que englobam o texto (clickable ou não, mas com bounds adequados)
                container_regex = r'<node[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
                
                candidates = []
                for c_match in re.finditer(container_regex, prefix):
                    cx1, cy1, cx2, cy2 = map(int, c_match.groups())
                    # Container precisa envolver o texto E ser largo o suficiente para ícone
                    if cx1 <= x1 and cy1 <= y1 and cy2 >= y2 and (cx2 - cx1) > 80:
                        candidates.append((c_match, cx1, cy1, cx2, cy2))
                
                if candidates:
                    # Pega o menor container que ainda engloba (mais próximo)
                    candidates.sort(key=lambda x: (x[2], x[3]-x[1]))  # Ordena por y1, depois por largura
                    cx1, cy1, cx2, cy2 = candidates[0][1:]
                    logger.debug(f"[LAYER3] Container texto+ícone: texto='{full_text}' container=({cx1},{cy1})-({cx2},{cy2})")
                    return VirtualUiObject(d, cx1, cy1, cx2 + 20, cy2, text=f"Layer3-Container-{full_text}")
        
    except Exception as e:
        logger.error(f"[LAYER3] Erro: {e}")
    
    return None


def _layer4_fallback(d: u2.Device):
    """
    CAMADA 4: Fallback robusto - IDs conhecidos e detecção visual.
    """
    try:
        xml = _get_cached_hierarchy(d, ttl=0.05)
        if not xml:
            return None
        
        # === IDs conhecidos e estáveis ===
        common_rids = [
            "close_button", "dismiss", "btn_close", "interstitial", "skip",
            "button_continue", "btn_continue", "continue_button", 
            "next_button", "btn_next", "primary_button", "cta_button"
        ]
        
        rid_regex = r'resource-id="[^"]*?(' + '|'.join(common_rids) + r')[^"]*"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        rid_match = re.search(rid_regex, xml, re.IGNORECASE)
        
        if rid_match:
            x1, y1, x2, y2 = map(int, rid_match.groups()[1:])
            logger.info(f"[LAYER4] Encontrado por ID: {rid_match.group(1)}")
            return VirtualUiObject(d, x1, y1, x2, y2, desc=rid_match.group(1))
        
        # === Busca por elementos com clickable + long-clickable ===
        clickable_regex = r'<node[^>]*?clickable="true"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?text="([^"]*)"'
        click_match = re.search(clickable_regex, xml)
        if click_match:
            # Verifica se tem texto relevante
            text = click_match.group(5)
            if text and len(text) > 2:
                x1, y1, x2, y2 = map(int, click_match.groups()[:4])
                logger.info(f"[LAYER4] Encontrado clicável com texto: '{text}'")
                return VirtualUiObject(d, x1, y1, x2, y2, text=text)
        
        # === Fallback Visual ===
        w, h = d.window_size()
        roi_topo = (0, 0, w, int(h * 0.25))
        
        # Tenta ícones conhecidos
        for template_name, threshold in [("skip_next.png", 0.70), ("continue_arrow.png", 0.70), ("close_x.png", 0.85)]:
            pos = visual_detector.find_template_on_screen(d, template_name, threshold=threshold, roi=roi_topo)
            if pos:
                logger.info(f"[LAYER4] Encontrado visual: {template_name}")
                # Margem para clicar no centro do ícone
                return VirtualUiObject(d, pos[0]-50, pos[1]-30, pos[0]+50, pos[1]+30, text=f"Visual-{template_name}")
        
        # === Fallback extremo: qualquer botão clicável na área ===
        # Busca o maior botão clicável no terço superior da tela
        w, h = d.window_size()
        all_clickables = re.findall(
            r'<node[^>]*?clickable="true"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml
        )
        
        if all_clickables:
            candidates = []
            for cb in all_clickables:
                cx1, cy1, cx2, cy2 = map(int, cb)
                if cy2 < h * 0.4:  # No terço superior
                    area = (cx2 - cx1) * (cy2 - cy1)
                    candidates.append((area, cx1, cy1, cx2, cy2))
            
            if candidates:
                candidates.sort(reverse=True)
                _, cx1, cy1, cx2, cy2 = candidates[0]
                logger.info(f"[LAYER4] Fallback extremo: maior clicável na área")
                return VirtualUiObject(d, cx1, cy1, cx2, cy2, text="Fallback-Clickable")
        
    except Exception as e:
        logger.error(f"[LAYER4] Erro: {e}")
    
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
    except Exception:
        pass
    return 0


# ============================================================
# FUNÇÕES DE DEBUG E DIAGNÓSTICO
# ============================================================

def debug_print_hierarchy(d: u2.Device, max_lines: int = 50):
    """
    Imprime a hierarquia XML atual para debug.
    Útil para entender a estrutura da UI e desenvolver seletores.
    """
    try:
        xml = d.dump_hierarchy()
        lines = xml.split('\n')[:max_lines]
        print("=" * 60)
        print("HIERARQUIA UI (primeiras linhas):")
        print("=" * 60)
        for i, line in enumerate(lines, 1):
            print(f"{i:3}: {line[:150]}...")
        print("=" * 60)
    except Exception as e:
        print(f"Erro ao obter hierarquia: {e}")


def debug_find_all_buttons(d: u2.Device) -> list:
    """
    Encontra todos os elementos clicáveis na tela para debug.
    Retorna lista com informações de cada elemento.
    """
    results = []
    try:
        xml = _get_cached_hierarchy(d, ttl=0)
        if not xml:
            return results
        
        # Encontra todos os elementos clicáveis
        clickable_regex = r'<node[^>]*?(?:text|content-desc)="([^"]*?)"[^>]*?clickable="true"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        
        for match in re.finditer(clickable_regex, xml, re.I):
            text = match.group(1)
            x1, y1, x2, y2 = map(int, match.groups()[1:])
            
            if text and len(text.strip()) > 0:
                results.append({
                    'text': text,
                    'bounds': f"({x1},{y1})-({x2},{y2})",
                    'center': ((x1+x2)//2, (y1+y2)//2)
                })
        
        # Também pega os não clicáveis que têm texto relevante
        text_regex = r'<node[^>]*?(?:text|content-desc)="([^"]*?)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        
        for match in re.finditer(text_regex, xml, re.I):
            text = match.group(1)
            if not text or len(text.strip()) < 2:
                continue
                
            # Verifica se já está na lista
            if any(r['text'] == text for r in results):
                continue
                
            # Verifica se contém palavras de botão
            button_keywords = ['continuar', 'fechar', 'ok', 'sim', 'não', 'cancelar', 
                               'pular', 'skip', 'close', 'next', 'confirmar', 'voltar']
            if any(kw in normalize_for_match(text) for kw in button_keywords):
                x1, y1, x2, y2 = map(int, match.groups()[1:])
                results.append({
                    'text': text,
                    'bounds': f"({x1},{y1})-({x2},{y2})",
                    'center': ((x1+x2)//2, (y1+y2)//2),
                    'note': 'texto relevante (não clicável)'
                })
                
    except Exception as e:
        logger.error(f"[DEBUG] Erro: {e}")
    
    return results


def debug_test_button_detection(d: u2.Device) -> dict:
    """
    Testa a detecção de botão e retorna relatório detalhado.
    Útil para validar se os algoritmos estão funcionando.
    """
    report = {
        'timestamp': time.strftime("%H:%M:%S"),
        'all_buttons': debug_find_all_buttons(d),
        'robust_result': None,
        'close_button_result': None
    }
    
    # Testa a função robusta
    robust_btn = find_robust_action_button(d, max_retries=1, timeout_per_retry=0.5)
    if robust_btn:
        report['robust_result'] = {
            'text': robust_btn.info.get('text'),
            'bounds': robust_btn.info.get('bounds'),
            'center': (robust_btn.center_x, robust_btn.center_y)
        }
    
    # Testa find_close_button
    close_btn = find_close_button(d, max_retries=1, timeout_per_retry=0.5)
    if close_btn:
        report['close_button_result'] = {
            'text': close_btn.info.get('text'),
            'bounds': close_btn.info.get('bounds'),
            'center': (close_btn.center_x, close_btn.center_y)
        }
    
    return report
