"""El dominio del CRM vive en `assistant.packs.crm` (repo crm-agente0). Este paquete solo lo re-exporta para que el código del producto
(`app.routes.crm`, workers) siga importando `app.crm.*` sin copias: una sola fuente de verdad."""
import importlib
import pkgutil
import sys

import assistant.packs.crm as _pack

for _m in pkgutil.iter_modules(_pack.__path__):
    sys.modules[f"{__name__}.{_m.name}"] = importlib.import_module(f"assistant.packs.crm.{_m.name}")
sys.modules[__name__].__dict__.update({k: v for k, v in vars(_pack).items() if not k.startswith("__")})
__path__ = _pack.__path__

# CRM_NUCLEO=agente0: el chat del CRM corre su bucle sobre el núcleo de Alan (perfil crm). Sin la variable, el bucle propio.
import os as _os  # noqa: E402

if _os.getenv("CRM_NUCLEO") == "agente0":
    from assistant.packs.crm import agente_diseno as _ad
    from assistant.profiles.crm import bucle as _bucle

    _ad._responder = _bucle.responder
