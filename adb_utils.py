"""
Módulo de utilidades para interação com o dispositivo Android.
Usa uiautomator2 para conexão e interações com a UI.
"""

import os
import random
import threading
import time
import uiautomator2 as u2
import adbutils
import sys
from colorama import Fore, Style

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Configurar caminho do ADB globalmente
_adb_bin = resource_path("adb.exe")
if os.path.exists(_adb_bin):
    adbutils.adb_path = _adb_bin


import config


_adb_client_lock = threading.Lock()
_adb_client = None
_device_sessions = {}


def _get_adb_client():
    """Reutiliza o cliente adbutils para evitar recriar conexões locais ao servidor ADB."""
    global _adb_client
    with _adb_client_lock:
        if _adb_client is None:
            _adb_client = adbutils.AdbClient()
        return _adb_client


class ManagedUiObject:
    """Proxy fino para objetos de seletor uiautomator2 com invalidação após clique."""

    def __init__(self, device, obj):
        self._managed_device = device
        self._obj = obj

    def __getattr__(self, name):
        return getattr(self._obj, name)

    def click(self, *args, **kwargs):
        return self._managed_device._call(
            "selector.click",
            lambda: self._obj.click(*args, **kwargs),
            invalidate=True,
        )

    def exists(self, *args, **kwargs):
        return self._managed_device._call(
            "selector.exists",
            lambda: self._obj.exists(*args, **kwargs),
            retries=1,
        )

    def get_text(self, *args, **kwargs):
        return self._managed_device._call(
            "selector.get_text",
            lambda: self._obj.get_text(*args, **kwargs),
            retries=1,
        )


class ManagedAdbDevice:
    """
    Proxy compatível com uiautomator2.Device com cache, retry e métricas por device.

    A mudança reduz dumps/app_current/window_size repetidos no mesmo estado de UI. O cache
    é invalidado em ações que podem alterar a tela, evitando leituras antigas após tap/back/start.
    """

    def __init__(self, serial: str, device: u2.Device):
        self.serial = serial or getattr(device, "serial", None) or "default"
        self._device = device
        self._op_lock = threading.RLock()
        self._cache_lock = threading.RLock()
        self._cache = {
            "hierarchy": (0.0, None),
            "app_current": (0.0, None),
            "window_size": (0.0, None),
            "screenshot": (0.0, None),
        }
        self._metrics = {
            "ops": 0,
            "failures": 0,
            "total_time": 0.0,
            "slow_ops": {},
        }

    def __getattr__(self, name):
        return getattr(self._device, name)

    def __call__(self, *args, **kwargs):
        return ManagedUiObject(self, self._device(*args, **kwargs))

    def _record_metric(self, label: str, elapsed: float, failed: bool = False):
        self._metrics["ops"] += 1
        self._metrics["total_time"] += elapsed
        if failed:
            self._metrics["failures"] += 1
        slow_threshold = getattr(config, "ADB_SLOW_OP_THRESHOLD", 1.2)
        if elapsed >= slow_threshold:
            item = self._metrics["slow_ops"].setdefault(label, {"count": 0, "total": 0.0, "max": 0.0})
            item["count"] += 1
            item["total"] += elapsed
            item["max"] = max(item["max"], elapsed)

    def _call(self, label: str, func, retries: int = None, invalidate: bool = False):
        retries = getattr(config, "ADB_RETRY_ATTEMPTS", 2) if retries is None else retries
        last_exc = None
        for attempt in range(retries + 1):
            start = time.perf_counter()
            try:
                # Serializa comandos por device. Em multi-instância isso evita duas threads
                # disputarem o mesmo serial enquanto ainda permite paralelismo entre devices.
                with self._op_lock:
                    result = func()
                elapsed = time.perf_counter() - start
                self._record_metric(label, elapsed)
                if invalidate:
                    self.invalidate_ui_cache()
                return result
            except Exception as exc:
                elapsed = time.perf_counter() - start
                self._record_metric(label, elapsed, failed=True)
                last_exc = exc
                if attempt >= retries:
                    break
                delay = min(
                    getattr(config, "ADB_RETRY_MAX_BACKOFF", 2.0),
                    getattr(config, "ADB_RETRY_BASE_BACKOFF", 0.25) * (2 ** attempt),
                )
                time.sleep(delay + random.uniform(0, delay * 0.2))
        raise last_exc

    def invalidate_ui_cache(self):
        with self._cache_lock:
            self._cache["hierarchy"] = (0.0, None)
            self._cache["app_current"] = (0.0, None)
            self._cache["screenshot"] = (0.0, None)

    def dump_hierarchy(self, *args, ttl: float = None, **kwargs):
        ttl = getattr(config, "UI_HIERARCHY_CACHE_TTL", 0.35) if ttl is None else ttl
        now = time.time()
        with self._cache_lock:
            ts, xml = self._cache["hierarchy"]
            if xml is not None and ttl > 0 and (now - ts) <= ttl:
                return xml

        def _dump():
            try:
                return self._device.dump_hierarchy(*args, **kwargs)
            except TypeError:
                return self._device.dump_hierarchy()

        xml = self._call("dump_hierarchy", _dump)
        with self._cache_lock:
            self._cache["hierarchy"] = (time.time(), xml)
        return xml

    def app_current(self, ttl: float = None):
        ttl = getattr(config, "APP_CURRENT_CACHE_TTL", 0.25) if ttl is None else ttl
        now = time.time()
        with self._cache_lock:
            ts, current = self._cache["app_current"]
            if current is not None and ttl > 0 and (now - ts) <= ttl:
                return current
        current = self._call("app_current", self._device.app_current)
        with self._cache_lock:
            self._cache["app_current"] = (time.time(), current)
        return current

    def window_size(self, ttl: float = None):
        ttl = getattr(config, "WINDOW_SIZE_CACHE_TTL", 300.0) if ttl is None else ttl
        now = time.time()
        with self._cache_lock:
            ts, size = self._cache["window_size"]
            if size is not None and ttl > 0 and (now - ts) <= ttl:
                return size
        size = self._call("window_size", self._device.window_size)
        with self._cache_lock:
            self._cache["window_size"] = (time.time(), size)
        return size

    def screenshot(self, *args, ttl: float = None, **kwargs):
        # Screenshots para arquivo devem sempre capturar a tela atual.
        if args or kwargs:
            return self._call("screenshot_file", lambda: self._device.screenshot(*args, **kwargs))

        ttl = getattr(config, "SCREENSHOT_CACHE_TTL", 0.35) if ttl is None else ttl
        now = time.time()
        with self._cache_lock:
            ts, img = self._cache["screenshot"]
            if img is not None and ttl > 0 and (now - ts) <= ttl:
                return img
        img = self._call("screenshot", self._device.screenshot)
        with self._cache_lock:
            self._cache["screenshot"] = (time.time(), img)
        return img

    def shell(self, cmd, *args, timeout: float = None, retries: int = None, **kwargs):
        mutating = str(cmd).startswith((
            "input ", "am ", "pm ", "settings ", "wm ", "logcat -c", "monkey ",
        ))

        def _shell():
            try:
                if timeout is not None:
                    return self._device.shell(cmd, *args, timeout=timeout, **kwargs)
                return self._device.shell(cmd, *args, **kwargs)
            except TypeError:
                return self._device.shell(cmd)

        return self._call(f"shell:{str(cmd).split(' ', 1)[0]}", _shell, retries=retries, invalidate=mutating)

    def click(self, x, y, *args, **kwargs):
        return self._call("click", lambda: self._device.click(x, y, *args, **kwargs), invalidate=True)

    def press(self, key, *args, **kwargs):
        return self._call(f"press:{key}", lambda: self._device.press(key, *args, **kwargs), invalidate=True)

    def send_keys(self, text, *args, **kwargs):
        return self._call("send_keys", lambda: self._device.send_keys(text, *args, **kwargs), invalidate=True)

    def app_start(self, package, *args, **kwargs):
        return self._call("app_start", lambda: self._device.app_start(package, *args, **kwargs), invalidate=True)

    def app_stop(self, package, *args, **kwargs):
        return self._call("app_stop", lambda: self._device.app_stop(package, *args, **kwargs), invalidate=True)

    def app_clear(self, package, *args, **kwargs):
        return self._call("app_clear", lambda: self._device.app_clear(package, *args, **kwargs), invalidate=True)

    def get_metrics(self):
        metrics = dict(self._metrics)
        metrics["avg_time"] = metrics["total_time"] / metrics["ops"] if metrics["ops"] else 0.0
        return metrics


def managed_device(d: u2.Device, serial: str = None) -> ManagedAdbDevice:
    """Garante que chamadas legadas também possam receber o proxy instrumentado."""
    if isinstance(d, ManagedAdbDevice):
        return d
    return ManagedAdbDevice(serial or getattr(d, "serial", None), d)


def connect_managed_device(serial: str = None, force_reconnect: bool = False) -> ManagedAdbDevice:
    """
    Conecta uma vez por serial e reaproveita a sessão uiautomator2 nas próximas chamadas.

    Isso evita reconexões redundantes em fluxos como ultra-eco, automação e restauração.
    """
    key = serial or "default"
    if not force_reconnect:
        with _adb_client_lock:
            session = _device_sessions.get(key)
            if session is not None:
                return session

    attempts = getattr(config, "ADB_CONNECT_RETRIES", 3)
    last_exc = None
    for attempt in range(attempts):
        try:
            device = u2.connect(serial) if serial else u2.connect()
            session = ManagedAdbDevice(serial or getattr(device, "serial", None) or key, device)
            with _adb_client_lock:
                _device_sessions[key] = session
            return session
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                break
            delay = min(5.0, 0.5 * (2 ** attempt))
            time.sleep(delay + random.uniform(0, delay * 0.2))
    raise last_exc


def drop_managed_device(serial: str = None):
    """Remove sessão em cache após falha crítica para a próxima tentativa reconectar de verdade."""
    key = serial or "default"
    with _adb_client_lock:
        _device_sessions.pop(key, None)


def sleep_interruptible(seconds: float, stop_event=None, step: float = 0.2) -> bool:
    """Sleep curto em fatias para a parada da instância não ficar presa em waits longos."""
    deadline = time.time() + max(0, seconds)
    while time.time() < deadline:
        if stop_event and stop_event.is_set():
            return True
        time.sleep(min(step, deadline - time.time()))
    return bool(stop_event and stop_event.is_set())


def wait_until(predicate, timeout: float, poll: float = 0.3, stop_event=None, backoff: float = 1.25) -> bool:
    """Espera orientada a estado com backoff leve para substituir sleeps cegos."""
    deadline = time.time() + timeout
    interval = poll
    while time.time() < deadline:
        if stop_event and stop_event.is_set():
            return False
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(min(interval, max(0, deadline - time.time())))
        interval = min(2.0, interval * backoff)
    return False


def wait_for_package(d: u2.Device, package: str, timeout: float = 10.0, poll: float = 0.4) -> bool:
    """Aguarda o pacote entrar em foreground sem gastar o timeout inteiro quando já abriu."""
    d = managed_device(d)
    return wait_until(lambda: d.app_current().get("package") == package, timeout=timeout, poll=poll)


def _get_device_model(serial: str) -> str:
    """Tenta obter o modelo do dispositivo via adb shell."""
    try:
        adb = _get_adb_client()
        dev = adb.device(serial)
        model = dev.shell("getprop ro.product.model").strip()
        if model:
            return model
        brand = dev.shell("getprop ro.product.brand").strip()
        name = dev.shell("getprop ro.product.name").strip()
        if brand and name:
            return f"{brand} {name}"
    except Exception:
        pass
    return "Desconhecido"


def list_devices() -> list:
    """
    Lista todos os dispositivos ADB conectados.
    
    Returns:
        Lista de dicts com 'serial' e 'model' de cada dispositivo.
    """
    try:
        adb = _get_adb_client()
        devices = adb.device_list()
        result = []
        for dev in devices:
            model = _get_device_model(dev.serial)
            result.append({"serial": dev.serial, "model": model})
        return result
    except Exception:
        return []


def connect_device(serial: str = None) -> u2.Device:
    """
    Conecta ao dispositivo Android via uiautomator2.
    
    Se houver múltiplos dispositivos conectados, lista todos e
    permite ao usuário escolher qual usar.
    
    Args:
        serial: Serial específico do dispositivo. Se None, detecta automaticamente.
    
    Returns:
        Objeto Device do uiautomator2.
    """
    try:
        print(f"{Fore.CYAN}[ADB] Procurando dispositivos...{Style.RESET_ALL}")
        
        adb = _get_adb_client()
        devices = adb.device_list()
        
        if not devices:
            print(f"{Fore.RED}[ERRO] Nenhum dispositivo encontrado!{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}  Dicas:{Style.RESET_ALL}")
            print(f"  1. Verifique se a Depuração USB está ativada")
            print(f"  2. Conecte o celular via cabo USB")
            print(f"  3. Inicie o emulador e aguarde inicializar")
            print(f"  4. Execute 'adb devices' para verificar")
            raise ConnectionError("Nenhum dispositivo ADB encontrado")
        
        # Listar dispositivos encontrados
        print(f"{Fore.GREEN}[OK] {len(devices)} dispositivo(s) encontrado(s):{Style.RESET_ALL}")
        device_list = []
        for dev in devices:
            model = _get_device_model(dev.serial)
            device_list.append({"serial": dev.serial, "model": model})
            
        for i, dev_info in enumerate(device_list, 1):
            print(f"  {Fore.CYAN}[{i}]{Style.RESET_ALL} {dev_info['model']} ({dev_info['serial']})")
        
        # Selecionar dispositivo
        if serial:
            target_serial = serial
        elif len(device_list) == 1:
            target_serial = device_list[0]["serial"]
        else:
            # Múltiplos dispositivos — mostrar menu com opção "Todos"
            print(f"  {Fore.CYAN}[0]{Style.RESET_ALL} {Fore.GREEN}★ Todos os dispositivos (paralelo){Style.RESET_ALL}")
            print(f"\n{Fore.YELLOW}Escolha o dispositivo (0-{len(device_list)}): {Style.RESET_ALL}", end="")
            try:
                choice = int(input().strip())
                if choice == 0:
                    # Retorna None para indicar "todos"
                    return None, device_list
                elif 1 <= choice <= len(device_list):
                    target_serial = device_list[choice - 1]["serial"]
                else:
                    print(f"{Fore.YELLOW}Opção inválida. Usando o primeiro dispositivo.{Style.RESET_ALL}")
                    target_serial = device_list[0]["serial"]
            except (ValueError, EOFError):
                print(f"{Fore.YELLOW}Usando o primeiro dispositivo.{Style.RESET_ALL}")
                target_serial = device_list[0]["serial"]
        
        # Conectar ao dispositivo selecionado
        selected_model = next(
            (d["model"] for d in device_list if d["serial"] == target_serial),
            "Desconhecido"
        )
        print(f"\n{Fore.CYAN}[ADB] Conectando a: {selected_model} ({target_serial})...{Style.RESET_ALL}")
        
        d = connect_managed_device(target_serial)
        
        info = d.info
        display = d.window_size()
        
        print(f"{Fore.GREEN}[OK] Dispositivo conectado!{Style.RESET_ALL}")
        print(f"  📱 Modelo     : {selected_model}")
        print(f"  🔌 Serial     : {target_serial}")
        print(f"  📐 Tela       : {display[0]}x{display[1]}")
        print(f"  🤖 Android SDK: {info.get('sdkInt', '?')}")
        
        return d, [{"serial": target_serial, "model": selected_model}]
    except ConnectionError:
        raise
    except Exception as e:
        print(f"{Fore.RED}[ERRO] Falha ao conectar: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  Dicas:{Style.RESET_ALL}")
        print(f"  1. Verifique se a Depuração USB está ativada")
        print(f"  2. Conecte o celular via cabo USB ou inicie o emulador")
        print(f"  3. Execute 'adb devices' para verificar a conexão")
        raise


def launch_app(d: u2.Device, package: str = None):
    """
    Abre o aplicativo no dispositivo.
    
    Args:
        d: Dispositivo u2 conectado.
        package: Nome do pacote do app. Se None, usa config.APP_PACKAGE.
    """
    package = package or config.APP_PACKAGE
    d = managed_device(d)
    print(f"{Fore.CYAN}[APP] Abrindo aplicativo: {package}{Style.RESET_ALL}")
    d.app_start(package)
    wait_for_package(d, package, timeout=getattr(config, "APP_REOPEN_TIMEOUT", 25), poll=0.4)
    print(f"{Fore.GREEN}[OK] Aplicativo aberto!{Style.RESET_ALL}")


def force_restart_app(d: u2.Device, package: str = None, clear_cache: bool = False):
    """
    Reinicia o aplicativo.
    
    Args:
        d: Dispositivo u2 conectado.
        package: Nome do pacote.
        clear_cache: Se True, limpa os dados/cache do app.
    """
    package = package or config.APP_PACKAGE
    d = managed_device(d)
    if clear_cache:
        print(f"{Fore.YELLOW}[APP] Limpando dados e reiniciando: {package}{Style.RESET_ALL}")
        d.app_clear(package)
    else:
        print(f"{Fore.YELLOW}[APP] Reiniciando: {package}{Style.RESET_ALL}")
        d.app_stop(package)
    
    sleep_interruptible(0.8)
    d.app_start(package)
    wait_for_package(d, package, timeout=getattr(config, "APP_REOPEN_TIMEOUT", 25), poll=0.4)
    print(f"{Fore.GREEN}[OK] Aplicativo reiniciado!{Style.RESET_ALL}")


def is_app_running(d: u2.Device, package: str = None, safe_packages: list = None) -> bool:
    """
    Verifica se o aplicativo está em foreground (rodando na frente).
    Permite pacotes "seguros" (ex: Play Store) se fornecidos.
    
    Args:
        d: Dispositivo u2 conectado.
        package: Nome do pacote. Se None, usa config.APP_PACKAGE.
        safe_packages: Lista de pacotes que não devem ser considerados "fechamento".
    
    Returns:
        True se o app ou um dos safe_packages está em foreground.
    """
    package = package or config.APP_PACKAGE
    d = managed_device(d)
    try:
        current = d.app_current()
        curr_pkg = current.get("package", "")
        
        if curr_pkg == package:
            return True
            
        if safe_packages and curr_pkg in safe_packages:
            return True
            
        return False
    except Exception:
        return False


def save_debug_screenshot(d: u2.Device, folder: str, name: str) -> str:
    """
    Salva uma screenshot para fins de debug.
    
    Args:
        d: Dispositivo u2 conectado.
        folder: Pasta onde salvar.
        name: Nome do arquivo (sem extensão).
    
    Returns:
        Caminho do arquivo salvo.
    """
    os.makedirs(folder, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(folder, f"{name}_{timestamp}.png")
    d = managed_device(d)
    d.screenshot(filepath)
    print(f"{Fore.MAGENTA}  [DEBUG] Screenshot salva: {filepath}{Style.RESET_ALL}")
    return filepath


def dump_ui_hierarchy(d: u2.Device, folder: str = "debug_screenshots") -> str:
    """
    Faz dump da hierarquia de UI e salva em arquivo XML.
    Útil para debug e para encontrar elementos.
    
    Args:
        d: Dispositivo u2 conectado.
        folder: Pasta onde salvar.
    
    Returns:
        Caminho do arquivo XML salvo.
    """
    os.makedirs(folder, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(folder, f"ui_dump_{timestamp}.xml")
    
    d = managed_device(d)
    xml = d.dump_hierarchy(ttl=0)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(xml)
    
    print(f"{Fore.MAGENTA}  [DEBUG] UI dump salvo: {filepath}{Style.RESET_ALL}")
    return filepath


def optimize_emulator_memory(d: u2.Device):
    """
    Executa comandos ADB para tentar liberar RAM no emulador.
    """
    if not getattr(config, 'ENABLE_MEMORY_OPTIMIZATION', True):
        return

    d = managed_device(d)
    now = time.time()
    last_run = getattr(d, "_last_memory_optimization", 0.0)
    min_interval = getattr(config, "MEMORY_OPTIMIZATION_MIN_INTERVAL", 600)
    if now - last_run < min_interval:
        return

    print(f"{Fore.CYAN}[ADB] Otimizando memória do emulador...{Style.RESET_ALL}")
    try:
        # Um único shell evita duas idas ao ADB para uma manutenção pesada e pouco frequente.
        d.shell("pm trim-caches 1024G; logcat -c", timeout=20, retries=0)
        d._last_memory_optimization = now
        print(f"{Fore.GREEN}[OK] Otimização (trim-caches + logcat) concluída.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ERRO] Falha na otimização: {e}{Style.RESET_ALL}")

def reset_advertising_id(d: u2.Device) -> bool:
    """
    Abre as configurações do Google e reseta o ID de publicidade.
    Necessário quando não há mais anúncios disponíveis.
    """
    d = managed_device(d)
    print(f"{Fore.MAGENTA}[ADB] Resetando ID de Publicidade...{Style.RESET_ALL}")
    try:
        # Tenta abrir direto a activity de Ads do Google Play Services
        # Comando: am start -n com.google.android.gms/.ads.settings.AdsSettingsActivity
        d.shell("am start -n com.google.android.gms/.ads.settings.AdsSettingsActivity")
        time.sleep(2.5)
        
        # Procura o botão de repor/redefinir
        # Texto da imagem do usuário: "Repor ID de publicidade"
        # Outras variações: "Redefinir ID de publicidade", "Reset advertising ID"
        found_reset = False
        for text in ["Repor ID de publicidade", "Redefinir ID de publicidade", "Reset advertising ID"]:
            btn = d(text=text)
            if btn.exists(timeout=1):
                btn.click()
                found_reset = True
                break
        
        if not found_reset:
            # Tenta regex se o texto exato falhar
            btn = d(textMatches=".*(Repor|Redefinir|Reset).*ID.*publicidade.*")
            if btn.exists(timeout=1):
                btn.click()
                found_reset = True
                
        if found_reset:
            time.sleep(1.5)
            # Confirma no popup (OK / Confirmar)
            for confirm_text in ["OK", "Confirmar", "Confirm"]:
                btn_ok = d(text=confirm_text)
                if btn_ok.exists(timeout=1):
                    btn_ok.click()
                    print(f"{Fore.GREEN}[OK] ID de publicidade resetado com sucesso!{Style.RESET_ALL}")
                    time.sleep(1)
                    return True
            
            print(f"{Fore.YELLOW}[AVISO] Botão de confirmação não encontrado.{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[ERRO] Botão 'Repor ID' não encontrado.{Style.RESET_ALL}")
            
    except Exception as e:
        print(f"{Fore.RED}[ERRO] Falha ao resetar ID: {e}{Style.RESET_ALL}")
    
    return False

def apply_headless_optimizations(d: u2.Device):
    """
    Modo Ultra-Eco (Headless Simulado):
    Reduz resolução, densidade e desativa animações para economizar recursos.
    """
    d = managed_device(d)
    print(f"{Fore.MAGENTA}[ADB] Aplicando Otimizações Ultra-Eco (Headless)...{Style.RESET_ALL}")
    try:
        # Agrupa ajustes estáticos para reduzir seis subprocessos/roundtrips ADB por instância.
        d.shell(
            "wm size 360x640; "
            "wm density 160; "
            "settings put global window_animation_scale 0.0; "
            "settings put global transition_animation_scale 0.0; "
            "settings put global animator_duration_scale 0.0; "
            "settings put system screen_brightness 1",
            timeout=20,
        )
        
        print(f"{Fore.GREEN}[OK] Emulador otimizado para baixo consumo.{Style.RESET_ALL}")
        return True
    except Exception as e:
        print(f"{Fore.RED}[ERRO] Falha ao aplicar headless: {e}{Style.RESET_ALL}")
        return False

def restore_display_defaults(d: u2.Device):
    """
    Restaura resolução, densidade e animações padrão do Android.
    """
    d = managed_device(d)
    print(f"{Fore.CYAN}[ADB] Restaurando configurações padrão de tela...{Style.RESET_ALL}")
    try:
        d.shell(
            "wm size reset; "
            "wm density reset; "
            "settings put global window_animation_scale 1.0; "
            "settings put global transition_animation_scale 1.0; "
            "settings put global animator_duration_scale 1.0",
            timeout=20,
        )
        print(f"{Fore.GREEN}[OK] Configurações restauradas.{Style.RESET_ALL}")
        return True
    except Exception as e:
        print(f"{Fore.RED}[ERRO] Falha ao restaurar: {e}{Style.RESET_ALL}")
        return False
