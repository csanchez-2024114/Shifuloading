"""
Genera doc/postman/<app>.json (una coleccion por app) y la plantilla de entorno desde las fichas del codigo.
Determinista: volver a correrlo sin cambios no modifica nada. Uso:  python scripts/export_postman.py
Ojo: sobrescribe las colecciones. Si guardaste respuestas de ejemplo en Postman, re-exporta DESDE Postman
despues de generar (o trabaja sobre la coleccion generada) para no perderlas.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.functions.postman import collection_for_app, environment_template, render
from app.functions.registry import list_apps, load_all

OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "doc", "postman")


def main() -> None:
    load_all()
    os.makedirs(OUT, exist_ok=True)
    for app in list_apps():
        with open(os.path.join(OUT, f"{app.app}.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(render(collection_for_app(app.app)))
    with open(os.path.join(OUT, "shifu.postman_environment.template.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render(environment_template()))
    print(f"postman: {len(list_apps())} colecciones + plantilla de entorno en doc/postman/")


if __name__ == "__main__":
    main()
