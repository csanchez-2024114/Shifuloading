"""Crea backend/.env para desarrollar en tu computadora, con claves de seguridad aleatorias.

Uso (desde la carpeta backend):
    python scripts/crear_env_local.py

- No pisa un .env que ya exista.
- Las claves de seguridad (SECRET_KEY, ENCRYPTION_*) se generan aquí, al azar, y son solo tuyas.
- OPENAI_API_KEY queda con el marcador "sk-pendiente-…" (el servidor exige que tenga algo para arrancar) y TAVILY_API_KEY vacía: cada
  persona crea las suyas (ver docs/CREAR_CLAVES_ENV.md) y las pega en el archivo. Mientras sea el marcador, el CRM funciona en
  "modo básico" (reglas), sin IA, y no llama a OpenAI.
- Supone MongoDB en el puerto 27017 y Redis en el 6379 (ver COMO_CORRERLO.md para levantarlos con Docker).
"""
import base64
import os
import secrets
import sys
from pathlib import Path


def fernet() -> str:
    """Una clave Fernet es 32 bytes al azar en base64 seguro para URL."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def contenido() -> str:
    return f"""# Generado por scripts/crear_env_local.py. Este archivo NO se sube al repositorio.
ENVIRONMENT=development
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=shifu_dev
REDIS_URL=redis://localhost:6379

# Seguridad: generadas al azar para tu computadora
SECRET_KEY={secrets.token_hex(32)}
ENCRYPTION_KEY={fernet()}
ENCRYPTION_SALT={secrets.token_hex(16)}
SECRETS_ENCRYPTION_KEY={fernet()}

# IA: crea tus propias claves (docs/CREAR_CLAVES_ENV.md) y pégalas aquí, sin comillas ni espacios.
# El servidor necesita que OPENAI_API_KEY tenga ALGO para arrancar; mientras diga "sk-pendiente..." el CRM trabaja en modo básico (sin IA).
OPENAI_API_KEY=sk-pendiente-pega-aqui-tu-clave
TAVILY_API_KEY=

# Frontend local
FRONTEND_URL=http://localhost:5180
BACKEND_BASE_URL=http://localhost:5000
CORS_ALLOWED_ORIGINS=http://localhost:5180
RATE_LIMIT_ENABLED=false
"""


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / ".env"
    if destino.exists():
        print(f"Ya existe {destino}. No lo toqué. Bórralo si quieres que genere uno nuevo.")
        return 1
    destino.write_text(contenido(), encoding="utf-8", newline="\n")
    print(f"Listo: creé {destino}")
    print("Falta pegar tu OPENAI_API_KEY (y, si quieres búsqueda en internet, TAVILY_API_KEY). Guía: docs/CREAR_CLAVES_ENV.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
