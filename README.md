# SpinBot

Desktop app em Python/PySide6 para orquestrar automacoes Android via ADB e uiautomator2.

## Estrutura

- `app/`: bootstrap e wiring da aplicacao.
- `ui/`: janelas, widgets e sinais de interface.
- `automation/`: runner do fluxo, estrategias e orquestracao multi-instancia.
- `adb/`: API interna para ADB/uiautomator2.
- `devices/`: descoberta e gerenciamento de dispositivos.
- `services/`: configuracao, logs, paths e persistencia.
- `models/`: dataclasses e enums compartilhados.
- `core/`: regras puras e funcoes testaveis.
- `utils/`: helpers reutilizaveis.
- `legacy/`: arquivos antigos preservados como referencia historica.

## Desenvolvimento

```bash
python -m pip install -r requirements.txt
python gui.py
```

## Testes

```bash
python -m unittest discover -s tests
```

## Build Windows

O projeto mantem `gui.py` como entrada compativel para PyInstaller.

```bash
python -m PyInstaller --noconfirm --clean SpinBot_v0.6.4.spec
```

Saida esperada:

```text
dist/SpinBot_v0.6.4/SpinBot_v0.6.4.exe
```

Como o build esta em modo `onedir`, envie a pasta `dist/SpinBot_v0.6.4` inteira, incluindo `_internal`.
