"""Piezas elegidas en pantalla: nota solo para el modelo (no va en el texto que miran los cercos)."""


def nota_seleccion(seleccion: list[dict] | None) -> str:
    if not seleccion:
        return ""
    partes = []
    for x in seleccion:
        if x.get("tipo") == "bloque":
            partes.append(f"bloque {x.get('id')} «{x.get('nombre')}»")
        elif x.get("tipo") == "pestaña":
            partes.append(f"pestaña {x.get('id')} «{x.get('nombre')}»")
        else:
            partes.append(str(x.get("nombre") or x.get("id") or ""))
    if not partes:
        return ""
    return (
        f"[La persona SELECCIONÓ en su pantalla (medido por el código): {'; '.join(partes)}. "
        "Cuando diga \"esto\", \"estos\", \"aquí\" se refiere EXACTAMENTE a eso: usa esos ids.]"
    )
