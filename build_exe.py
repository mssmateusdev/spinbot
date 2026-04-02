import PyInstaller.__main__
import os
import shutil

# Limpar dist anterior
if os.path.exists('dist/SpinBot_v0.6.1'):
    try:
        shutil.rmtree('dist/SpinBot_v0.6.1')
    except:
        pass

print("--- Iniciando Build do SpinBot v0.6.1 (No Console) ---")

args = [
    'gui.py',                      # Script principal
    '--name=SpinBot_v0.6.1',       # Nome do executável (v0.6.1)
    '--onedir',                    
    '--noconfirm',                 
    '--clean',                     
    '--noconsole',                 
    
    # Imports ocultos e Coletas
    '--hidden-import=uiautomator2',
    '--hidden-import=adbutils',
    '--hidden-import=PIL',
    '--hidden-import=numpy',
    '--hidden-import=cv2',
    
    '--collect-all=uiautomator2',
    '--collect-all=adbutils',
    '--collect-all=PIL',
    '--collect-all=cv2',
    '--exclude-module=torch',
    '--exclude-module=torchvision',
    '--exclude-module=tensorflow',
    '--exclude-module=tensorboard',
    '--exclude-module=scipy',
    '--exclude-module=skimage',
    
    # Adicionar dados (Templates de imagem e binários ADB)
    '--add-data=assets/templates;assets/templates',
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
