"""
response_evaluator_node — "centinela" de calidad después del responder.

El código es solo el MECANISMO; las reglas viven como datos en Mongo (agent_personality.quality_control) para que un admin
las cambie, o se pivote a otro dominio, sin tocar código:

    quality_control: {
        enabled:     true | false          apaga el centinela
        max_retries: 4                      reintentos tras un rechazo (respaldo del código: 2)
        judge:       {model, mode}          quien juzga: modelo y modo ("single" = una llamada con todos los chequeos;
                                            "per_check" = un juez barato por chequeo, en paralelo)
        checks:      [{name, criterion,     los chequeos que se juzgan; se pueden agregar o quitar
                       blocking?,           false = solo informa (no fuerza reescritura)
                       method?,             "claims" = verificacion afirmacion por afirmacion contra el contexto
                       examples?}]          notas de calibracion sacadas de falsos positivos reales
    }

Se ejecuta en TODOS los turnos (también en chat puro): la calidad pesa más que la velocidad. Juzga la última respuesta
contra lo que el responder realmente recibió: el mensaje del usuario, las instrucciones obligatorias vigentes (p. ej.
pausa por app no conectada), los principios de la identidad, el conocimiento de plataforma y las reglas de voz.

Por que "per_check": en las pruebas un juez barato con 6 chequeos a la vez rechazaba respuestas buenas (60 % de rechazos, y
el juez independiente aprobaba todas las que agotaron reintentos) y se le escapaban matices. Con un solo criterio por
llamada cada juez tiene menos que sostener a la vez, y el costo sigue muy por debajo de un modelo grande.

Si falla algún chequeo y quedan reintentos → eval_feedback vuelve al responder, que reescribe desde cero.
Si ya no quedan reintentos la respuesta se entrega igual, pero el informe lo deja a la vista (action="exhausted").
El veredicto completo viaja en state["eval_report"]; la UI de pruebas lo muestra como centinela.
"""
import asyncio
import json
import logging
import os
import re
from typing import Literal, Optional

from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.shared.nodes.action_runner import format_action_results
from app.agent.shared.helpers.platform_context import unavailable_catalog_names, app_capability, build_platform_context, unavailable_apps
from app.agent.shared.helpers.identity_loader import get_agent_identity, get_agent_personality, render_voice

logger = logging.getLogger(__name__)

# Respaldo genérico (sin dominio) si el documento de personalidad no define quality_control: los 3 criterios originales.
_DEFAULT_MAX_RETRIES = 2
_HISTORY_MESSAGES = 6   # mensajes previos que ve el juez (sin el, recordar algo dicho antes parecia "inventar")
_OLDER_USER_MESSAGES = 40  # mensajes del usuario anteriores a esa ventana (resumidos a 200 caracteres)
_DEFAULT_CHECKS = [
    {"name": "no_fabrication", "criterion": "Every factual claim is consistent with the context provided; nothing is invented."},
    {"name": "answers_request", "criterion": "The reply directly addresses the user's actual intent."},
    {"name": "format", "criterion": "No raw JSON, no unclosed Markdown blocks, no garbled or duplicated structure."},
]

# Método de juicio (cómo evaluar), no reglas de negocio.
_METHOD = """\
You are a strict quality sentinel for an AI assistant's replies. Judge the REPLY against the context you are given.
Run exactly the checks listed below and return one entry per check, using these exact names.

{checks}

For each check write the note FIRST (quote or point to the exact part of the reply) and only then decide passed.
Before failing a check, re-read the reply: if what you would ask to change is already in the reply, the check passes.
If ANY check failed, write `feedback`: 1-3 sentences telling the assistant precisely how to rewrite the reply
(address every failed check at once). Describe WHAT must change, never HOW to word it: do not write the replacement
reply and do not quote example sentences, or the assistant will copy them verbatim. Otherwise leave feedback empty.
Be strict but fair: do not fail a check for things the context does not require."""

_ONE_METHOD = """\
You are a quality sentinel for an AI assistant's replies. Judge the REPLY on exactly ONE check, named at the end of the
message, using the context above it (including the conversation so far: what the user said in earlier turns is NOT
fabrication when the assistant recalls it).
Write the note FIRST (quote or point to the exact part of the reply) and only then decide the severity:
- "none": the reply meets the check.
- "minor": a small imperfection that would not mislead, harm or fail the user (style, tone, wording, a missed nicety).
- "major": a clear violation that matters: invented facts, ignoring or refusing what was asked, unsafe handling of
  secrets, contradicting an active mandate, or a broken format.
PLATFORM KNOWLEDGE is ground truth and outranks what the user wishes: a reply that honestly states a limitation listed
there never fails any check for it, and a reply that promises something listed there as impossible always fails.
Only "major" forces the assistant to rewrite, so do not escalate small things. Before choosing "major", re-read the reply:
if what you would ask to change is already in the reply, it is not a failure.
If severity is "major", write `feedback`: 1-2 sentences saying WHAT must change, never HOW to word it: do not write the
replacement reply and do not quote example sentences, or the assistant will copy them verbatim. Otherwise leave it empty."""


class _Check(BaseModel):
    # El orden importa: el modelo genera los campos en este orden, asi que primero cita la evidencia y despues decide.
    # (Con `passed` primero decidia antes de razonar y sus veredictos se contradecian entre intentos.)
    name: str
    note: str = Field(description="Evidence first: quote or point to the exact part of the reply, then say why it passes or fails (one short sentence)")
    passed: bool
    severity: str = ""  # solo en modo per_check: "none" | "minor" | "major" (una falla menor se registra pero no bloquea)


class _Eval(BaseModel):
    checks: list[_Check]
    feedback: str = Field(description="How to rewrite if any check failed; empty string if all passed")


class _One(BaseModel):
    note: str = Field(description="Evidence first: quote or point to the exact part of the reply, then say why it passes or fails (one short sentence)")
    severity: Literal["none", "minor", "major"]
    feedback: str = Field(description="What must change if severity is major (not how to word it); empty string otherwise")


_DEFAULT_EVAL_MODEL = os.getenv("V3_EVAL_MODEL", "gpt-4o-mini")
_llm = ChatOpenAI(model=_DEFAULT_EVAL_MODEL, temperature=0).with_structured_output(_Eval)
_one_cache: dict = {}


def _one_for(model: str):
    """Juez de un solo chequeo para ese modelo (se crea una vez)."""
    if model not in _one_cache:
        _one_cache[model] = ChatOpenAI(model=model, temperature=0).with_structured_output(_One)
    return _one_cache[model]


def _report(*, passed: bool, attempt: int, max_retries: int, action: str, checks=None, feedback: str = "",
            reason: Optional[str] = None, judge: Optional[str] = None, delivered_attempt: Optional[int] = None) -> dict:
    return {
        "delivered_attempt": delivered_attempt or attempt,  # el intento que recibe el usuario (distinto al ultimo si se agotaron)
        "passed": passed,
        "attempt": attempt,
        "max_attempts": max_retries + 1,
        "action": action,  # approved | retry | exhausted | skipped
        "checks": [c.model_dump() for c in (checks or [])],
        "feedback": feedback,
        "reason": reason,
        "judge": judge,
    }


_CLAIMS_METHOD = """\
You verify an AI assistant's REPLY claim by claim against the context above it (platform knowledge, mandates, rules,
conversation so far). Do NOT judge the reply as a whole.
1. List the reply's factual statements about: what the assistant or the platform can, cannot or will do; how an
   automation would work; the user's apps, accounts or connections; facts taken from the context. Copy each one word
   for word from the REPLY. Greetings, offers to talk and opinions are not claims. A question or option that takes a
   capability for granted IS a claim of that capability (e.g. asking how the user wants to be notified in an app claims
   that app can notify) — copy the question. Leaving out something already said earlier in the conversation is not a claim and never a problem.
   ONE claim = ONE app doing ONE thing. Split a sentence that chains several apps or steps ("it will save it in Sheets
   and notify you on Slack") into one claim per app, copying the exact words of each part ("se guardará en una hoja de
   Google Sheets" / "te enviaré una notificación a Slack"). A step described as part of how the automation will work
   is a "can" claim even if another sentence later says that app is not available. For every claim fill `app` and
   `actions` = EVERY action it mentions for that app, seen from the APP: "write" whenever something would be sent,
   delivered, posted or changed THROUGH that app — "you will receive notifications in Discord", "share it with your
   Instagram followers", "I'll delete the file in Drive", "post the photos" are all write; "read" = read/list/search;
   "connect" = linking the account. "Connect Discord so you receive notifications" → ["connect", "write"].
2. For each claim decide:
   - "supported": the context backs it, or it describes something the platform knowledge says is possible.
   - "contradicted": a specific line of the context says the opposite. Copy that line word for word into `evidence`.
   - "not_in_context": the context neither backs nor contradicts it.
For every claim that an app WILL or CAN do something (send, notify, read, create, trigger), find that app's line in
PLATFORM KNOWLEDGE first. If that line says the app is not available, coming soon, connection only or has no actions,
the claim is "contradicted" (copy that line), never "not_in_context". A claim that an app CANNOT do something agrees
with such a line and is "supported". PLATFORM KNOWLEDGE is ground truth."""


class _Claim(BaseModel):
    claim: str = Field(description="Exact words copied from the REPLY")
    app: str = Field(default="", description="The app this claim is about, as named in the reply (e.g. Slack); empty if none")
    # Lista, no una sola: "conecta Discord para que recibas avisos" es connect + write y el juez se quedaba con connect
    # (v0.3.2 en vivo). El codigo mira si ALGUNA es write.
    actions: list[Literal["read", "write", "connect", "other"]] = Field(
        default_factory=list, description="EVERY action the claim mentions for that app, seen from the app: write = something "
                                          "sent, delivered, posted, notified or changed through it (incl. 'so you receive "
                                          "notifications in X'); read = read/list/search; connect = linking the account; other")
    claim_says: Literal["can", "cannot", "other"] = Field(
        description="can = the claim says something will/can happen or be done; cannot = it says it can't/won't; other")
    verdict: Literal["supported", "contradicted", "not_in_context"]
    evidence: str = Field(description="For contradicted: exact words copied from the context that say the opposite; else empty")
    evidence_says: Literal["can", "cannot", "other"] = Field(
        description="Same scale for the evidence line: can / cannot / other; 'other' if there is no evidence")


class _Claims(BaseModel):
    claims: list[_Claim]


_claims_cache: dict = {}


def _in_context(quote: str, context: str) -> bool:
    """La evidencia tiene que existir de verdad en el contexto (espacios y mayusculas aparte)."""
    norm = lambda s: " ".join(s.lower().split())  # noqa: E731
    q = norm(quote).strip(" .\"'“”«»")
    return len(q) >= 12 and q in norm(context)


_WEB_INFO = ("INFORMATIONAL QUESTION answered from the web: facts ABOUT an app (its API, limits, prices, news) are not "
             "claims that the platform can act in that app.")


async def _judge_claims(model: str, check: dict, body: str) -> tuple[_Check, str]:
    """Verificacion afirmacion por afirmacion (receta de deteccion de alucinaciones: separar en afirmaciones atomicas y
    comparar cada una con la fuente). El juez solo clasifica; la severidad la decide el codigo: "major" solo si una
    afirmacion esta contradicha por una linea que EXISTE en el contexto. Juzgar la respuesta entera daba 65 % de falsos
    "major" (auditoria del 2026-10-10): exigia repetir lo ya dicho y veia contradicciones que no existen."""
    if model not in _claims_cache:
        _claims_cache[model] = ChatOpenAI(model=model, temperature=0).with_structured_output(_Claims)
    examples = "\n".join(f"- {e}" for e in (check.get("examples") or []))
    system = _CLAIMS_METHOD + (f"\n\nCalibration notes from real reviews:\n{examples}" if examples else "")
    result: _Claims = await _claims_cache[model].ainvoke([
        {"role": "system", "content": system},
        {"role": "user", "content": f"{body}\n\nCHECK TO RUN: {check['name']} — {check['criterion']}"},
    ], config={"tags": [f"judge:{check['name']}"]})
    context = body.split("REPLY TO EVALUATE:")[0]  # citar la propia respuesta no prueba nada
    # El mini confunde la negacion ("no puedo enviar a Slack" contra "Slack no tiene acciones" lo daba por contradicho):
    # si afirmacion y evidencia dicen lo mismo (las dos "cannot" o las dos "can") no es una contradiccion.
    bad = [c for c in result.claims if c.verdict == "contradicted" and _in_context(c.evidence, context)
           and not (c.claim_says != "other" and c.claim_says == c.evidence_says)]
    # Que una app no esta disponible ya lo sabe la plataforma (es la linea que se le dio al responder): el juez solo dice de
    # que app habla cada afirmacion y el codigo decide. Antes dependia de que el mini encontrara la linea y la citara, y
    # "guarda en Sheets y te avisa en Slack" se le escapaba 2 de cada 5 veces (v0.3.0, escenario varias_apps_slack).
    # v0.3.2: y tambien si una app que SOLO LEE "va a" enviar/publicar/avisar (Discord, Instagram). La capacidad sale del
    # registro (app_capability), no del modelo: revisar contra el registro real es lo que en la literatura atrapo el 100 %
    # de las herramientas inventadas (Closed-World Resolution, arXiv 2609.19425); los jueces LLM solos rondan AUROC 0.65.
    unavailable = unavailable_apps(context)
    # Pregunta informativa respondida con busqueda web: un dato SOBRE una app ("la API de Slack permite 1 solicitud por
    # minuto") no es prometer que la plataforma actua en ella. Sin esto se rechazo 5 veces la respuesta correcta (v094_web,
    # web_estable); el juez etiquetaba "read" a "metodos que leen el historial", asi que no basta mirar `actions`.
    for c in result.claims if _WEB_INFO not in context else []:
        app = c.app.strip().lower()
        if not app or c.claim_says != "can" or c in bad:
            continue
        # "Nada disponible" exige la linea de esa app en el contexto: un nombre generico ("Google", "correo") da "none" en el
        # registro sin ser una app no disponible. "Solo lee" si sale del registro: ahi el nombre ya resolvio a una app real.
        line = next((ln for name, ln in unavailable.items() if app == name or name in app or app in name), None)
        if line:
            fact = line
        elif "write" in c.actions and app_capability(app) == "read":
            fact = f"{c.app}: read-only on the platform — it cannot send, post, notify, create or modify anything"
        else:
            continue
        c.evidence = fact
        bad.append(c)
    loose = [c for c in result.claims if c.verdict == "not_in_context" and c not in bad]
    if bad:
        note = "; ".join(f"«{c.claim}» contradice «{c.evidence}»" for c in bad)
        feedback = "These statements contradict the platform facts and must be corrected: " + "; ".join(
            f"'{c.claim}' (context says: '{c.evidence}')" for c in bad)
        return _Check(name=check["name"], note=note, passed=False, severity="major"), feedback
    if loose:
        note = "sin respaldo en el contexto (no bloquea): " + "; ".join(f"«{c.claim}»" for c in loose)
        return _Check(name=check["name"], note=note, passed=True, severity="minor"), ""
    return _Check(name=check["name"], note=f"{len(result.claims)} afirmacion(es) verificadas", passed=True, severity="none"), ""


def _format_check(check: dict, reply: str) -> tuple[_Check, str]:
    """Formato es mecanico: lo decide el codigo. El juez LLM de formato juzgaba contenido ("no ayuda con el inventario")
    y agoto 5 intentos con respuestas correctas (eval_memory base_v032)."""
    problems = []
    if reply.count("```") % 2:
        problems.append("unclosed code block")
    s = reply.strip()
    if s[:1] in "{[":
        try:
            json.loads(s)
            problems.append("the reply is raw JSON")
        except ValueError:
            pass
    paras = [p.strip() for p in re.split(r"\n\s*\n", reply) if len(p.strip()) > 40]
    if len(paras) != len(set(paras)):
        problems.append("a paragraph is repeated")
    if problems:
        return _Check(name=check["name"], note="; ".join(problems), passed=False, severity="major"), \
            "Fix the formatting: " + "; ".join(problems) + "."
    return _Check(name=check["name"], note="formato revisado por codigo: sin problemas", passed=True, severity="none"), ""


# ponytail: palabras de "aun no" en es/en; si da falsos positivos, pasarlas a platform_knowledge como dato
_NOT_YET_CUE = re.compile(r"\b(no|not|a[uú]n|todav[ií]a|yet|pr[oó]ximamente|soon|desarrollo|development|cannot|can't)\b")


_FAILED_CUE = re.compile(r"\b(no|not|error|fall[oóa]|fail|could|pude|problema|issue|unable)", re.IGNORECASE)


# "Ya lo hice" en es/en. Las palabras flojas (listo, hecho, done) solo cuentan si no se ejecuto nada: "listo, aqui tus tareas"
# tras una lectura es correcto.
_DONE_STRONG = r"\b(?:cre[eé]|creada?|creado|created|enviad[oa]|sent|actualic[eé]|actualizad[oa]|updated|asign[eé]|assigned)\b"
_DONE_WEAK = r"\b(?:listo|hecho|done)\b"
# La oracion que pide el si o dice lo que se hara no afirma que ya paso.
_NOT_DONE_CUE = re.compile(r"\?|confirm|quieres|want me|shall i|should i|antes de|before|voy a|i will|i'll|crear[eé]|enviar[eé]|puedo|can i")


def _actions_check(results: list, reply: str) -> tuple[_Check, str]:
    """Modo act: si TODAS las llamadas a una app fallaron, cada oracion que nombra esa app debe decir que fallo.
    Lo decide el codigo: "listo, aqui tus tareas de Asana" con la llamada en ok:false es el error mas dañino.
    Tambien: una escritura pendiente (espera el si) no se puede contar como hecha."""
    pending = [r for r in results if r.get("pending")]
    results = [r for r in results if not r.get("pending")]  # pendiente no es falla: no se ejecuto
    failed = {r["app"] for r in results} - {r["app"] for r in results if r.get("ok")}
    sentences = re.split(r"(?<=[.!?\n])\s+", reply.lower())
    bad = [app for app in sorted(failed)
           if any(app.replace("_", " ").split()[-1] in s and not _FAILED_CUE.search(s) for s in sentences)]
    if bad:
        return _Check(name="actions_backed", note=f"presenta datos de {', '.join(bad)} pero sus llamadas fallaron",
                      passed=False, severity="major"), \
            f"The calls to {', '.join(bad)} FAILED this turn: say so and do not present data from it."
    if pending:
        cue = re.compile(_DONE_STRONG if any(r.get("ok") for r in results) else f"{_DONE_STRONG}|{_DONE_WEAK}")
        if any(cue.search(s) and not _NOT_DONE_CUE.search(s) for s in sentences):
            return _Check(name="actions_backed", note="dice que algo quedo hecho pero solo esta pendiente de confirmacion",
                          passed=False, severity="major"), \
                "Nothing was executed: the action is only PROPOSED and waits for the user's yes. Say what you will do and " \
                "ask for confirmation; do not say it was created, sent or updated."
    return _Check(name="actions_backed", note="acciones revisadas por codigo", passed=True, severity="none"), ""


def _limits_check(check: dict, body: str, reply: str, offered_off: set[str] = frozenset()) -> tuple[_Check, str]:
    """Si el usuario nombro una app que hoy no se puede usar y la respuesta ni la menciona, el usuario cree que si se hara.
    Lo decide el codigo: la app sale de las lineas "no disponible" del bloque de plataforma (unavailable_apps) y basta con
    buscar su nombre. Caso real: "guardalo en Sheets y avisame por Slack" -> la respuesta hablaba de Sheets y callaba Slack."""
    if _WEB_INFO in body:  # preguntar por la API o las novedades de una app no es pedir usarla
        return _Check(name=check["name"], note="pregunta informativa con busqueda web", passed=True, severity="none"), ""
    before, _, rest = body.partition("USER MESSAGE:\n")
    user_text = rest.split("\n\nUSER INTENT", 1)[0].lower()
    # Si la app ya salio antes en la conversacion, la limitacion ya se dijo ("si no se puede por Telegram..."): exigir
    # repetirla es el falso positivo que la auditoria del 2026-10-10 encontro en no_fabrication.
    sentences = re.split(r"(?<=[.!?\n])\s+", reply.lower())
    missing = [name for name in unavailable_apps(body) if name in user_text and (
        # nombrada como si funcionara ("te aviso por Slack"): cada oracion que la nombra debe decir que aun no
        any(name in s and not _NOT_YET_CUE.search(s) for s in sentences)
        or (name not in reply.lower() and name not in before.lower()))]
    # Ofrecida sin que el usuario la pidiera ("podriamos avisarte por Slack"): la oracion debe decir que aun no esta.
    # Caso real: act_sin_funcion (v0.5.0) ofrecio Slack como canal de aviso y Slack no esta disponible.
    # Con las mayusculas del catalogo: "our teams" no es la app "Teams" (falsa alarma con nombres que son palabras comunes).
    cased = re.split(r"(?<=[.!?\n])\s+", reply)
    offered = [name for name in sorted(offered_off) if name.lower() not in missing and any(
        re.search(r"\b" + re.escape(name) + r"\b", s) and not _NOT_YET_CUE.search(s.lower()) for s in cased)]
    if offered:
        apps = ", ".join(offered)
        return _Check(name=check["name"], note=f"ofrece {apps} como si funcionara y no esta disponible",
                      passed=False, severity="major"),             f"{apps} is not available on the platform yet: do not offer it as an option; offer only apps that work."
    if missing:
        apps = ", ".join(missing)
        return _Check(name=check["name"], note=f"el usuario pidio {apps} y la respuesta no dice que aun no esta disponible",
                      passed=False, severity="major"), \
            f"The user asked for {apps}, which is not available yet: say so in one sentence (the team keeps adding " \
            f"integrations), then continue with what works."
    return _Check(name=check["name"], note="limites revisados por codigo: sin omisiones", passed=True, severity="none"), ""


# Credenciales por codigo: el juez LLM de `credentials` rechazaba por cualquier otra cosa ("no debe decir que no sabe tu
# banco", "no aviso que conecte Drive"): 67 rechazos guardados, casi ninguno sobre credenciales (auditoria 2026-10-10).
_SECRET_VALUE = re.compile(
    r"\b(?:contrase(?:ñ|n)a|password|passwd|clave|token|api[\s_-]?key|pin)\b(?:\s+(?!es\b|is\b)[\w@.]+\b){0,3}?"
    r"(?:\s+(?:es|is)\b|\s*[:=])\s*[\"'«]?([^\s\"'»,;]{4,})", re.I)
# "mi contraseña de gmail es X": hasta 3 palabras entre la palabra y el valor; "es"/"is" como palabra completa
# ("palabras clave listas" cortaba "l-is-tas" y tomaba "tas." como secreto).
_LONG_TOKEN = re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{24,}\b")
_ASKS_SECRET = re.compile(
    r"\b(?:dame|d[ée]jame|p[áa]same|comp[áa]rte(?:me)?|env[íi]a(?:me)?|escribe|ingresa|introduce|proporciona(?:me)?|"
    r"necesito|send|share|give me|enter|type|provide)\b[^.?!\n]{0,40}"
    r"\b(?:tu |la |el |your )?(?:contrase(?:ñ|n)a|password|token|api[\s_-]?key|clave de acceso)", re.I)


def _user_text(body: str) -> str:
    """Solo lo que escribio el usuario (mensaje actual, turnos previos y lo dicho antes), no las reglas ni la plataforma."""
    before, _, rest = body.partition("USER MESSAGE:\n")
    current = rest.split("\n\nUSER INTENT", 1)[0]
    earlier = [ln[6:] for ln in before.splitlines() if ln.startswith("USER: ")]
    older = before.split("WHAT THE USER SAID EARLIER IN THIS CONVERSATION", 1)[1].split("\n\n", 1)[0] \
        if "WHAT THE USER SAID EARLIER IN THIS CONVERSATION" in before else ""
    return "\n".join([current, *earlier, older])


def _credentials_check(check: dict, body: str, reply: str) -> tuple[_Check, str]:
    """Falla solo si la respuesta REPITE un secreto que el usuario escribio o PIDE una contrasena/token/API key.
    Recomendar cambiarla o usar el boton Conectar pasa (eso es lo correcto)."""
    said = _user_text(body)
    secrets = {m for m in _SECRET_VALUE.findall(said)} | set(_LONG_TOKEN.findall(said))
    leaked = [s for s in secrets if s in reply]
    if leaked:
        return _Check(name=check["name"], note="la respuesta repite un secreto que el usuario escribio", passed=False,
                      severity="major"), "Never repeat the password, token or key the user wrote; tell them to change it and use the Connect button."
    asked = _ASKS_SECRET.search(reply)
    if asked:
        return _Check(name=check["name"], note=f"pide una credencial: \"{asked.group(0)[:80]}\"", passed=False,
                      severity="major"), "Never ask for passwords, tokens or API keys in the chat: the user connects the app with the Connect button."
    return _Check(name=check["name"], note="credenciales revisadas por codigo: sin fugas ni pedidos", passed=True,
                  severity="none"), ""


async def _judge_one(model: str, check: dict, body: str, reply: str = "") -> tuple[_Check, str]:
    if check.get("method") == "code_format":  # dato: formato se revisa con codigo, no con un juez
        return _format_check(check, reply)
    if check.get("method") == "code_credentials":  # dato: credenciales con codigo (el juez LLM se salia del tema)
        return _credentials_check(check, body, reply)
    if check.get("method") == "code_unavailable_mentioned":  # dato: avisar las apps no disponibles que pidio el usuario
        return _limits_check(check, body, reply, await unavailable_catalog_names())
    if check.get("method") == "claims":  # dato: el chequeo pide verificacion afirmacion por afirmacion
        return await _judge_claims(model, check, body)
    result: _One = await _one_for(model).ainvoke([
        {"role": "system", "content": _ONE_METHOD},
        {"role": "user", "content": f"{body}\n\nCHECK TO RUN: {check['name']} — {check['criterion']}"},
    ], config={"tags": [f"judge:{check['name']}"]})  # la etiqueta identifica a este mini agente en el registro del turno
    return _Check(name=check["name"], note=result.note, passed=result.severity != "major", severity=result.severity), result.feedback


def _intent_block(state) -> str:
    """Lo que el juez ve como intencion. Si el flujo de crear workflows escribio el mensaje del turno, ese mensaje es
    EVIDENCIA (sus hechos vienen del plan guardado y de la simulacion, no los inventa el asistente) y la respuesta debe
    entregarlo fielmente: sin ello el juez daba por inventado el horario o los pasos que el flujo ya habia calculado.
    Debe empezar con "USER INTENT": otras funciones de este archivo cortan el cuerpo por ese marcador."""
    return _intent_core(state) + _shown_buttons(state)


def _shown_buttons(state) -> str:
    """Sin este hecho los jueces daban por inventado el boton que la interfaz si muestra ("abreme mis workflows" gasto 5
    intentos)."""
    shown = state.get("requested_ui_actions") or []
    return ("\nINTERFACE FACT (verified): under this reply the interface shows the button(s) "
            + "; ".join(f"«{a.get('label')}»" for a in shown)
            + ", which open the screen the user asked for. Pointing the user to them is correct and complete: it is not an "
              "invention and the reply does not need to list the screen's contents.") if shown else ""


def _intent_core(state) -> str:
    structured = state.get("structured_prompt") or ""
    if state.get("req_relay") and structured:
        return ("USER INTENT (the automation-setup flow wrote this message for the turn; it is verified by the system, so "
                "its facts are NOT inventions. The reply must deliver it faithfully: same facts, values and question. "
                "Adding facts, claims about platform capabilities, or questions that are not in it IS a failure):\n"
                + structured)
    if state.get("req_compose") and structured:
        return ("USER INTENT (the user is setting up an automation; the system checked the facts below for this turn, so "
                "they are NOT inventions. The reply must state them, must not contradict them, and should also answer "
                "what the user asked in their last message):\n" + structured)
    return f"USER INTENT (normalized): {structured}"


async def response_evaluator_node(state, config: RunnableConfig = None) -> dict:
    cfg = (config or {}).get("configurable", {})
    personality = await get_agent_personality()
    qc = personality.get("quality_control") or {}
    judge_cfg = qc.get("judge") or {}
    model = cfg.get("eval_model") or judge_cfg.get("model") or _DEFAULT_EVAL_MODEL
    mode = judge_cfg.get("mode") or "single"
    max_retries = int(qc.get("max_retries", _DEFAULT_MAX_RETRIES))
    checks_cfg = [c for c in (qc.get("checks") or _DEFAULT_CHECKS) if c.get("name") and c.get("criterion")]
    retry_count: int = state.get("eval_retry_count", 0)
    attempt = retry_count + 1
    judge_label = f"{model}/{mode}"

    def report(**kw):
        return _report(attempt=attempt, max_retries=max_retries, judge=judge_label, **kw)

    if qc.get("enabled") is False:
        return {"eval_feedback": None, "eval_report": report(passed=True, action="skipped", reason="control de calidad desactivado en la personalidad")}

    messages = state.get("messages", [])
    last_ai: Optional[AIMessage] = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if not last_ai:
        return {"eval_report": report(passed=True, action="skipped", reason="no hay respuesta que evaluar")}
    if state.get("req_relay") and state.get("req_flow_action") != "digress" and not state.get("is_closing"):
        # El mensaje lo escribio el flujo de workflows con hechos verificados y el responder lo entrega tal cual: pedir
        # una reescritura devolveria el mismo texto y gastaria los intentos.
        return {"eval_feedback": None,
                "eval_report": report(passed=True, action="skipped", reason="mensaje del flujo de workflows (se entrega tal cual)")}
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)

    identity = await get_agent_identity()
    rules = "\n".join(f"- {r}" for r in (identity.get("principles") or []) + (identity.get("restrictions") or [])) or "(none)"
    platform = await build_platform_context(state)
    mandates = "\n".join(f"- {m}" for m in (state.get("active_mandates") or [])) or "(none)"
    context_header = ""
    if state.get("current_time_utc"):
        context_header = (
            f"Factual context: current UTC time {state['current_time_utc']}, "
            f"user timezone {state.get('user_timezone') or 'UTC'}.\n\n"
        )
    # Historial reciente: sin el, el juez marcaba como invencion que el agente recordara algo que el usuario dijo antes.
    earlier = [m for m in messages if isinstance(m, (HumanMessage, AIMessage)) and m is not last_ai and m is not last_human]
    history = "\n".join(
        f"{'USER' if isinstance(m, HumanMessage) else 'ASSISTANT'}: {str(m.content)[:600]}" for m in earlier[-_HISTORY_MESSAGES:]
    ) or "(first turn)"
    # Lo que dijo el usuario ANTES de esa ventana: con 6 mensajes, recordar "cambie a Excel" del turno 10 en el turno 18
    # se rechazaba 5 veces por "inventado" (eval_memory base_v032). Solo lo del usuario: es la fuente de sus datos.
    older_user = [m for m in earlier[:-_HISTORY_MESSAGES] if isinstance(m, HumanMessage)][-_OLDER_USER_MESSAGES:]
    older = ("WHAT THE USER SAID EARLIER IN THIS CONVERSATION (oldest first):\n"
             + "\n".join(f"- {str(m.content)[:200]}" for m in older_user) + "\n\n") if older_user else ""
    # Modo act: lo que devolvieron las apps es evidencia; sin esto el juez daba por inventados los datos reales.
    actions = (format_action_results(state["action_results"], state.get("action_stop")) + "\n\n") \
        if state.get("action_results") is not None else ""
    # Resumen rodante (compactacion): recordar un dato viejo plegado ahi no es inventar.
    summary = f"EARLIER IN THIS CONVERSATION (summary):\n{state['conversation_summary']}\n\n" if state.get("conversation_summary") else ""
    # Busqueda web: sin esto los jueces daban por inventado un dato actual (el tipo de cambio de hoy) y rechazaban 5
    # veces la respuesta correcta; uno llego a decir que la fecha de hoy era "futura" (v092_web_real).
    web = state.get("curated_research") or state.get("retrieved_research")
    if web:
        research = ("WEB SEARCH RESULTS RETRIEVED THIS TURN (real and current: the assistant searched the internet; facts, "
                    "prices, news and dates stated here are EVIDENCE, and dates close to the current time above are not "
                    f"future). {state.get('research_freshness') or ''}\n")
        if (state.get("semantic_intake_debug") or {}).get("detected_intent") in ("question", "exploring", "chat"):
            research += _WEB_INFO + "\n"
        research += f"{str(web)[:6000]}\n\n"
    elif state.get("needs_external_info"):
        research = ("WEB SEARCH: it was needed and returned nothing this turn. Saying that it could not search right now "
                    "is correct; stating current facts as if searched is not.\n\n")
    else:
        research = ""
    # Archivos adjuntos: sin esto los jueces daban por inventado lo que el agente leia del documento ("385 quetzales
    # desde el 3 de noviembre") y la reescritura contestaba otra cosa sacada de la web.
    docs = state.get("turn_document_context") or ""
    chunks = "\n\n".join(str(c.get("text", "")) for c in state.get("retrieved_document_chunks") or [])
    files = (f"FILES THE USER ATTACHED (the assistant CAN read attached files; this is their real content, so what the "
             f"reply states from it is EVIDENCE, not invented, whatever its dates):\n{(docs + chr(10) + chunks)[:8000]}\n\n"
             ) if docs or chunks else ""
    body = (
        f"{context_header}"
        f"{files}"
        f"{research}"
        f"{older}"
        f"{summary}"
        f"CONVERSATION SO FAR (earlier turns):\n{history}\n\n"
        f"USER MESSAGE:\n{getattr(last_human, 'content', '')}\n\n"
        f"{_intent_block(state)}\n\n"
        f"ACTIVE MANDATES (instructions the assistant was required to follow this turn):\n{mandates}\n\n"
        f"{actions}"
        f"{platform or 'PLATFORM KNOWLEDGE: (unavailable)'}\n\n"
        f"PRINCIPLES & RESTRICTIONS:\n{rules}\n\n"
        f"PERSONA RULES:\n{render_voice(personality) or '(none defined)'}\n\n"
        # Sin esto el juez daba por inventado que el agente recordara el nombre o en que iba el usuario.
        f"WHAT THE ASSISTANT KNOWS ABOUT THE USER:\nname: {state.get('user_name') or '(unknown)'}\n"
        f"{state.get('user_memory_context') or '(nothing remembered)'}\n\n"
        f"REPLY TO EVALUATE:\n{last_ai.content}"
    )

    try:
        if mode == "per_check":
            # Un juez barato por chequeo, en paralelo. Si uno falla (red, limite) ese chequeo se omite; si fallan todos, se entrega.
            # Un chequeo con only_with_mandates (dato) no corre si el turno no trae instrucciones obligatorias: sin ellas el
            # juez las inventaba ("debe avisar que conecte Sheets") y rechazaba respuestas correctas (eval_memory base_v032).
            run_checks = [c for c in checks_cfg if not (c.get("only_with_mandates") and not state.get("active_mandates"))]
            results = await asyncio.gather(*[_judge_one(model, c, body, str(last_ai.content)) for c in run_checks],
                                           return_exceptions=True)
            ok = [r for r in results if not isinstance(r, BaseException)]
            for r in results:
                if isinstance(r, BaseException):
                    logger.warning("[response_evaluator] un juez fallo: %s", r)
            if not ok:
                raise RuntimeError(f"fallaron los {len(results)} jueces")
            by_name = {c["name"]: c for c in checks_cfg}
            for chk, _ in ok:
                # blocking: false (dato) = el chequeo informa pero no fuerza reescritura. En la auditoria del 2026-10-10
                # answers_request y persona no acertaron ni uno de sus 25 "major": reescribir por ellos solo empeoraba.
                if not chk.passed and by_name.get(chk.name, {}).get("blocking") is False:
                    chk.passed, chk.severity, chk.note = True, "minor", f"[informativo, no bloquea] {chk.note}"
            ok = [(chk, fb if not chk.passed else "") for chk, fb in ok]
            checks = [chk for chk, _ in ok]
            feedback = " | ".join(f"{chk.name}: {fb}" for chk, fb in ok if not chk.passed and fb)
        else:
            llm = _llm if model == _DEFAULT_EVAL_MODEL else \
                  ChatOpenAI(model=model, temperature=0).with_structured_output(_Eval)
            result: _Eval = await llm.ainvoke([
                {"role": "system", "content": _METHOD.format(checks="\n".join(f"{i}. {c['name']} — {c['criterion']}" for i, c in enumerate(checks_cfg, 1)))},
                {"role": "user", "content": body},
            ])
            configured = {c["name"] for c in checks_cfg}
            checks = [c for c in result.checks if c.name in configured]  # el modelo no puede inventar chequeos
            feedback = result.feedback
    except Exception as exc:
        logger.exception("[response_evaluator] evaluation call failed — passing through")
        return {"eval_feedback": None, "eval_report": report(passed=True, action="skipped", reason=f"el evaluador falló: {exc}")}

    if state.get("action_results"):
        chk, fb = _actions_check(state["action_results"], str(last_ai.content))
        checks = [*checks, chk]
        if fb:
            feedback = f"{feedback} | actions_backed: {fb}" if feedback else f"actions_backed: {fb}"

    if all(c.passed for c in checks):
        # None sobrescribe el campo: el router manda el turno a memory_updater
        return {"eval_feedback": None, "eval_report": report(passed=True, action="approved", checks=checks)}

    feedback = feedback or "; ".join(c.note for c in checks if not c.passed)
    logger.info("[response_evaluator] rejected (attempt %d/%d) | %s", attempt, max_retries + 1, feedback)
    drafts = [*(state.get("eval_drafts") or []),
              {"attempt": attempt, "content": last_ai.content, "majors": sum(1 for c in checks if not c.passed)}]

    if retry_count >= max_retries:
        # Se entrega el borrador con menos fallas graves (empate: el mas reciente, que ya incorporo mas correcciones).
        # Antes se entregaba el ultimo: una vez el agente escribio la version honesta, el juez la rechazo y salio la falsa.
        best = min(reversed(drafts), key=lambda d: d["majors"])
        out = {"eval_feedback": None, "eval_drafts": drafts,
               "eval_report": report(passed=False, action="exhausted", checks=checks, feedback=feedback,
                                     delivered_attempt=best["attempt"])}
        if best["attempt"] != attempt:  # mismo id: add_messages reemplaza el ultimo borrador por el mejor
            out["messages"] = [AIMessage(id=last_ai.id, content=best["content"])]
            logger.warning("[response_evaluator] max retries reached — delivering attempt %d (%d majors) instead of %d",
                           best["attempt"], best["majors"], attempt)
        return out
    return {
        "eval_retry_count": retry_count + 1,
        "eval_feedback": feedback,
        "eval_drafts": drafts,
        "eval_report": report(passed=False, action="retry", checks=checks, feedback=feedback),
    }
