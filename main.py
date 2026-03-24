"""
╔══════════════════════════════════════════════════════════════╗
║          SPINBOT OPTIMIZED v0.4.0 - MAX PERFORMANCE          ║
╚══════════════════════════════════════════════════════════════╝
"""
import sys
import time
import os
import threading
import gc
from datetime import datetime
from colorama import init, Fore, Style

import config
import uiautomator2 as u2
from adb_utils import (
    connect_device,
    launch_app,
    force_restart_app,
    is_app_running,
    optimize_emulator_memory
)
from screen_reader import (
    find_spin_button,
    find_ad_button,
    find_close_button,
    check_spins_status,
    check_and_dismiss_popup,
    is_main_screen,
    is_ad_screen,
    get_ad_timer,
    read_coin_count_from_ui,
)
from device_profiles import load_profile

init(autoreset=True)

class SpinAutomator:
    _print_lock = threading.Lock()
    
    def __init__(self, serial=None, device_profile=None, stop_event=None, on_log=None, on_stats_update=None, device_label="Device", account_email=None, dry_run=False):
        self.device = None
        self.serial = serial
        self.device_profile = device_profile
        self.stop_event = stop_event
        self.on_log = on_log
        self.on_stats_update = on_stats_update
        self.device_label = device_label
        self.account_email = account_email # Email para relatórios
        self.dry_run = dry_run
        
        self.total_spins = 0
        self.total_ads = 0
        self.total_cycles = 0
        self.app_restarts = 0
        self.consecutive_ghost_spins = 0 # Contador de giros sem ganhos
        self.consecutive_no_spins_after_ad = 0 # NOVO: Controle de loop de Ad bugado
        self.errors_consecutivos = 0
        self.last_stats_update = 0
        
        self.start_time = None
        self.current_coins = 0
        self.initial_coins = 0
        self.last_action_time = time.time()
        
        # Carrega lucro já acumulado hoje para este email
        from stats_manager import manager
        self.points_today_pre = manager.get_profit(self.account_email) if self.account_email else 0

    def get_daily_profit(self):
        session_profit = self.current_coins - self.initial_coins if self.initial_coins > 0 else 0
        return self.points_today_pre + session_profit

    def log(self, msg: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M")
        color = {
            "info": Fore.WHITE, "success": Fore.GREEN, 
            "warning": Fore.YELLOW, "error": Fore.RED, "action": Fore.CYAN,
            "header": Fore.MAGENTA
        }.get(level, Fore.WHITE)
        
        with SpinAutomator._print_lock:
            if level == "header":
                print(f"\n{color}{'='*40}\n  {msg}\n{'='*40}")
            else:
                print(f"{color}[{timestamp}] {msg}")
        
        if self.on_log:
            self.on_log(msg, level)

    def stats_update(self, force=False):
        now = time.time()
        if force or (now - self.last_stats_update) > getattr(config, 'STATS_UPDATE_INTERVAL', 10):
            if self.on_stats_update:
                elapsed = datetime.now() - self.start_time if self.start_time else "0:00:00"
                # Calcula lucro total (acumulado hoje + sessão atual)
                profit = self.get_daily_profit()
                
                self.on_stats_update({
                    "elapsed": str(elapsed).split('.')[0],
                    "spins": self.total_spins,
                    "ads": self.total_ads,
                    "cycles": self.total_cycles,
                    "restarts": self.app_restarts,
                    "current_coins": self.current_coins,
                    "profit": profit
                })
                
                # Relatórios persistentes
                if self.account_email:
                    from stats_manager import manager
                    manager.update_profit(self.account_email, profit)
            self.last_stats_update = now

    def _update_coins(self):
        """Lê moedas da UI e atualiza o estado interno."""
        c = read_coin_count_from_ui(self.device, self.device_profile)
        if c > 0:
            if self.initial_coins == 0: 
                self.initial_coins = c
                self.log(f"Saldo Inicial Capturado: {c:,}".replace(',', '.'), "info")
            
            # Se o novo valor for menor que o anterior (exceto no início), 
            # pode ser erro de leitura ou gasto. Só atualizamos se for plausível.
            if self.current_coins == 0 or abs(c - self.current_coins) < 100000:
                self.current_coins = c
                self.stats_update(True)

    def wait(self, seconds: float) -> bool:
        if self.stop_event and self.stop_event.is_set(): return True
        time.sleep(seconds)
        return self.stop_event and self.stop_event.is_set()

    def run(self):
        """Entry point para a thread da GUI."""
        self.start_time = datetime.now()
        
        while not (self.stop_event and self.stop_event.is_set()):
            try:
                # Conectar ou tentar reconectar se self.device for None
                if not self.device:
                    self.log(f"Conectando ao dispositivo {self.serial or ''}...", "info")
                    try:
                        self.device = u2.connect(self.serial) if self.serial else u2.connect()
                        if not self.device: raise Exception("Falha u2.connect")
                    except Exception as e:
                        self.log(f"Falha na conexão ADB: {e}. Tentando em 10s...", "error")
                        self.wait(10)
                        continue
                        
                    # Carregar perfil se não estiver definido
                    if not self.device_profile and self.serial:
                        from device_profiles import load_profile
                        self.device_profile = load_profile(self.serial)
                    
                    self.log("Dispositivo conectado com sucesso!", "success")
                    optimize_emulator_memory(self.device)
                
                # Garantir início limpo (primeira iteração ou reconexão crítica)
                if self.start_time is None or getattr(self, '_first_run', True):
                    self.log(f"Bot v0.4.0 Iniciado - Realizando limpeza inicial de dados...", "header")
                    self.device.app_clear(config.APP_PACKAGE)
                    self.wait(3)
                    self.start_time = datetime.now()
                    self.last_action_time = time.time()
                    self._first_run = False
                
                # Garantir app aberto e logado
                current_pkg = self.device.app_current().get("package")
                if current_pkg == "com.android.chrome":
                    self.handle_chrome_interruption()
                    continue
                
                if not is_app_running(self.device):
                    launch_app(self.device)
                    self.wait(2)
                
                if not is_main_screen(self.device):
                    self.handle_login_flow()
                    if self.wait(2): break

                if (self.total_cycles > 0 and self.total_cycles % 10 == 0):
                    self.log("Otimizando RAM...", "warning")
                    optimize_emulator_memory(self.device)
                    gc.collect()

                # Tentar ler moedas e atualizar dashboard
                if is_main_screen(self.device):
                    self._update_coins()

                # Executar Ciclo
                success = self.main_cycle()
                
                if not success:
                    self.log("Ciclo falhou, tentando recuperar...", "warning")
                    self.errors_consecutivos += 1
                    
                    if self.errors_consecutivos >= 3:
                        # Se já falhou 3 ciclos seguidos, forçamos o restart com limpeza
                        self.log("Muitas falhas seguidas. Reiniciando app com limpeza de dados...", "error")
                        force_restart_app(self.device, clear_cache=True)
                        self.app_restarts += 1
                        self.errors_consecutivos = 0
                        
                        # Lógica de Reset de ID de Publicidade (se reiniciar > 2 vezes seguidas)
                        if not hasattr(self, 'consecutive_restarts'):
                             self.consecutive_restarts = 0
                        self.consecutive_restarts += 1
                        
                        if self.consecutive_restarts > 2:
                            self.log("Muitos reinícios sem sucesso (Ads esgotados?). Resetando ID...", "warning")
                            from adb_utils import reset_advertising_id
                            if reset_advertising_id(self.device):
                                self.log("ID Resetado! Tentando novamente...", "success")
                                self.consecutive_restarts = 0 # Resetamos o contador para dar chance
                                launch_app(self.device)
                                self.wait(5)
                            else:
                                self.log("Falha ao resetar ID. Continuando...", "error")
                else:
                    self.errors_consecutivos = 0
                    if hasattr(self, 'consecutive_restarts'):
                        self.consecutive_restarts = 0
                    self.total_cycles += 1
                
                self.stats_update(True)
                
            except Exception as e:
                self.log(f"Erro Crítico no loop: {e}", "error")
                import traceback
                print(traceback.format_exc())
                # Forçar a reconexão na próxima tentativa
                self.device = None
                self.log("Aguardando 10s antes de tentar reconectar...", "warning")
                self.wait(10)
                
        self.log("Bot finalizado pelo usuário.", "header")

    def handle_login_flow(self):
        """Lida com as telas de onboarding e login com verificação de sucesso."""
        from screen_reader import find_getting_started_button, find_email_field, find_login_button, is_main_screen
        
        # 1. Getting Started
        btn_start = find_getting_started_button(self.device)
        if btn_start:
            self.log("Tela inicial detectada. Clicando em Iniciar...", "action")
            btn_start.click()
            self.wait(2)
            
        # 2. Tela de Login
        field = find_email_field(self.device)
        if field:
            self.log(f"Inserindo email...", "action")
            field.click()
            self.wait(1)
            self.device.send_keys(self.account_email)
            self.device.press("enter")
            self.wait(1)
            
            btn_login = find_login_button(self.device)
            if btn_login:
                btn_login.click()
                self.log("Login enviado. Aguardando tela principal (30s)...", "info")
                
                # MONITORAR SUCESSO DO LOGIN (30s timeout)
                wait_start = time.time()
                while (time.time() - wait_start) < 30:
                     if is_main_screen(self.device):
                         self.log("Login efetuado com sucesso!", "success")
                         return True
                     if self.wait(1): return False
                
                # TIMEOUT: Limpar dados e reiniciar
                self.log("TIMEOUT LOGIN: Não entrou na tela principal.", "error")
                self.log("Reiniciando limpo (Clear Data) para tentar novamente...", "warning")
                
                # Executa pm clear para limpar dados e cache, forçando logout/reinicio total
                self.device.shell(f"pm clear {config.APP_PACKAGE}")
                self.wait(2)
                
                # O loop principal do run() vai reabrir o app na próxima iteração
                return False
                
        return False


    def handle_external_redirection(self, pkg_detected="Desconhecido"):
        """
        Detecta se o dispositivo saiu do Spincoin para um app externo (Chrome, Play Store, etc)
        e força o retorno imediato.
        """
        self.log(f"Redirecionamento externo detectado ({pkg_detected})! Analisando...", "warning")
        
        # 1. Caso especial: Google Identity/Play Store Login
        if pkg_detected in ["com.google.android.gms", "com.android.vending"]:
             for text in config.PLAY_STORE_LOGIN_TEXTS:
                  if self.device(textContains=text).exists(timeout=0.1):
                       self.log(f"Popup de Identidade Google detectado! Tentando dispensar...", "action")
                       self.device.press("back")
                       self.wait(1.5)
                       if self.device.app_current().get("package") == config.APP_PACKAGE:
                            return True
                       # Segunda tentativa
                       self.device.press("back")
                       self.wait(1.5)
                       break

        try:
            # 2. Volte para o aplicativo
            self.device.app_start(config.APP_PACKAGE)
            self.wait(2.0)
            
            # 3. Force parada de apps indesejados se abertos (Chrome é o mais problemático)
            if pkg_detected == "com.android.chrome":
                 self.device.app_stop("com.android.chrome")
            elif pkg_detected == "com.android.vending":
                 self.device.app_stop("com.android.vending")
            
            # 4. Verifica se voltou com sucesso
            curr = self.device.app_current().get("package")
            if curr == config.APP_PACKAGE:
                 self.log(f"Retorno ao Spincoin bem-sucedido.", "success")
                 return True
            return False
            
        except Exception as e:
            self.log(f"Erro ao tratar redirecionamento: {e}", "error")
            return False

    def handle_chrome_interruption(self):
        # Mantido por compatibilidade, mapeando para a nova lógica generalista
        return self.handle_external_redirection("com.android.chrome")

    def main_cycle(self) -> bool:
        """Um ciclo: SPINs -> AD -> Voltar."""
        phase_start = time.time()
        
        while (time.time() - phase_start) < 60:
            if self.stop_event and self.stop_event.is_set(): return True
            
            # 0. Verificação específica do Google Chrome ou Play Store (Solicitação do Usuário)
            current_app = self.device.app_current()
            curr_pkg = current_app.get("package")
            
            if curr_pkg != config.APP_PACKAGE and curr_pkg not in config.SAFE_AD_PACKAGES:
                 self.handle_external_redirection(curr_pkg)
                 return False # Forçar reinício do fluxo
            
            if is_main_screen(self.device):
                if check_and_dismiss_popup(self.device):
                    self.log("Sincronizando spins: Popup fechado. Reiniciando app...", "warning")
                    force_restart_app(self.device)
                    self.wait(5)
                    continue
                
                status = check_spins_status(self.device, self.device_profile)
                
                if status == "HAS_SPINS":
                    self.log("MODO TURBO: Iniciando giros rápidos...", "action")
                    spin_btn = find_spin_button(self.device)
                    if not spin_btn:
                         self.log("Botão SPIN não encontrado. Reiniciando...", "warning")
                         force_restart_app(self.device)
                         continue
                         
                    # Coordenadas fixas para cliques ultra-rápidos
                    btn_bounds = spin_btn.info.get('bounds')
                    target_x = (btn_bounds['left'] + btn_bounds['right']) // 2
                    target_y = (btn_bounds['top'] + btn_bounds['bottom']) // 2
                    
                    last_profit_time = time.time()
                    coins_at_turbo_start = self.current_coins
                    turbo_clicks = 0
                    
                    # Loop de Alta Velocidade (Turbo)
                    # Para se: acabarem os spins, o app travar (10s sem lucro) ou stop_event
                    while (time.time() - last_profit_time) < 10:
                        if self.stop_event and self.stop_event.is_set(): break
                        
                        # Clique rápido por coordenadas
                        if not self.dry_run:
                             self.device.click(target_x, target_y)
                        
                        turbo_clicks += 1
                        self.total_spins += 1
                        self.last_action_time = time.time()
                        
                        # Intervalo mínimo para o toque ser processado
                        self.wait(config.TURBO_CLICK_INTERVAL)
                        
                        # Verificação de lucro (a cada ciclo do turbo)
                        from screen_reader import get_spin_result
                        prize = get_spin_result(self.device)
                        self._update_coins()
                        
                        if prize > 0 or self.current_coins > coins_at_turbo_start:
                             # Sucesso! Resetamos o cronômetro de 10s
                             self.log(f"Turbo Spin: +{prize} moedas! (Total Cliques: {turbo_clicks})", "success")
                             last_profit_time = time.time()
                             coins_at_turbo_start = self.current_coins
                             self.stats_update()
                             
                        # Verificação de fim de spins (a cada 3 cliques para não pesar o ADB)
                        if turbo_clicks % 3 == 0:
                             if check_spins_status(self.device) == "NO_SPINS":
                                  self.log(f"Modo Turbo finalizado após {turbo_clicks} giros.", "info")
                                  break
                    
                    # Se saiu por inatividade (10s sem lucro)
                    if (time.time() - last_profit_time) >= 10:
                        self.log("Timeout de 10s sem lucro no Modo Turbo. Possível travamento.", "error")
                        force_restart_app(self.device, clear_cache=True)
                        return False
                        
                    continue
                    
                elif status == "NO_SPINS":
                    ad_btn = find_ad_button(self.device)
                    if ad_btn:
                        if not self.dry_run: ad_btn.click()
                        self.log("Anúncio iniciado", "action")
                        self.last_action_time = time.time() # Atividade detectada
                        if self.watch_ad():
                            self.total_ads += 1
                            return True
                        return False
                    else:
                        # Acabaram os spins mas o botão de anúncio sumiu (bug comum)
                        self.log("Sem spins e botão de anúncio não encontrado. Reiniciando app...", "warning")
                        force_restart_app(self.device)
                        self.app_restarts += 1
                        self.last_action_time = time.time()
                        self.wait(5)
                        return True # Retorna True para contar como ciclo "tratado" e continuar
                
                # CHECK IDLE TIMEOUT (60s na main sem rodar nada)
                if (time.time() - self.last_action_time) > 60:
                    self.log("Inatividade na tela principal (>60s). Reiniciando app com limpeza de dados...", "error")
                    force_restart_app(self.device, clear_cache=True)
                    self.app_restarts += 1
                    self.last_action_time = time.time()
                    self.wait(5)
                    return False
            
            else:
                if is_ad_screen(self.device):
                    self.watch_ad()
                    continue
                # Se estiver perdido, tenta voltar
                self.device.press("back")
                if self.wait(2): return True
            
            if self.wait(1): return True
        return False

    def watch_ad(self) -> bool:
        """Lógica de anúncio: espera timer acabar, clica X ou Continuar (>|)."""
        self.wait(config.AD_LOAD_WAIT)
        start = time.time()
        
        ad_parts_closed = 0
        max_duration = 120  # 120s totais como solicitado
        last_timer_log = -1
        timer_was_active = False
        reward_received = False
        clicks_after_reward = 0
        
        self.log(f"Anúncio detectado. Monitorando (Item #{self.total_ads+1})...", "action")
        
        while (time.time() - start) < max_duration:
            if self.stop_event and self.stop_event.is_set(): return False
            
            # 1. App fechou ou Redirecionou? (Bloqueio Agressivo de Apps Externos)
            current_app = self.device.app_current()
            curr_pkg = current_app.get("package")
            
            if curr_pkg != config.APP_PACKAGE and curr_pkg not in config.SAFE_AD_PACKAGES:
                 # Se o pacote mudou para algo não autorizado (Chrome, Play Store, Samsung Internet, etc)
                 self.handle_external_redirection(curr_pkg)
                 self.wait(2)
                 continue

            # 1.5. Verificar Recompensa Concedida (REIR PRIORIDADE)
            # Ao detectar recompensa, o bot deve reiniciar imediatamente para não travar na tela final
            if self.device(textContains="Recompensa concedida").exists(timeout=0.2) or \
               self.device(textContains="Recompensa concluida").exists(timeout=0.2):
                self.log("Recompensa concedida detectada! Reiniciando app imediatamente...", "success")
                force_restart_app(self.device, clear_cache=False)
                self.wait(5)
                return True

            # 2. Voltou para tela principal? (Sucesso!)
            if is_main_screen(self.device):
                check_and_dismiss_popup(self.device)
                
                # Verificação extra solicitada pelo usuário (Se spins for 0, não girar)
                spins = self.get_spins_count(quick=True)
                if spins > 0:
                    self._update_coins()
                    self.log(f"Anúncio validado! Spins disponíveis: {spins}", "success")
                    self.consecutive_no_spins_after_ad = 0 # Reseta o contador de erro
                    return True
                else:
                    self.wait(5) # Espera sincronização do app
                    spins_retry = self.get_spins_count(quick=True)
                    if spins_retry > 0:
                         self.log("Anúncio validado com sucesso!", "success")
                         self.consecutive_no_spins_after_ad = 0
                         return True
                    
                    self.consecutive_no_spins_after_ad += 1
                    self.log(f"Voltou para main, mas contador de spins ainda é 0 (Tentativa {self.consecutive_no_spins_after_ad}/2).", "warning")
                    
                    if self.consecutive_no_spins_after_ad >= 2:
                        self.log("DETECÇÃO DE LOOP: O app não creditou os spins. Reiniciando forçado...", "error")
                        force_restart_app(self.device, clear_cache=True)
                        self.wait(5)
                        self.consecutive_no_spins_after_ad = 0 # Reseta após o restart
                        
                    return True 

            # 3. Verificar timer (Pillar: 'espere acabar até os segundos sumirem')
            timer = get_ad_timer(self.device)
            if timer >= 0:
                timer_was_active = True
                if timer != last_timer_log:
                    # Logar progresso (a cada 5s ou quando chegar perto do fim)
                    if timer % 5 == 0 or timer < 10:
                        self.log(f"Timer: {timer}s restantes...", "info")
                    last_timer_log = timer
                self.wait(1)
                continue  # Enquanto houver número/timer, aguarda e não clica.

            # 4. Diálogo de confirmação 'Fechar vídeo?' -> Clicar em RETOMAR
            btn_retomar = self.device(textMatches="(?i).*retomar.*v[ií]deo.*")
            if btn_retomar.exists(timeout=0.1):
                self.log("Diálogo detectado -> Retomando vídeo para garantir prêmio...", "warning")
                btn_retomar.click()
                self.wait(1)
                continue

            # 5. Timer acabou ou não existe -> Procurar X, Continuar ou '>|'
            elapsed = time.time() - start
            
            # PASSIVE_WAIT_MINIMO: 10 segundos ignorando botões X (exceto se for retorno pra main)
            if elapsed < 10:
                 self.wait(1)
                 continue
                 
            # Ajuste de paciência: Se nunca vimos um timer, esperamos pelo menos 15s 
            min_wait_fallback = getattr(config, 'AD_MIN_WAIT_FALLBACK', 15)
            required_wait = 1 if timer_was_active else min_wait_fallback
            
            if elapsed > required_wait:
                close_btn = find_close_button(self.device)
                
                # Proteção extra: Se achou um botão escrito "Skip" ou "Pular", 
                # só clica se já passou pelo menos 25 segundos, pois costumam não dar prêmio antes.
                if close_btn:
                    try:
                        btn_info = close_btn.info
                        btn_text = str(btn_info.get('text', '') or btn_info.get('description', '')).lower()
                        if ("skip" in btn_text or "pular" in btn_text) and elapsed < 25:
                            self.log(f"Botão '{btn_text}' ignorado por ser muito cedo ({int(elapsed)}s).", "info")
                            close_btn = None
                    except: pass

                if close_btn:
                    ad_parts_closed += 1
                    btn_text = close_btn.info.get('text', 'X') or close_btn.info.get('description', 'X-Icon')
                    self.log(f"Clicando para fechar/continuar: '{btn_text}' (Parte {ad_parts_closed})", "action")
                    close_btn.click()
                    self.wait(2.5)
                    
                    if reward_received:
                        clicks_after_reward += 1
                    
                    # Se clicou num botão 'Continuar', pode ser o fim do ad
                    if "continuar" in str(btn_text).lower() or ">|" in str(btn_text):
                        self.wait(2)
                        if is_main_screen(self.device): return True
                    
                    # Se já clicamos muitas vezes após a recompensa e não fechou, reinicia
                    if clicks_after_reward >= 3:
                        self.log("Muitos cliques no X após recompensa sem sucesso. Reiniciando app...", "warning")
                        force_restart_app(self.device, clear_cache=False)
                        self.wait(5)
                        return True
                    
                    timer_was_active = False
                    last_timer_log = -1
                    continue
                
                # FALLBACK: Se o timer acabou (או nunca existiu) e passou 30s sem achar botão X
                # Tentamos usar o botão de Voltar (Back) conforme solicitado para alguns tipos de ads
                if elapsed > 30 and not timer_was_active and (elapsed % 15 < 1):
                    self.log("Botão X não detectado -> Tentando comando VOLTAR (Back)...", "warning")
                    self.device.press("back")
                    self.wait(1.5)
                    # O tratamento do diálogo 'Fechar vídeo?' acima cuidará se isso for proibido agora

            # 6. Fallback extremo (Restart)
            if elapsed > 60 and not timer_was_active:
                if self.device(text="Instalar").exists(timeout=0.1) or self.device(textContains="Play Store").exists(timeout=0.1):
                    self.log("Possível tela final de Ad detectada. Reiniciando app...", "warning")
                    force_restart_app(self.device, clear_cache=False)
                    self.wait(5)
                    return True

            self.wait(1)
            
        # TIMEOUT: Forçar restart do app com limpeza
        self.log(f"Timeout total (120s). Reiniciando app com limpeza de dados...", "error")
        force_restart_app(self.device, clear_cache=True)
        self.app_restarts += 1
        return False

    def get_spins_count(self, quick=False):
        """Helper para ler spins rapidamente."""
        from screen_reader import read_spin_count_from_ui
        return read_spin_count_from_ui(self.device, self.device_profile)

if __name__ == "__main__":
    # Inicia em modo CLI se rodar o arquivo diretamente
    bot = SpinAutomator(device_label="CLI")
    bot.run()
