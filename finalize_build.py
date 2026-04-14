import os
import shutil


BUILD_NAME = "SpinBot_v0.6.4"
DIST_PATH = f"dist/{BUILD_NAME}"


try:
    os.makedirs(DIST_PATH, exist_ok=True)

    if os.path.exists("CHANGELOG.txt"):
        shutil.copy("CHANGELOG.txt", DIST_PATH)
        print("CHANGELOG.txt copiado.")

    if os.path.exists("icon.png"):
        shutil.copy("icon.png", DIST_PATH)
        print("icon.png copiado.")

    src_prof = "device_profiles"
    dst_prof = os.path.join(DIST_PATH, "device_profiles")
    if os.path.exists(src_prof):
        if os.path.exists(dst_prof):
            shutil.rmtree(dst_prof)
        shutil.copytree(src_prof, dst_prof)
        print("device_profiles copiados.")
    else:
        os.makedirs(dst_prof, exist_ok=True)

    print(f"[SUCESSO] Instalacao finalizada em {DIST_PATH}")
except Exception as exc:
    print(f"[ERRO] Falha na copia final: {exc}")
