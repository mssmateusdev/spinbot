"""Inspeciona todos os elementos na tela para encontrar o botão X do banner 'Recompensa concedida'."""
import uiautomator2 as u2

d = u2.connect("TC45MJWWTKO765BE")
w, h = d.window_size()
print(f"Tela: {w}x{h}\n")

# Buscar todos os elementos clicáveis ou com texto
print("=== TODOS os elementos com texto ===")
elements = d.xpath('//*[@text]').all()
for e in elements:
    text = e.attrib.get("text", "").strip()
    bounds = e.attrib.get("bounds", "")
    cls = e.attrib.get("class", "")
    desc = e.attrib.get("content-desc", "")
    rid = e.attrib.get("resource-id", "")
    click = e.attrib.get("clickable", "")
    print(f"  text='{text}' desc='{desc}' class='{cls}' rid='{rid}' click={click} bounds={bounds}")

print("\n=== TODOS os elementos com content-desc ===")
elements2 = d.xpath('//*[@content-desc]').all()
for e in elements2:
    text = e.attrib.get("text", "").strip()
    bounds = e.attrib.get("bounds", "")
    cls = e.attrib.get("class", "")
    desc = e.attrib.get("content-desc", "")
    rid = e.attrib.get("resource-id", "")
    click = e.attrib.get("clickable", "")
    print(f"  text='{text}' desc='{desc}' class='{cls}' rid='{rid}' click={click} bounds={bounds}")

print("\n=== Elementos clickáveis ===")
elements3 = d.xpath('//*[@clickable="true"]').all()
for e in elements3:
    text = e.attrib.get("text", "").strip()
    bounds = e.attrib.get("bounds", "")
    cls = e.attrib.get("class", "")
    desc = e.attrib.get("content-desc", "")
    rid = e.attrib.get("resource-id", "")
    print(f"  text='{text}' desc='{desc}' class='{cls}' rid='{rid}' bounds={bounds}")

print("\n=== Buscando textos específicos ===")
for t in ["Recompensa", "concedida", "×", "X", "✕", "✖", "Close", "Fechar"]:
    btn = d(text=t)
    if btn.exists(timeout=0.5):
        info = btn.info
        print(f"  ENCONTRADO: text='{t}' bounds={info.get('bounds')} desc='{info.get('contentDescription','')}'")
    else:
        btn2 = d(textContains=t)
        if btn2.exists(timeout=0.5):
            info2 = btn2.info
            print(f"  ENCONTRADO (contains): text contém '{t}' -> '{info2.get('text','')}' bounds={info2.get('bounds')}")
        else:
            print(f"  NÃO encontrado: '{t}'")

print("\n=== Buscando por description ===")
for desc in ["Close", "Fechar", "close", "dismiss", "Dismiss", "Recompensa"]:
    btn = d(description=desc)
    if btn.exists(timeout=0.3):
        info = btn.info
        print(f"  ENCONTRADO desc='{desc}': text='{info.get('text','')}' bounds={info.get('bounds')}")
    btn2 = d(descriptionContains=desc)
    if btn2.exists(timeout=0.3):
        info2 = btn2.info
        print(f"  ENCONTRADO descContains='{desc}': text='{info2.get('text','')}' desc='{info2.get('contentDescription','')}' bounds={info2.get('bounds')}")

print("\nDone!")
