"""
Ferramenta de calibração e debug para o automador.
Usa uiautomator2 para inspecionar os elementos da UI do app.

Uso:
  python calibrar.py              -> Screenshot + info do dispositivo
  python calibrar.py --dump       -> Dump da hierarquia de UI (mostra elementos)
  python calibrar.py --elementos  -> Lista elementos com texto visível na tela
"""

import sys
import os
import time
import re
from colorama import init, Fore, Style

init(autoreset=True)


def info_dispositivo():
    """Captura screenshot e mostra informações do dispositivo."""
    from adb_utils import connect_device
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"  CALIBRAÇÃO - Info do Dispositivo")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    d, _ = connect_device()
    if d is None:
        print(f"{Fore.RED}Nenhum dispositivo selecionado.{Style.RESET_ALL}")
        return
    
    # Screenshot
    os.makedirs("calibracao", exist_ok=True)
    filepath = f"calibracao/screenshot_{time.strftime('%H%M%S')}.png"
    d.screenshot(filepath)
    print(f"\n{Fore.GREEN}Screenshot salva: {filepath}{Style.RESET_ALL}")


def dump_hierarquia():
    """Faz dump da hierarquia de UI e salva em XML."""
    from adb_utils import connect_device, dump_ui_hierarchy
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"  CALIBRAÇÃO - Dump da Hierarquia de UI")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    d, _ = connect_device()
    if d is None:
        print(f"{Fore.RED}Nenhum dispositivo selecionado.{Style.RESET_ALL}")
        return
    
    os.makedirs("calibracao", exist_ok=True)
    filepath = dump_ui_hierarchy(d, "calibracao")
    print(f"\n{Fore.GREEN}Dump salvo: {filepath}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Abra o XML para ver todos os elementos da tela.{Style.RESET_ALL}")


def listar_elementos():
    """Lista todos os elementos com texto visível na tela."""
    from adb_utils import connect_device
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"  CALIBRAÇÃO - Elementos com Texto na Tela")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    d, _ = connect_device()
    if d is None:
        print(f"{Fore.RED}Nenhum dispositivo selecionado.{Style.RESET_ALL}")
        return
    
    # Usar xpath para pegar todos os elementos
    elements = d.xpath('//*[@text!=""]').all()
    
    print(f"\n{Fore.GREEN}Encontrados {len(elements)} elementos com texto:{Style.RESET_ALL}\n")
    
    for i, elem in enumerate(elements, 1):
        text = elem.attrib.get("text", "")
        cls = elem.attrib.get("class", "").split(".")[-1]
        res_id = elem.attrib.get("resource-id", "")
        bounds = elem.attrib.get("bounds", "")
        desc = elem.attrib.get("content-desc", "")
        
        print(f"  {Fore.CYAN}#{i}{Style.RESET_ALL} ", end="")
        print(f"{Fore.WHITE}texto={Style.RESET_ALL}\"{Fore.GREEN}{text}{Style.RESET_ALL}\"", end="")
        
        if res_id:
            short_id = res_id.split("/")[-1] if "/" in res_id else res_id
            print(f"  {Fore.YELLOW}id={short_id}{Style.RESET_ALL}", end="")
        if desc:
            print(f"  {Fore.MAGENTA}desc={desc}{Style.RESET_ALL}", end="")
        
        print(f"  [{cls}] {bounds}")
    
    print(f"\n{Fore.YELLOW}Dica: use os textos acima para ajustar config.py se necessário.{Style.RESET_ALL}")


if __name__ == "__main__":
    if "--dump" in sys.argv:
        dump_hierarquia()
    elif "--elementos" in sys.argv:
        listar_elementos()
    else:
        info_dispositivo()
