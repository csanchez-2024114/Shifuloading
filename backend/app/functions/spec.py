"""Contrato de las funciones de apps: ficha (FunctionSpec), app (AppSpec) y resultado (Result).

Es la base que programan los juniors. Ver doc/funciones/CONTRATO.md.
Todo lo de este archivo es puro (sin Mongo, sin red) para que se pueda probar solo.
"""
import hashlib
import json
import re
from enum import Enum
from typing import Any, Optional

from pydantic import Field, field_validator, model_validator

from app.models._base import AppBaseModel

CONTRACT_VERSION = 1

# app.recurso.verbo, todo en minusculas e ingles. Nunca se renombra una vez publicada.
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

# Las descripciones las lee el agente (para BUSCAR la funcion y para llenar sus argumentos): en ingles y completas.
# Ambos minimos son hipotesis: se ajustan midiendo el acierto de recuperacion del selector (tarea T5 del plan maestro).
MIN_DESCRIPTION_CHARS = 200
MIN_FIELD_DESCRIPTION_CHARS = 10
_SPANISH_CHARS = re.compile(r"[áéíóúñü¿¡]", re.IGNORECASE)
_SPANISH_WORDS = frozenset({"el", "la", "los", "las", "del", "para", "una", "por", "con", "sin", "que", "como", "cuando", "desde", "hasta", "esta", "este"})


def looks_spanish(text: str) -> bool:
    """Heuristica barata (puede fallar con texto sin tildes ni palabras comunes): atrapa lo evidente, no reemplaza la revision."""
    if _SPANISH_CHARS.search(text):
        return True
    return sum(1 for w in re.findall(r"[a-zA-Z]+", text.lower()) if w in _SPANISH_WORDS) >= 2


def _strip_wording(obj: Any) -> Any:
    """Quita description/title/examples de un esquema: el texto no es parte del contrato (mejorarlo no rompe a nadie)."""
    if isinstance(obj, dict):
        return {k: _strip_wording(v) for k, v in obj.items() if k not in ("description", "title", "examples")}
    if isinstance(obj, list):
        return [_strip_wording(v) for v in obj]
    return obj


class Verb(str, Enum):
    create = "create"
    read = "read"
    update = "update"
    delete = "delete"


class Status(str, Enum):
    draft = "draft"
    testing = "testing"
    active = "active"
    degraded = "degraded"
    obsolete = "obsolete"


class ConfirmationPolicy(str, Enum):
    assume = "assume"                      # leer, o crear/actualizar interno y reversible: asumir y decir el supuesto
    draft_and_confirm = "draft_and_confirm"  # sale al exterior: borrador y pedir un si
    ask = "ask"                            # eliminar o irreversible: preguntar


class ErrorCode(str, Enum):
    auth_expired = "auth_expired"
    missing_scope = "missing_scope"
    rate_limited = "rate_limited"
    not_found = "not_found"
    invalid_input = "invalid_input"
    upstream_changed = "upstream_changed"
    upstream_down = "upstream_down"
    # Agregados al implementar (cambio del contrato propuesto): cubren "ninguna cuenta" y "varias sin elegir".
    missing_connection = "missing_connection"
    account_selection_required = "account_selection_required"
    # v0.6.6: la cuenta tiene el permiso pero no acceso a ESE recurso (archivo no compartido); reconectar no lo arregla.
    access_denied = "access_denied"


# codigo -> (reintentable, accion para el usuario). Son datos: el responder los convierte en texto y botones.
_ERROR_DEFAULTS: dict[ErrorCode, tuple[bool, str]] = {
    ErrorCode.auth_expired: (False, "reconnect_app"),
    ErrorCode.missing_scope: (False, "grant_scopes"),
    ErrorCode.rate_limited: (True, "retry_later"),
    ErrorCode.not_found: (False, "fix_input"),
    ErrorCode.invalid_input: (False, "fix_input"),
    ErrorCode.upstream_changed: (False, "report_bug"),
    ErrorCode.upstream_down: (True, "retry_later"),
    ErrorCode.missing_connection: (False, "connect_app"),
    ErrorCode.account_selection_required: (False, "choose_account"),
    ErrorCode.access_denied: (False, "request_access"),
}


class AuthType(str, Enum):
    none = "none"
    api_key = "api_key"
    bearer = "bearer"
    basic = "basic"
    custom_params = "custom_params"
    oauth2_code = "oauth2_code"
    # Declarados para que el contrato los conozca, pero SIN estrategia todavia (ver doc/funciones/AUTENTICACION.md):
    oauth2_client_credentials = "oauth2_client_credentials"
    oauth1 = "oauth1"
    hmac_signature = "hmac_signature"


class AuthSpec(AppBaseModel):
    """Como se autentica una app. Los campos que no apliquen al tipo se ignoran."""
    type: AuthType
    scopes: list[str] = Field(default_factory=list)  # todos los scopes que la app puede pedir (los de cada funcion van en FunctionSpec)
    placement: str = "header"                         # api_key / custom_params: "header" o "query"
    header_name: str = "Authorization"                # api_key y bearer: nombre del header
    scheme: Optional[str] = None                      # bearer/oauth2: None = "Bearer", "" = token crudo (ClickUp), "Token", "Bot"...; api_key: prefijo opcional
    param_names: list[str] = Field(default_factory=list)  # custom_params: nombres de los campos (ej. key, token)
    authorize_url: Optional[str] = None               # oauth2_code: pantalla de consentimiento de la plataforma
    authorize_params: dict[str, str] = Field(default_factory=dict)  # oauth2_code: extras de la URL (Dropbox: token_access_type=offline)
    pkce: bool = False                                # oauth2_code: la plataforma exige PKCE (S256)
    token_url: Optional[str] = None                   # oauth2_code: endpoint de intercambio del codigo y de refresco
    client_id_env: Optional[str] = None               # oauth2_code: variable de entorno con el client_id
    client_secret_env: Optional[str] = None           # oauth2_code: variable de entorno con el client_secret
    scope_error_marker: Optional[str] = None          # regex que, dentro de un 400/401, significa 'falta un permiso' y no 'token vencido' ni 'entrada invalida'
    token_invalid_marker: Optional[str] = None        # regex que, dentro de un 403, significa 'token invalido o vencido' (Salesforce: Bad_OAuth_Token) y se trata como un 401

    @field_validator("placement")
    @classmethod
    def _placement_ok(cls, v: str) -> str:
        if v not in ("header", "query"):
            raise ValueError("placement debe ser 'header' o 'query'")
        return v


class AppSpec(AppBaseModel):
    app: str                                          # nombre estable: dropbox, brevo...
    provider_keys: list[str]                          # valores de `provider` en user_connected_accounts
    auth: AuthSpec
    api_version: str = ""
    multi_account: bool = True                        # False: la app solo admite una cuenta (marca para adaptar despues)
    whoami: Optional[str] = None                      # id de una funcion de lectura que dice quien es la cuenta (opcional)

    @field_validator("app")
    @classmethod
    def _app_ok(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError("app en minusculas, sin espacios")
        return v

    @field_validator("provider_keys")
    @classmethod
    def _keys_ok(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("provider_keys no puede estar vacio")
        return v


class Example(AppBaseModel):
    name: str = "default"
    input: dict[str, Any] = Field(default_factory=dict)
    output: Optional[dict[str, Any]] = None           # respuesta tipica; sirve de resultado simulado


class FunctionSpec(AppBaseModel):
    id: str
    version: int = Field(ge=1)                        # version mayor del contrato; un cambio que rompe la sube
    app: str
    upstream_api: str = ""                            # version de la API externa que usa (ej. "v3")
    verb: Verb
    exits_outside: bool = False                       # correo, mensaje, invitacion, publicacion
    reversible: bool = True
    scopes: list[str] = Field(default_factory=list)   # scopes que necesita esta funcion
    multi_account: bool = True
    description: str                                  # corta y neutra, sin instrucciones de enrutamiento
    examples: list[Example] = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    status: Status = Status.draft
    contract_version: int = CONTRACT_VERSION

    @field_validator("id")
    @classmethod
    def _id_ok(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("id debe ser app.recurso.verbo en minusculas (ej. dropbox.files.list)")
        return v

    @field_validator("description")
    @classmethod
    def _description_ok(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < MIN_DESCRIPTION_CHARS:
            raise ValueError(
                f"la descripcion debe ser completa (minimo {MIN_DESCRIPTION_CHARS} caracteres, tiene {len(v)}): que hace, cuando usarla, "
                "que devuelve, parametros importantes y limites. El agente la usa para buscar y elegir la funcion")
        if looks_spanish(v):
            raise ValueError("la descripcion debe estar en INGLES (el agente trabaja en ingles; busca y elige funciones con ese texto)")
        return v

    @model_validator(mode="after")
    def _coherent(self) -> "FunctionSpec":
        if self.id.split(".", 1)[0] != self.app:
            raise ValueError(f"el id '{self.id}' debe empezar por la app '{self.app}'")
        if self.verb == Verb.read and self.exits_outside:
            raise ValueError("una funcion de lectura no puede salir al exterior")
        return self

    @property
    def confirmation_policy(self) -> ConfirmationPolicy:
        """Derivada de (verbo, sale al exterior, reversible); no se guarda aparte."""
        if self.verb == Verb.delete or not self.reversible:
            return ConfirmationPolicy.ask
        if self.exits_outside:
            return ConfirmationPolicy.draft_and_confirm
        return ConfirmationPolicy.assume

    @property
    def spec_hash(self) -> str:
        """Huella del CONTRATO: sin status (se cambia en Mongo sin desplegar) y sin texto (description, examples y las
        description/title de los esquemas). Mejorar una descripcion no cambia la huella; tocar campos, tipos, verbo,
        scopes o marcas si."""
        payload = self.model_dump(mode="json", exclude={"status", "description", "examples"})
        payload["input_schema"] = _strip_wording(payload["input_schema"])
        payload["output_schema"] = _strip_wording(payload["output_schema"])
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ErrorInfo(AppBaseModel):
    code: ErrorCode
    message: str = ""
    retryable: bool = False
    user_action: str = "none"

    @classmethod
    def of(cls, code: ErrorCode, message: str = "") -> "ErrorInfo":
        retryable, action = _ERROR_DEFAULTS[code]
        return cls(code=code, message=message, retryable=retryable, user_action=action)


class ResultMeta(AppBaseModel):
    function_id: str
    version: int
    account_id: Optional[str] = None
    duration_ms: int = 0
    simulated: bool = False


class Result(AppBaseModel):
    """Resultado unico de toda funcion: {ok, data} o {ok:false, error}. Nunca se lanza una excepcion al agente."""
    ok: bool
    data: Any = None
    error: Optional[ErrorInfo] = None
    meta: Optional[ResultMeta] = None

    @model_validator(mode="after")
    def _shape(self) -> "Result":
        if self.ok and self.error is not None:
            raise ValueError("un resultado ok no puede traer error")
        if not self.ok and self.error is None:
            raise ValueError("un resultado fallido necesita error")
        return self

    @classmethod
    def success(cls, data: Any, meta: Optional[ResultMeta] = None) -> "Result":
        return cls(ok=True, data=data, meta=meta)

    @classmethod
    def failure(cls, code: ErrorCode, message: str = "", meta: Optional[ResultMeta] = None) -> "Result":
        return cls(ok=False, error=ErrorInfo.of(code, message), meta=meta)
