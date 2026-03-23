import shutil
import os
import sys

# Script auxiliar para finalizar a build
try:
    dist_path = "dist/SpinBot_v0.4.0"
    if not os.path.exists(dist_path):
        os.makedirs(dist_path, exist_ok=True)
    
    # Copiar CHANGELOG
    if os.path.exists("CHANGELOG.txt"):
        shutil.copy("CHANGELOG.txt", dist_path)
        print("CHANGELOG.txt copiado.")

    # Copiar ícone para a pasta raíz também
    if os.path.exists("icon.png"):
        shutil.copy("icon.png", dist_path)
        print("icon.png copiado.")

    # Copiar perfis
    src_prof = "device_profiles"
    dst_prof = os.path.join(dist_path, "device_profiles")
    if os.path.exists(src_prof):
        if os.path.exists(dst_prof):
            shutil.rmtree(dst_prof)
        shutil.copytree(src_prof, dst_prof)
        print("device_profiles copiados.")
    else:
        os.makedirs(dst_prof, exist_ok=True)
        
    print(f"[SUCESSO] Instalação finalizada em {dist_path}")
    
except Exception as e:
    print(f"[ERRO] Falha na cópia final: {e}")
