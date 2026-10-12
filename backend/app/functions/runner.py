"""Ejecutor: unica via para correr una funcion. SIEMPRE devuelve un Result; nunca lanza al agente.

Excepcion inesperada dentro de un handler -> upstream_changed (casi siempre es una respuesta con otra forma de la
esperada) y se registra con el traceback completo. Nunca se oculta un fallo.
"""
import asyncio
import logging
import time
from typing import Any, Optional

import httpx
from pydantic import BaseModel, ValidationError

from app.functions.connections import get_connection
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import RegisteredFunction, get_app
from app.functions.spec import ErrorCode, Result, ResultMeta

logger = logging.getLogger("functions.runner")

DEFAULT_FUNCTION_TIMEOUT = 60.0


def _short(exc: ValidationError) -> str:
    err = exc.errors()[0]
    where = ".".join(str(p) for p in err.get("loc", ()))
    return f"{where}: {err.get('msg', 'invalido')}" if where else err.get("msg", "invalido")


async def execute(fn: RegisteredFunction, raw_input: Optional[dict], *, db: Any, user_id: str,
                  account_id: Optional[str] = None, dry_run: bool = False, simulate: bool = False,
                  transport: Optional[httpx.AsyncBaseTransport] = None,
                  timeout: float = DEFAULT_FUNCTION_TIMEOUT) -> Result:
    started = time.monotonic()
    spec = fn.spec
    meta = ResultMeta(function_id=spec.id, version=spec.version, account_id=account_id, simulated=simulate)

    def done(result: Result) -> Result:
        result.meta = meta.model_copy(update={"duration_ms": int((time.monotonic() - started) * 1000)})
        return result

    try:
        args = fn.input_model.model_validate(raw_input or {})
    except ValidationError as exc:
        return done(Result.failure(ErrorCode.invalid_input, _short(exc)))

    if simulate:  # no se llama a la app externa: se devuelve el ejemplo de la ficha
        example = spec.examples[0].output
        return done(Result.success(example if example is not None else {}))

    try:
        conn = await get_connection(db, user_id, get_app(spec.app), account_id, transport=transport)
        meta = meta.model_copy(update={"account_id": conn.account_id})
        ctx = Context(user_id=user_id, conn=conn, account_id=conn.account_id, dry_run=dry_run)
        out = await asyncio.wait_for(fn.handler(ctx, args), timeout)
        # Siempre se revalida (aunque el handler ya devuelva el modelo): un modelo armado con model_construct no cumple nada.
        raw_out = out.model_dump() if isinstance(out, BaseModel) else out
        return done(Result.success(fn.output_model.model_validate(raw_out).model_dump(mode="json")))
    except FunctionError as exc:
        return done(Result.failure(exc.code, exc.message))
    except asyncio.TimeoutError:
        return done(Result.failure(ErrorCode.upstream_down, f"La funcion supero {timeout:.0f}s."))
    except ValidationError as exc:  # la respuesta de la app no cumple el contrato de salida
        return done(Result.failure(ErrorCode.upstream_changed, f"La respuesta de la app no cumple output_schema ({_short(exc)})."))
    except Exception as exc:
        logger.exception("[%s] excepcion inesperada en el handler", spec.id)
        return done(Result.failure(ErrorCode.upstream_changed, f"Error inesperado ({type(exc).__name__}); revisar el log."))
