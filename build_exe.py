import PyInstaller.__main__
import os
import shutil

# Limpar dist anterior
if os.path.exists('dist/SpinBot_v0.4.0'):
    try:
        shutil.rmtree('dist/SpinBot_v0.4.0')
    except:
        pass

print("--- Iniciando Build do SpinBot (No Console) ---")

args = [
    'gui.py',                      # Script principal
    '--name=SpinBot_v0.4.0',       # Nome do executável (v0.4.0)
    '--onedir',                    # Pasta única (mais rápido que onefile)
    '--noconfirm',                 # Substituir destino sem perguntar
    '--clean',                     # Limpar cache
    '--noconsole',                 # Ocultar janela do CMD (apenas GUI)
    
    # Imports ocultos
    '--hidden-import=uiautomator2',
    '--hidden-import=adbutils',
    '--hidden-import=PIL',
    '--hidden-import=numpy',
    '--hidden-import=pytesseract',
    
    # Coletar dados
    '--collect-all=uiautomator2',
    '--collect-all=adbutils',
    '--collect-all=PIL',
    # 'pytesseract' is a module, not a package, so collect-all skip it anyway
    
    # Adicionar ícone e binários do ADB aos dados internos
    '--add-data=icon.png;.',
    '--add-data=adb.exe;.',
    '--add-data=AdbWinApi.dll;.',
    '--add-data=AdbWinUsbApi.dll;.',
    '--distpath=dist',
]

# Verificar se existe ícone
if os.path.exists('icon.png'):
    args.append('--icon=icon.png')

print(f"Executando PyInstaller com args: {args}")
PyInstaller.__main__.run(args)

print("--- Build Concluído! ---")
print("Verifique a pasta 'dist/SpinBot'")
