"""Endpoints internos para ver y probar las funciones de apps. Ver doc/funciones/POSTMAN.md.

Acceso: cualquier usuario autenticado (decision del usuario), pero siempre sobre las conexiones del propio user_id del
token: nunca se ejecuta con cuentas de otra persona. Mitigaciones: limite de ritmo, auditoria de cada prueba,
las funciones que no son de lectura se simulan salvo allow_write=true, e interruptor FUNCTIONS_TEST_ENABLED.
"""
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.constants import Collections
from app.core.limiter import limiter
from app.database import get_current_user, get_db
from app.functions.auth import get_strategy
from app.functions.registry import RegisteredFunction, RegistryError, get_app, get_function, list_functions, load_all
from app.functions.runner import execute
from app.functions.spec import Verb
from app.services.audit_service import log_event

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_ACCOUNTS_PER_TEST = 25  # hipotesis: protege el ritmo hacia la app externa; se ajusta con el uso real


def _enabled() -> None:
    if os.getenv("FUNCTIONS_TEST_ENABLED", "true").strip().lower() in ("0", "false", "no", "off"):
        raise HTTPException(status_code=404, detail="Not Found")


def _loaded() -> None:
    # Carga perezosa: una ficha invalida no tumba el arranque del agente; se ve aqui, en pruebas y en CI.
    try:
        load_all()
    except RegistryError as exc:
        logger.error("Registro de funciones invalido: %s", exc)
        raise HTTPException(status_code=500, detail=f"Registro de funciones invalido: {exc}") from exc


def _fn(function_id: str, version: Optional[int]) -> RegisteredFunction:
    try:
        return get_function(function_id, version)
    except RegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _mongo_status(db: Any) -> dict[tuple[str, int], str]:
    """El status vive en Mongo despues de publicar (se cambia sin desplegar); si no esta publicada, vale el del codigo."""
    try:
        docs = await db[Collections.FUNCTIONS].find({}, {"id": 1, "version": 1, "status": 1}).to_list(length=5000)
    except Exception:
        return {}
    return {(d["id"], d["version"]): d.get("status") for d in docs}


def _summary(fn: RegisteredFunction, statuses: dict) -> dict[str, Any]:
    s = fn.spec
    return {"id": s.id, "version": s.version, "app": s.app, "verb": s.verb.value, "exits_outside": s.exits_outside,
            "reversible": s.reversible, "confirmation_policy": s.confirmation_policy.value,
            "status": statuses.get((s.id, s.version)) or s.status.value, "description": s.description}


def check_spec(fn: RegisteredFunction) -> list[dict[str, Any]]:
    """Revisiones de la ficha (el registro ya valida casi todo al cargar; aqui se muestran en el informe)."""
    s, app = fn.spec, get_app(fn.spec.app)
    checks = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    add("id_formato", s.id.split(".")[0] == s.app, s.id)
    add("ejemplos", len(s.examples) >= 1, f"{len(s.examples)} ejemplo(s)")
    try:
        fn.input_model.model_validate(s.examples[0].input)
        add("ejemplo_cumple_input_schema", True)
    except Exception as exc:
        add("ejemplo_cumple_input_schema", False, str(exc)[:200])
    try:
        get_strategy(app.auth.type)
        add("autenticacion_implementada", True, app.auth.type.value)
    except NotImplementedError as exc:
        add("autenticacion_implementada", False, str(exc)[:200])
    extra = set(s.scopes) - set(app.auth.scopes) if app.auth.scopes else set()
    add("scopes_dentro_de_la_app", not extra, ", ".join(sorted(extra)))
    return checks


class TestBody(BaseModel):
    input: Optional[dict[str, Any]] = Field(default=None, description="Entrada de la funcion; vacio = el primer ejemplo de la ficha")
    account_ids: list[str] = Field(default_factory=list, description="Vacio = cuenta por defecto; una o varias = una ejecucion por cuenta (sin minimo)")
    allow_write: bool = Field(default=False, description="Sin esto, las funciones que no son de lectura se simulan")
    version: Optional[int] = Field(default=None, description="Version de la funcion; vacio = la mayor")


@router.get("/functions")
async def list_all(request: Request, user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    _enabled(); _loaded()
    statuses = await _mongo_status(db)
    return {"functions": [_summary(f, statuses) for f in list_functions()]}


@router.get("/functions/{function_id}")
async def get_one(function_id: str, version: Optional[int] = None, user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    _enabled(); _loaded()
    fn = _fn(function_id, version)
    statuses = await _mongo_status(db)
    return {**_summary(fn, statuses), "spec": fn.spec.model_dump(mode="json"), "spec_hash": fn.spec.spec_hash,
            "app": get_app(fn.spec.app).model_dump(mode="json")}


@router.post("/functions/{function_id}/test")
@limiter.limit("30/minute")
async def test_function(request: Request, function_id: str, body: TestBody, user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    _enabled(); _loaded()
    fn = _fn(function_id, body.version)
    if len(body.account_ids) > MAX_ACCOUNTS_PER_TEST:
        raise HTTPException(status_code=422, detail=f"Maximo {MAX_ACCOUNTS_PER_TEST} cuentas por prueba.")
    user_id = str(user.get("_id") or user.get("id"))
    app = get_app(fn.spec.app)
    raw_input = body.input if body.input is not None else fn.spec.examples[0].input
    simulate = fn.spec.verb != Verb.read and not body.allow_write

    runs = []
    for account in (body.account_ids or [None]):
        result = await execute(fn, raw_input, db=db, user_id=user_id, account_id=account, simulate=simulate)
        run: dict[str, Any] = {"requested_account_id": account, "result": result.model_dump(mode="json"), "identity": None}
        if result.ok and not simulate and app.whoami:
            who = result if fn.spec.id == app.whoami else await execute(get_function(app.whoami), {}, db=db, user_id=user_id, account_id=result.meta.account_id)
            expected = result.meta.account_id
            got = who.data.get("account_id") if who.ok and isinstance(who.data, dict) else None
            run["identity"] = {"expected": expected, "got": got, "match": got is not None and str(got) == str(expected) and (account is None or str(account) == str(expected)),
                               "whoami": app.whoami, "error": None if who.ok else who.error.code.value}
        runs.append(run)

    ok_runs = sum(1 for r in runs if r["result"]["ok"])
    mismatches = sum(1 for r in runs if r["identity"] and not r["identity"]["match"])
    log_event(user_id, "function_tested", fn.spec.id, db, outcome="success" if ok_runs == len(runs) and not mismatches else "failure",
              extra={"version": fn.spec.version, "accounts": len(runs), "ok": ok_runs, "simulated": simulate, "identity_mismatches": mismatches})
    return {
        "function": {"id": fn.spec.id, "version": fn.spec.version, "spec_checks": check_spec(fn)},
        "runs": runs,
        "summary": {"runs": len(runs), "ok": ok_runs, "failed": len(runs) - ok_runs, "simulated": simulate, "identity_mismatches": mismatches},
    }
