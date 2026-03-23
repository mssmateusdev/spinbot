# 🎰 SPINBOT OPTIMIZED v0.4.0 - MAX PERFORMANCE

O **Spinbot** é uma ferramenta de automação avançada para o aplicativo Spincoin (Android), focada em maximizar o lucro através da automatização inteligente de spins e visualização de anúncios (ads). Esta versão conta com uma interface gráfica (GUI) moderna e sistemas de auto-recuperação de erros.

---

## ✨ Funcionalidades Principais

-   **Dashboard em Tempo Real**: Visualize ciclos, lucros acumulados (em moedas e BRL), tempo de sessão e status atual.
-   **Projeções Inteligentes**: Calcule estimativas de lucro para 1 hora, 1 dia, 1 semana e até 1 mês com base no seu desempenho atual.
-   **Limpeza Inteligente de Cache (Novo!)**:
    -   Limpeza inicial de dados ao iniciar a automação para garantir eficiência máxima.
    -   Reset automático do app (`pm clear`) em caso de timeout de 120s nos anúncios.
    -   Reinício limpo se o bot detectar inatividade (>60s) na tela principal.
-   **Auto-Recuperação**:
    -   Tratamento de interrupções do Google Chrome e Play Store.
    -   Reset automático do ID de publicidade se os anúncios esgotarem.
    -   Otimização de memória RAM do emulador periódica.
-   **Multi-Dispositivos**: Escolha facilmente entre vários dispositivos ADB conectados.
-   **Relatórios Persistentes**: Registro diário de lucros salvos por e-mail da conta.

---

## 🛠️ Pré-requisitos

1.  **Python 3.10+**: Certifique-se de ter o Python instalado e no PATH.
2.  **ADB (Android Debug Bridge)**: Necessário para a comunicação com o dispositivo.
    -   O projeto já inclui um binário `adb.exe`, mas recomenda-se ter o [Platform Tools](https://developer.android.com/tools/releases/platform-tools) instalado no Windows.
3.  **Dispositivo Android/Emulador**:
    -   **Depuração USB Ativada** (em Opções do Desenvolvedor).
    -   Resolução recomendada: **1080x2400** (ou calibrada via `calibrar.py`).

---

## 🚀 Como Iniciar

### 1. Instalar Dependências
Abra o terminal na pasta do projeto e execute:
```bash
pip install -r requirements.txt
```

### 2. Abrir a Interface Gráfica
```bash
python gui.py
```

### 3. Configuração Rápida
1.  Selecione seu dispositivo na aba **Configurações**.
2.  Insira seu **E-mail da Conta** na barra lateral.
3.  Clique no botão **INICIAR AUTOMAÇÃO** no Dashboard.

---

## 🔧 Calibração (Se necessário)

Se os botões não estiverem sendo clicados corretamente devido à resolução do seu celular:
1.  Vá em **Configurações** na GUI e clique em **Recalibrar Tela**.
2.  Siga as instruções para gerar as novas coordenadas e atualizar o `config.py`.

---

## 📂 Estrutura do Projeto

-   `gui.py`: Interface gráfica principal (Tkinter).
-   `main.py`: Lógica central da automação e loops de controle.
-   `adb_utils.py`: Funções de baixo nível para interação via ADB.
-   `screen_reader.py`: Processamento de imagem e detecção de elementos (OCR/Templates).
-   `config.py`: Parâmetros de tempo, pacotes e coordenadas.
-   `stats_manager.py`: Persistência de estatísticas e lucros diários.

---

## ⚠️ Avisos e Recomendações

-   **Mantenha a Tela Ligada**: O dispositivo deve permanecer com a tela ativa para o processamento visual.
-   **Otimização**: Se notar lentidão no emulador, o bot tentará limpar o cache automaticamente a cada 10 ciclos.
-   **Segurança**: O bot trata janelas pop-up de "Identidade Google" e "Play Store" automaticamente para evitar interrupções.

---

## 📝 Changelog v0.4.0
-   Adicionada limpeza de cache (`pm clear`) na inicialização e timeouts.
-   Nova interface Zinc Palette (Dark Modern).
-   Sistema de projeção de ganhos financeiros (BRL).
-   Melhoria radical no reconhecimento de botões de fechar anúncios (X).
