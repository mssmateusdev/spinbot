# 🎰 Automador de Spins + Anúncios via ADB

Automatiza o ciclo de spins e anúncios em um aplicativo Android usando ADB (Android Debug Bridge).

## 📋 Pré-requisitos

### 1. ADB (Android Debug Bridge)

- Baixe o [Platform Tools](https://developer.android.com/tools/releases/platform-tools) do Android
- Extraia e adicione a pasta ao **PATH** do Windows
- Verifique: `adb version`


### 2. Depuração USB no celular

1. Vá em **Configurações** → **Sobre o telefone**
2. Toque 7x em **Número da versão** (ativa opções de desenvolvedor)
3. Vá em **Opções de desenvolvedor** → Ative **Depuração USB**
4. Conecte o celular via cabo USB
5. Aceite a autorização no celular

### 3. Python 3.10+

```bash
python --version
```

## 🚀 Instalação

```bash
# Instalar dependências
pip install -r requirements.txt
```

## 🔧 Calibração (IMPORTANTE - Faça isso primeiro!)

As coordenadas dos botões dependem da resolução do seu celular. Você precisa calibrar antes de rodar.

### Passo 1: Capturar screenshot

```bash
python calibrar.py
```

Isso vai mostrar a resolução do celular e salvar uma screenshot na pasta `calibracao/`.

### Passo 2: Encontrar coordenadas

Abra a screenshot salva em um editor de imagens (ex: Paint) e anote as coordenadas (x, y) de:

- **Centro do botão SPIN**
- **Centro do botão "See an ad..."**
- **Botão X de fechar anúncio**
- **Região do contador de spins** (retângulo: x1, y1, x2, y2)
- **Região do timer de anúncio** (retângulo: x1, y1, x2, y2)

### Passo 3: Atualizar config.py

Edite o `config.py` com as coordenadas encontradas.

### Passo 4: Verificar posições

```bash
python calibrar.py --regioes
```

Abra a imagem gerada e verifique se os marcadores estão nos lugares corretos.

### Passo 5: Testar OCR

```bash
python calibrar.py --testar-ocr
```

Verifique se o contador de spins está sendo lido corretamente.

## ▶️ Execução

### Modo normal

```bash
python main.py
```

### Modo simulação (não toca na tela)

```bash
python main.py --dry-run
```

## ⚙️ Configuração

Edite o arquivo `config.py` para ajustar:

| Parâmetro           | Descrição                              |
| ------------------- | -------------------------------------- |
| `SPIN_BUTTON`       | Coordenadas (x, y) do botão SPIN       |
| `AD_BUTTON`         | Coordenadas (x, y) do botão de anúncio |
| `CLOSE_AD_BUTTON`   | Coordenadas (x, y) do botão X          |
| `SPIN_COUNT_REGION` | Região do contador de spins            |
| `AD_TIMER_REGION`   | Região do timer do anúncio             |
| `SPIN_WAIT`         | Tempo de espera após cada spin         |
| `AD_MAX_WAIT`       | Timeout máximo do anúncio              |
| `MAX_CYCLES`        | Limite de ciclos (None = infinito)     |
| `DEBUG_MODE`        | Salva screenshots de erro              |

## 🔄 Fluxo de Funcionamento

```
┌─────────────────────────────┐
│   Início                    │
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│   Captura screenshot        │
│   Lê contador de spins      │
└─────────────┬───────────────┘
              ▼
         ┌────────┐
         │Spins>0?│──── Sim ──→ Clica SPIN → Espera animação ─┐
         └────────┘                                            │
              │ Não                                            │
              ▼                                                │
┌─────────────────────────────┐                                │
│   Clica "See an ad..."      │                     ◄──────────┘
│   Espera anúncio carregar   │
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│   Monitora timer do anúncio │
│   Espera chegar a 0         │
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│   Clica X (fechar anúncio)  │
│   Volta à tela principal    │
└─────────────┬───────────────┘
              ▼
         Repete ciclo
```

## ⚠️ Notas Importantes

- **Mantenha a tela do celular ligada** durante a automação
- O programa usa `Ctrl+C` para parar
- Screenshots de debug são salvas em `debug_screenshots/`
- Se o OCR não funcionar bem, ajuste as regiões de recorte em `config.py`

