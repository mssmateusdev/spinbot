import os
import shutil

import PyInstaller.__main__


BUILD_NAME = "SpinBot_v0.6.2"


if os.path.exists(f"dist/{BUILD_NAME}"):
    try:
        shutil.rmtree(f"dist/{BUILD_NAME}")
    except Exception:
        pass

print(f"--- Iniciando Build do {BUILD_NAME} (No Console) ---")

args = [
    "gui.py",
    f"--name={BUILD_NAME}",
    "--onedir",
    "--noconfirm",
    "--clean",
    "--noconsole",
    "--hidden-import=uiautomator2",
    "--hidden-import=adbutils",
    "--hidden-import=PIL",
    "--hidden-import=numpy",
    "--hidden-import=cv2",
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=PySide6.QtWidgets",
    "--collect-all=uiautomator2",
    "--collect-all=adbutils",
    "--collect-all=PIL",
    "--collect-all=cv2",
    "--exclude-module=torch",
    "--exclude-module=torchvision",
    "--exclude-module=tensorflow",
    "--exclude-module=tensorboard",
    "--exclude-module=scipy",
    "--exclude-module=skimage",
    "--exclude-module=tkinter",
    "--add-data=assets/templates;assets/templates",
    "--add-data=icon.png;.",
    "--add-data=adb.exe;.",
    "--add-data=AdbWinApi.dll;.",
    "--add-data=AdbWinUsbApi.dll;.",
    "--distpath=dist",
]

if os.path.exists("icon.png"):
    args.append("--icon=icon.png")

print(f"Executando PyInstaller com args: {args}")
PyInstaller.__main__.run(args)

print("--- Build Concluido! ---")
print(f"Verifique a pasta 'dist/{BUILD_NAME}'")
