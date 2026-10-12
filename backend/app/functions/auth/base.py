"""Base de las estrategias de autenticacion.

Una estrategia sabe aplicar una credencial a una peticion HTTP y, si el metodo lo permite, refrescarla.
El handler de una funcion nunca ve el secreto crudo: solo llama a conn.request(...).

Para agregar un metodo nuevo: una clase que herede de AuthStrategy, decorada con @register_auth(AuthType.xxx),
mas un test. Ver doc/funciones/AUTENTICACION.md.
"""
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.functions.spec import AuthSpec, AuthType


@dataclass
class Credentials:
    """Credenciales ya descifradas. 'token' y 'refresh_token' para un solo campo; los demas nombres para varios campos."""
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def token(self) -> str:
        return self.fields.get("token", "")


@dataclass
class RequestParts:
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)


class AuthStrategy:
    can_refresh: bool = False

    def apply(self, req: RequestParts, creds: Credentials, spec: AuthSpec) -> None:
        raise NotImplementedError

    async def refresh(self, client: httpx.AsyncClient, creds: Credentials, spec: AuthSpec) -> Optional[dict[str, str]]:
        """Devuelve campos nuevos ({'access_token': ..., 'refresh_token'?: ...}) o None si no se pudo."""
        return None


_REGISTRY: dict[AuthType, AuthStrategy] = {}


def register_auth(auth_type: AuthType):
    def deco(cls):
        _REGISTRY[auth_type] = cls()
        return cls
    return deco


def get_strategy(auth_type: AuthType) -> AuthStrategy:
    try:
        return _REGISTRY[auth_type]
    except KeyError:
        raise NotImplementedError(
            f"No hay estrategia de autenticacion para '{auth_type.value}'. "
            "Esta declarada en el contrato pero sin implementar (ver doc/funciones/AUTENTICACION.md)."
        ) from None


def implemented_types() -> set[AuthType]:
    return set(_REGISTRY)
