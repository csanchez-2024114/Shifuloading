"""research_analyst: piensa sobre lo que trajo la busqueda antes de que el responder conteste.

Sin este paso el agente repetia lo primero que encontraba: un pronostico como si fuera el precio de hoy, un blog por encima
de la pagina oficial, o un solo valor cuando dos fuentes daban distinto. Aqui un modelo lee las fuentes CON su dominio y
su fecha y decide: cuales sirven y cuales no (y por que), en que coinciden, por que difieren, cual es la respuesta y que
tan segura es. Si lo encontrado no alcanza puede pedir UNA busqueda mas, mejor dirigida.

El criterio es dato: `agent_personality.research_policy` {enabled, model, max_followups, criteria}. El resultado va al
inicio de `curated_research`, asi lo leen el responder y los jueces.
"""
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Literal, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agent.shared.helpers.identity_loader import get_agent_personality
from app.agent.shared.nodes.tavily_searcher import tavily_searcher_node
from app.agent.shifu_base_v1.graph.state import ShifuState

logger = logging.getLogger(__name__)

_DEFAULT_POLICY = {
    "enabled": True,
    "model": "gpt-4o-mini",
    "max_followups": 1,
    "criteria": (
        "- Read each source as a skeptical analyst, not as a copyist. First check it is about what was asked: the same "
        "thing, place, unit, product version and time. A page about another country, another product or a forecast for "
        "the future does not answer a question about now.\n"
        "- Weigh who says it: the official or primary source (the company's own docs, changelog or pricing page, a "
        "government or central bank, the exchange itself) beats news media, which beats blogs, aggregators and SEO pages, "
        "which beat social media, forums and videos. Discard promos and pages that only mention the topic in passing.\n"
        "- Weigh when: for anything that changes, the most recent dated fact wins. A fact without a date, or older than "
        "the question needs, is weaker: say so.\n"
        "- When sources give different values, work out why before choosing (different moment, buy vs sell rate, "
        "different market, plan or region, rounded figure). If the reason is clear, answer with the best one and explain "
        "the gap in a few words; if not, give the range and who says each.\n"
        "- Do the date arithmetic against TODAY, explicitly. If a source calls something 'upcoming', 'expected' or "
        "'rumored' for a date that TODAY has already passed, that source is OUTDATED: the thing has probably happened, so "
        "what it calls 'the latest' is no longer the latest. Do not conclude from it; lower the confidence and ask for a "
        "search of what actually happened.\n"
        "- Every value, name and date in the conclusion must be copied from a source. If a source gives a day without "
        "the year, do not add a year yourself. Do not stamp TODAY's date on a fact "
        "the source does not date, and do not list 'no publication date' as a caveat for a fact that does not change.\n"
        "- Check the result makes sense: orders of magnitude, units, dates that are not in the future, a claim only one "
        "weak source makes. Something surprising needs two independent sources.\n"
        "- Say what the search did NOT establish. Never fill a gap with what you remember.\n"
        "- Ask for one more search only when it would change the answer: the sources miss the point, contradict each "
        "other with no way to settle it, or only weak sources were found. Write the query for the primary source."
    ),
}

_SYSTEM = """\
You are the research analyst of an assistant. The assistant searched the web and you must THINK about what came back
before anyone answers the user. You do not write the reply: you write the judgment the reply will be built on.

How to judge:
{criteria}

Dates in SEARCH RESULTS carry a tag computed by code against TODAY: [PAST: N days before TODAY], [FUTURE: in N days],
[PAST month], [FUTURE month]. The tag is a fact; trust it over the wording of the source. Something a source says "will
be available on", "is set for" or "launches on" a [PAST] date has ALREADY happened: write it in the past tense and count
it as released. Never copy the tags into your answer.

Refer to sources by their number in SOURCES, like [2]. Use only what is in the search results. Write in English, short
and concrete: values, dates and names verbatim."""


class _Announced(BaseModel):
    what: str = Field(description="What the source says is coming (a release, an event, a change).")
    date: str = Field(description="When, as YYYY-MM-DD or YYYY-MM, exactly as the source dates it.")
    check_query: str = Field(description="English web search query to find out whether it already happened and what the outcome was.")


class _Judgment(BaseModel):
    # Va primero a proposito: listar lo anunciado ANTES de concluir; al final el modelo ya habia concluido sin mirarlo.
    announced: list[_Announced] = Field(default_factory=list, description="Everything the sources call upcoming, expected, planned, rumored or scheduled that matters for the question. List it even if you think it has not happened.")
    reasoning: str = Field(description="Your thinking, step by step and brief: what each useful source says, how much to trust it and why, where they agree or differ.")
    conclusion: str = Field(description="The best answer to the user's question that the sources support, with values, the date they refer to and source numbers like [1].")
    confidence: Literal["high", "medium", "low"] = Field(description="high: primary or several independent recent sources agree. medium: one decent source, or small differences. low: weak, old or conflicting sources.")
    caveats: list[str] = Field(default_factory=list, description="What the user should know: date of the data, why sources differ, what could not be established.")
    discarded: list[str] = Field(default_factory=list, description="Sources not to use, as '[N] reason'.")
    follow_up_query: Optional[str] = Field(default=None, description="ONE better web search query (English) if it would change the answer; otherwise null.")


def _already_past(announced: list[_Announced], today: str) -> list[_Announced]:
    """Lo que las fuentes llaman 'proximo' y ya paso. La resta de fechas la hace el codigo: 4o-mini escribio
    "septiembre de 2026, que aun no ocurre al 11 de octubre de 2026" y dio por ultimo el iPhone de 2025."""
    return [a for a in announced if len(a.date) >= 7 and a.date[:4].isdigit() and a.date[:len(today[:10])] < today[:len(a.date[:10])]]


_cache: dict[str, object] = {}


def _question(state: ShifuState) -> str:
    last = next((m for m in reversed(state.get("messages") or []) if getattr(m, "type", "") == "human"), None)
    return str(getattr(last, "content", "") or state.get("structured_prompt") or state.get("optimized_search_query") or "")


def _age(published: str, today: str) -> str:
    """La fecha de la fuente contra la del sistema, ya restada ("412 days before TODAY"): el modelo chico no resta fechas.
    Tavily manda RFC 2822 ("Fri, 10 Oct 2026 12:00:00 GMT") o ISO; si no se entiende, no se dice nada."""
    try:
        now = datetime.fromisoformat(today[:10])
        try:
            then = parsedate_to_datetime(published).replace(tzinfo=None)
        except (TypeError, ValueError):
            then = datetime.fromisoformat(published[:10])
    except ValueError:
        return ""
    days = (now.date() - then.date()).days
    return " (TODAY)" if days == 0 else f" ({days} days before TODAY)" if days > 0 else f" ({-days} days AFTER TODAY)"


_MONTHS = {m: i for i, names in enumerate((
    "january jan enero", "february feb febrero", "march mar marzo", "april apr abril", "may mayo", "june jun junio",
    "july jul julio", "august aug agosto", "september sep sept septiembre setiembre", "october oct octubre",
    "november nov noviembre", "december dec diciembre"), 1) for m in names.split()}
_M = "|".join(sorted(_MONTHS, key=len, reverse=True))
# Fechas escritas en el texto, en ingles y espanol. Primero las completas; la de solo mes y año va al final.
_DATE = re.compile(
    rf"\b(?P<y1>20\d\d)-(?P<m1>\d\d)-(?P<d1>\d\d)\b"
    rf"|\b(?P<m2>{_M})\.? (?P<d2>\d{{1,2}})(?:st|nd|rd|th)?,? (?P<y2>20\d\d)\b"
    rf"|\b(?P<d3>\d{{1,2}}) (?:de )?(?P<m3>{_M})\.?(?: de|,)? (?P<y3>20\d\d)\b"
    rf"|\b(?P<m4>{_M})\.? (?:de |of )?(?P<y4>20\d\d)\b", re.IGNORECASE)
_NEAR_DAYS = 400  # solo fechas cercanas a hoy: ahi se confunde el modelo; marcar un historial de 20 años solo agrega ruido


def _stamp_dates(text: str, today: str) -> str:
    """Cada fecha cercana del texto, marcada contra la del sistema: "September 18, 2026 [PAST: 23 days before TODAY]".

    El modelo chico no resta fechas, y la comprobacion de `announced` solo cubre lo que el decide listar: una nota que
    decia "estara disponible el 18 de septiembre de 2026" (sin llamarlo "proximo") no se listaba y el analista concluia en
    futuro algo que ya habia pasado (2 de 11 turnos del iPhone, 2026-10-11). Aqui la resta la hace el codigo para TODAS."""
    try:
        now = datetime.fromisoformat(today[:10]).date()
    except ValueError:
        return text

    def tag(m: re.Match) -> str:
        g = m.groupdict()
        try:
            if g["y1"]:
                then = datetime(int(g["y1"]), int(g["m1"]), int(g["d1"])).date()
            elif g["y2"]:
                then = datetime(int(g["y2"]), _MONTHS[g["m2"].lower()], int(g["d2"])).date()
            elif g["y3"]:
                then = datetime(int(g["y3"]), _MONTHS[g["m3"].lower()], int(g["d3"])).date()
            else:  # solo mes y año: se compara por mes
                if g["m4"] in ("may", "mar"):  # en minuscula son palabras comunes ("it may 2026 times", "el mar 2026")
                    return m.group(0)
                y, mo = int(g["y4"]), _MONTHS[g["m4"].lower()]
                if abs((y - now.year) * 12 + mo - now.month) > _NEAR_DAYS // 30:
                    return m.group(0)
                rel = "THIS MONTH" if (y, mo) == (now.year, now.month) else "PAST month" if (y, mo) < (now.year, now.month) else "FUTURE month"
                return f"{m.group(0)} [{rel}]"
        except (ValueError, KeyError):
            return m.group(0)
        days = (now - then).days
        if abs(days) > _NEAR_DAYS:
            return m.group(0)
        return f"{m.group(0)} [{'TODAY' if days == 0 else f'PAST: {days} days before TODAY' if days > 0 else f'FUTURE: in {-days} days'}]"

    return _DATE.sub(tag, text)


_FUTURE = re.compile(r"\b(will|set to|expected|upcoming|scheduled|slated|planned|to be released|pre-?orders?|not yet)\b", re.IGNORECASE)


def _future_about_past(conclusion: str, today: str) -> list[str]:
    """Fechas ya pasadas de las que la conclusion habla en futuro ("will be available on September 18, 2026" un 11 de
    octubre). La conclusion la escribe nuestro modelo en ingles, asi que basta buscar el futuro en ingles. Marcar las
    fechas en el texto de las fuentes no alcanzo (0 de 8 en el replay): el modelo copiaba el tiempo verbal de la fuente."""
    stale = []
    for sentence in re.split(r"(?<=[.;])\s+", conclusion or ""):
        if _FUTURE.search(sentence):
            stale += [m.group(0) for m in _DATE.finditer(sentence) if "[PAST" in _stamp_dates(m.group(0), today)]
    return list(dict.fromkeys(stale))


def _sources_block(sources: list, today: str = "") -> str:
    return "\n".join(
        f"[{i + 1}] {s.get('title') or s.get('domain', '')} — {s.get('domain', '')}"
        + (f" — published {s['published']}{_age(s['published'], today)}" if s.get("published") else " — no publication date")
        + f"\n    {s.get('url', '')}"
        for i, s in enumerate(sources[:10]))


async def _judge(model: str, criteria: str, state: ShifuState, research: str, sources: list, note: str = "") -> _Judgment:
    if model not in _cache:
        _cache[model] = ChatOpenAI(model=model, temperature=0).with_structured_output(_Judgment)
    # La nota va AL FINAL: arriba, lejos de donde el modelo concluye, hacia la segunda busqueda y aun asi escribia
    # "estara disponible el 18 de septiembre de 2026" un 11 de octubre (2 de 3 corridas).
    user = (f"TODAY: {state.get('current_time_utc') or 'unknown'}\n"
            f"SEARCH WINDOW: {state.get('research_freshness') or 'unknown'}\n"
            f"USER QUESTION: {_question(state)}\n\n"
            f"SOURCES:\n{_sources_block(sources, str(state.get('current_time_utc') or ''))}\n\n"
            # ponytail: tope fijo de caracteres; resumir por fuente si se queda corto
            f"SEARCH RESULTS:\n{_stamp_dates(research[:24000], str(state.get('current_time_utc') or ''))}"
            f"{note}")
    return await _cache[model].ainvoke(
        [{"role": "system", "content": _SYSTEM.format(criteria=criteria)}, {"role": "user", "content": user}],
        config={"tags": ["research_analyst"]})


def _render(j: _Judgment, searches: int) -> str:
    lines = ["## Analyst judgment (the search results were already reasoned about: build the answer on this)",
             f"Conclusion: {j.conclusion}", f"Confidence: {j.confidence}", f"Reasoning: {j.reasoning}"]
    if j.caveats:
        lines.append("Caveats to tell the user: " + " | ".join(j.caveats))
    if j.discarded:
        lines.append("Sources NOT to use: " + " | ".join(j.discarded))
    if searches > 1:
        lines.append(f"({searches} searches were made; the second one was aimed at settling the doubt.)")
    return "\n".join(lines)


async def research_analyst_node(state: ShifuState) -> dict:
    research = state.get("retrieved_research")
    if not research:
        return {}
    policy = {**_DEFAULT_POLICY, **((await get_agent_personality()) or {}).get("research_policy", {})}
    if not policy.get("enabled", True):
        return {}
    sources = list(state.get("retrieved_sources") or [])
    searches, extra, today = 1, "", str(state.get("current_time_utc") or "")
    try:
        judgment = await _judge(policy["model"], policy["criteria"], state, research, sources)
        for _ in range(int(policy.get("max_followups", 1))):
            past = _already_past(judgment.announced, today)
            note = "".join(
                f"\n\nDATE CHECK (computed by code, it is a fact): '{a.what}' was dated {a.date} and TODAY is {today[:10]}. "
                f"{a.date} is BEFORE today: it is in the PAST. Write about it in the past tense, as something that "
                "already happened (released, held, in effect), unless a source says it was cancelled or delayed. Never "
                "write that it 'will' happen or 'is upcoming'. Sources that call it upcoming are outdated, and so is "
                f"whatever they call 'the latest', 'the newest' or 'current': that was true only before {a.date}, and "
                "this is newer." for a in past)
            query = past[0].check_query.strip() if past else (judgment.follow_up_query or "").strip()
            if not query or (judgment.confidence == "high" and not past):
                break
            # La segunda busqueda no hereda la ventana de fechas de la primera: busca lo que falto.
            more = await tavily_searcher_node({**state, "optimized_search_query": query, "search_recency": "any", "search_topic": "general"})
            if not more.get("retrieved_research"):
                break
            searches += 1
            known = {s.get("url") for s in sources}
            sources += [s for s in (more.get("retrieved_sources") or []) if s.get("url") not in known]  # al final: no mueve los [N]
            extra += f"\n\n## Second search: {query}\n{more['retrieved_research'][:8000]}"
            # La segunda busqueda se lee primero: con el orden original las paginas viejas (mayoria) ganaban la conclusion.
            judgment = await _judge(policy["model"], policy["criteria"], state,
                                    f"{extra.strip()}\n\n## First search\n{research}", sources, note)
        # Ultima comprobacion por codigo: la conclusion no puede hablar en futuro de una fecha que ya paso. Si lo hace, se
        # rehace UNA vez con el hecho al final (donde el modelo si lo atiende).
        if stale := _future_about_past(judgment.conclusion, today):
            fix = "".join(
                f"\n\nDATE CHECK (computed by code, it is a fact): your conclusion speaks of {d} as something still to "
                f"come, but TODAY is {today[:10]} and {d} is in the PAST. Whatever was announced, set or scheduled for "
                f"{d} has ALREADY happened: say it in the past tense and count it as released/done. If that makes it the "
                "newest one, it IS the answer." for d in stale)
            body_for_judge = f"{extra.strip()}\n\n## First search\n{research}" if extra else research
            judgment = await _judge(policy["model"], policy["criteria"], state, body_for_judge, sources, fix)
            logger.info("[research_analyst] conclusion rewritten: spoke in future about %s", stale)
    except Exception as exc:  # sin juicio el turno sigue con lo que habia
        logger.warning("[research_analyst] failed: %s", exc)
        return {}
    logger.info("[research_analyst] confidence=%s searches=%d discarded=%d", judgment.confidence, searches, len(judgment.discarded))
    body = state.get("curated_research") or state.get("retrieved_research") or ""
    return {"curated_research": f"{_render(judgment, searches)}\n\n## Search results\n{body}{extra}",
            "retrieved_sources": sources or None}
