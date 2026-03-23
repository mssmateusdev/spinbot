"""
Módulo de utilidades para interação com o dispositivo Android.
Usa uiautomator2 para conexão e interações com a UI.
"""

import os
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


def _get_device_model(serial: str) -> str:
    """Tenta obter o modelo do dispositivo via adb shell."""
    try:
        adb = adbutils.AdbClient()
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
        adb = adbutils.AdbClient()
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
        
        adb = adbutils.AdbClient()
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
        
        d = u2.connect(target_serial)
        
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
    print(f"{Fore.CYAN}[APP] Abrindo aplicativo: {package}{Style.RESET_ALL}")
    d.app_start(package)
    time.sleep(config.APP_REOPEN_WAIT)
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
    if clear_cache:
        print(f"{Fore.YELLOW}[APP] Limpando dados e reiniciando: {package}{Style.RESET_ALL}")
        d.app_clear(package)
    else:
        print(f"{Fore.YELLOW}[APP] Reiniciando: {package}{Style.RESET_ALL}")
        d.app_stop(package)
    
    time.sleep(1.0)
    d.app_start(package)
    time.sleep(config.APP_REOPEN_WAIT)
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
    
    xml = d.dump_hierarchy()
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
        
    print(f"{Fore.CYAN}[ADB] Otimizando memória do emulador...{Style.RESET_ALL}")
    try:
        # 1. Limpar caches de aplicações (interno do android)
        d.shell("pm trim-caches 1024G")
        
        # 2. Limpar logs do sistema (libera um pouco de buffer RAM)
        d.shell("logcat -c")
        
        # 3. Forçar o GC do sistema se possível (apenas em versões compatíveis)
        # d.shell("cmd activity request-bugreport --progress") # Muito pesado
        
        print(f"{Fore.GREEN}[OK] Otimização (trim-caches + logcat) concluída.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ERRO] Falha na otimização: {e}{Style.RESET_ALL}")

def reset_advertising_id(d: u2.Device) -> bool:
    """
    Abre as configurações do Google e reseta o ID de publicidade.
    Necessário quando não há mais anúncios disponíveis.
    """
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
