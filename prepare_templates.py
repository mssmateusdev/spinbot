import os
from PIL import Image

# Pastas
OUTPUT_DIR = r"c:\Users\Mateus\Documents\Spinbot\assets\templates"
SOURCE_DIR = r"C:\Users\Mateus\.gemini\antigravity\brain\483c6c63-d68b-499c-af61-8698b6553c67"

def extract_close_x():
    # Na media__1774446804287.png o X circular está no Topo-Esquerdo
    img_path = os.path.join(SOURCE_DIR, "media__1774446804287.png")
    if not os.path.exists(img_path): return
    
    img = Image.open(img_path)
    # Recorte focado no X (ajustado para ser um template limpo)
    crop = img.crop((30, 25, 120, 115))
    crop.save(os.path.join(OUTPUT_DIR, "close_x.png"))
    print("Template close_x.png salvo.")

def extract_skip_next():
    # Na media__1774566183060.png o botão Continuar >| está no Topo-Direito
    img_path = os.path.join(SOURCE_DIR, "media__1774566183060.png")
    if not os.path.exists(img_path): return
        
    img = Image.open(img_path)
    w, h = img.size
    # Recorte focado apenas no ícone >| do botão Continuar
    # Tipicamente fica ali por x=850-1050, y=30-150
    crop = img.crop((w - 180, 40, w - 40, 140))
    crop.save(os.path.join(OUTPUT_DIR, "skip_next.png"))
    print("Template skip_next.png salvo.")

if __name__ == "__main__":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    extract_close_x()
    extract_skip_next()
