"""Genera src/plantillas/marca-base.css: las reglas del CRM base (src/crm.css, src/crm-extra.css) que tienen los colores de
Shifu escritos a mano (morado #7c5cff / verde #22d3a6), reescritas para usar los tokens de marca (--morado, --acento).
Así el branding llega a TODO sin tocar el CRM de Carlos. Volver a correr si cambia el CSS base:
    python3 laboratorio/servidor/generar-marca-css.py"""
import re, pathlib
raiz = pathlib.Path(__file__).resolve().parents[2]
MOR = re.compile(r'rgba\(\s*124,\s*92,\s*255,\s*([\d.]+)\s*\)'); VER = re.compile(r'rgba\(\s*34,\s*211,\s*166,\s*([\d.]+)\s*\)')
def tok(v):
    v = MOR.sub(lambda m: f'color-mix(in srgb, var(--morado) {round(float(m.group(1))*100)}%, transparent)', v)
    v = VER.sub(lambda m: f'color-mix(in srgb, var(--acento) {round(float(m.group(1))*100)}%, transparent)', v)
    return re.sub(r'#7c5cff', 'var(--morado)', re.sub(r'#22d3a6', 'var(--acento)', v, flags=re.I), flags=re.I)
salida = ['/* GENERADO por laboratorio/servidor/generar-marca-css.py — no editar a mano. */']
for f in ['src/crm.css', 'src/crm-extra.css']:
    css = (raiz / f).read_text()
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    for sel, cuerpo in re.findall(r'([^{}@]+)\{([^{}]*)\}', css):
        decl = [d.strip() for d in cuerpo.split(';') if d.strip()]
        conColor = [d for d in decl if MOR.search(d) or VER.search(d) or re.search(r'#(7c5cff|22d3a6)', d, re.I)]
        conColor = [d for d in conColor if not d.startswith('--')]  # las definiciones de variables base no se tocan
        if not conColor: continue
        sels = []
        for s in sel.split(','):
            s = s.strip()
            if not s or s.startswith(('from', 'to')) or re.match(r'^\d+%', s): continue
            sels.append(re.sub(r'^\.mc(?=[\[.:\s]|$)', '.mc.pl', s) if s.startswith('.mc') and not s.startswith('.mc-') else f'.pl {s}')
        if sels: salida.append(f"{', '.join(sels)} {{ {'; '.join(tok(d) for d in conColor)}; }}")
(raiz / 'laboratorio/src/plantillas/marca-base.css').write_text('\n'.join(salida) + '\n')
print(len(salida) - 1, 'reglas')
