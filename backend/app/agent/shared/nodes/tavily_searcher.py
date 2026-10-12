"""
tavily_searcher — agente_v3 Information Enrichment node

Two-phase search pipeline with effort-tier parametrization (Inference-Time Scaling):

  Phase 1 — TavilySearch (always runs when needs_external_info=True):
    Depth, max_results, include_answer, and include_raw_content are driven by
    the session's effort_level (low/medio/high/max).

  Phase 2 — TavilyExtract (runs only for tiers ≥ medio):
    Pulls full Markdown from the top N URLs. N = 0 for low, 1 for medio,
    2 for high, 4 for max. extract_depth = "basic" for medio, "advanced" for high/max.

Query source priority (Query Poisoning fix):
  1. state.optimized_search_query  — clean SEO query built by semantic_intake LLM.
  2. state.structured_prompt       — fallback (first ~200 chars).

Inbound sanitization:
  _sanitize() replaces competitor brand names (Zapier, Make, n8n, etc.) with
  generic terms BEFORE the text reaches the LLM.
"""

import json
import logging
import os
import re
from urllib.parse import urlparse

from langchain_tavily import TavilyExtract, TavilySearch

from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print

logger = logging.getLogger(__name__)

_TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Inference-Time Scaling: search depth and research budget per effort tier.
# effort_level is set by the WS handler from the client message (default: "medio").
_EFFORT_CONFIGS: dict[str, dict] = {
    "low":   {"depth": "basic",    "max_res": 3,  "answer": False, "raw": False, "ext_urls": 0, "ext_depth": "basic",    "cap":   3_000, "snippet_cap":   800},
    # medio (el esfuerzo por defecto) ya no descarga las paginas completas: con raw+extract traia ~90,000 caracteres, el
    # curador hacia 12 llamadas al modelo y el turno tardaba ~55 s para "a cuanto esta el dolar" (v092_web_real). Con la
    # respuesta de Tavily y los fragmentos alcanza para una pregunta normal; high y max siguen leyendo las paginas.
    "medio": {"depth": "advanced", "max_res": 7,  "answer": True,  "raw": False, "ext_urls": 0, "ext_depth": "basic",    "cap": 1_000_000, "snippet_cap": 3_000},
    "high":  {"depth": "advanced", "max_res": 7,  "answer": True,  "raw": True,  "ext_urls": 3, "ext_depth": "advanced", "cap": 1_000_000, "snippet_cap": 5_000},
    "max":   {"depth": "advanced", "max_res": 10, "answer": True,  "raw": True,  "ext_urls": 5, "ext_depth": "advanced", "cap": 1_000_000, "snippet_cap": 8_000},
}
_DEFAULT_EFFORT = "medio"
# Valores de time_range de Tavily, del mas estrecho al mas amplio. No hay "year": medido el 2026-10-11, filtrar por
# año saca la documentacion oficial y Wikipedia (no traen fecha de publicacion reciente) y deja blogs.
_WINDOWS = ["day", "week", "month"]

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Competitor brand → generic replacement.
# Keys are lowercase; regex match is case-insensitive.
_BRAND_MAP: dict[str, str] = {
    "zapier":       "traditional automation legacy systems",
    "make.com":     "visual workflow orchestrators",
    "make":         "visual workflow orchestrators",
    "integromat":   "visual workflow orchestrators",
    "n8n":          "alternative self-hosted workflow engines",
    "workato":      "enterprise integration platforms",
    "tray.io":      "enterprise integration platforms",
    "tray":         "enterprise integration platforms",
    "automate.io":  "cloud automation services",
    "pabbly":       "cloud automation services",
}

_BRAND_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(re.escape(brand), re.IGNORECASE), replacement)
    for brand, replacement in _BRAND_MAP.items()
]


def _sanitize(text: str) -> str:
    for pattern, replacement in _BRAND_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _parse_search_response(raw) -> dict:
    """Normalize TavilySearch output to {answer, results} regardless of return type."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"results": parsed, "answer": ""}
        except (json.JSONDecodeError, ValueError):
            pass
    return {"results": [], "answer": ""}


def _parse_extract_response(raw, cap: int = 15_000) -> str:
    """Flatten TavilyExtract response to a single markdown string."""
    target: dict | None = None
    if isinstance(raw, dict):
        target = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                target = parsed
        except (json.JSONDecodeError, ValueError):
            return raw[:cap]

    if target:
        results = target.get("results") or []
        parts = []
        for r in results:
            if not isinstance(r, dict):
                continue
            content = r.get("raw_content") or r.get("content") or ""
            url     = r.get("url", "")
            if content:
                parts.append(f"**Source:** {url}\n\n{content}" if url else content)
        return "\n\n---\n\n".join(parts)

    return ""


async def tavily_searcher_node(state: ShifuState) -> dict:
    needs_research = state.get("needs_external_info") or False
    logger.info("[tavily_searcher] ▶ needs_external_info=%s", needs_research)

    if not needs_research:
        logger.info("[tavily_searcher] skip — needs_external_info=False")
        return {"retrieved_research": None, "retrieved_sources": None}

    # Query priority: optimized SEO query (no poisoning) > structured prompt fallback
    query = (state.get("optimized_search_query") or "").strip()
    if not query:
        query = (state.get("structured_prompt") or "").strip()[:200]

    # Conditional location append — only when semantic_intake flagged the query as
    # location-sensitive. Avoids contaminating universal queries with user's city.
    user_location  = (state.get("user_location") or "").strip()
    location_aware = bool(state.get("location_aware", False))
    # El lugar ya NO se pega aqui: semantic_intake lo escribe en la consulta cuando importa ("Guadalajara weather",
    # "Mexico VAT rate"). Pegarlo siempre ensuciaba todo (medido el 2026-10-11 con eval_web.py: location_aware salia
    # true en 14 de 17 preguntas y "bitcoin price ... Guadalajara, Mexico" devolvia un partido de futbol).

    if not query:
        logger.info("[tavily_searcher] skip — no query available")
        return {"retrieved_research": None, "retrieved_sources": None}

    if not _TAVILY_API_KEY:
        logger.warning("[tavily_searcher] skip — TAVILY_API_KEY not set in .env")
        return {"retrieved_research": None, "retrieved_sources": None}

    # ── Resolve effort tier ───────────────────────────────────────────────────
    effort        = (state.get("effort_level") or _DEFAULT_EFFORT)
    cfg           = _EFFORT_CONFIGS.get(effort, _EFFORT_CONFIGS[_DEFAULT_EFFORT])
    is_news_query = bool(state.get("needs_fact_verification", False))

    # ── Deterministic temporal anchor (news queries only) ────────────────────
    # Only for time-sensitive queries: inject day+month+year so Tavily anchors
    # results to the present. Skipped for general/comparison/historical queries
    # to avoid biasing results toward recent content only.
    _current_time = (state.get("current_time_utc") or "").strip()
    _anchor = ""
    _filtered = state.get("search_recency") in _WINDOWS  # con filtro de fecha el ancla sobra y ensucia la consulta
    if is_news_query and not _filtered and _current_time and not re.search(r'\b20\d{2}\b', query):
        _year = _current_time[:4]
        try:
            _month = _MONTH_NAMES[int(_current_time[5:7]) - 1]
            _day   = str(int(_current_time[8:10]))
        except (ValueError, IndexError):
            _month, _day = "", ""
        _anchor = f"{_month} {_day} {_year}".strip() if _month and _day else _year
        query = f"{query} {_anchor}"
        logger.info("[tavily_searcher] temporal anchor injected: %r", _anchor)

    logger.info(
        "[tavily_searcher] effort=%s  depth=%s  max_res=%d  cap=%d  news=%s",
        effort, cfg["depth"], cfg["max_res"], cfg["cap"], is_news_query,
    )

    synthesized_answer = ""
    results: list[dict] = []
    top_urls: list[str] = []
    snippets: list[str] = []
    extract_content     = ""
    structured_sources: list[dict] = []

    # ── Phase 1: TavilySearch (parametrized by effort tier) ──────────────────
    # Ventana de fechas: el usuario quiere lo vigente salvo que pida lo viejo. La elige semantic_intake
    # (search_recency): day/week/month para lo que cambia, "any" (sin filtro) para hechos estables y documentacion.
    # Sin ella, una semana para noticias. Si la ventana no trae nada se amplia un escalon y `research_freshness` lo
    # dice, para que el responder no presente lo viejo como actual.
    recency = state.get("search_recency")
    if recency not in (*_WINDOWS, "any"):
        recency = "week" if is_news_query else "any"
    windows = [*_WINDOWS[_WINDOWS.index(recency):], None] if recency in _WINDOWS else [None]
    window = None
    try:
        for window in windows:
            search_kwargs: dict = dict(
                max_results=cfg["max_res"],
                search_depth=cfg["depth"],
                include_answer=cfg["answer"],
                include_raw_content=cfg["raw"],
            )
            if window:
                search_kwargs["time_range"] = window
            # "news" es el unico indice que devuelve published_date, pero para clima o precios trae notas sueltas:
            # lo decide semantic_intake (search_topic); sin ese campo, noticias con ventana corta.
            topic = state.get("search_topic") or ("news" if is_news_query and window in ("day", "week") else "general")
            if topic == "news" and window:  # sin ventana el indice de noticias devolvia notas de hace un año
                search_kwargs["topic"] = "news"
            search_tool  = TavilySearch(**search_kwargs)
            raw_response = await search_tool.ainvoke({"query": query})
            response     = _parse_search_response(raw_response)
            results      = [r for r in (response.get("results") or []) if isinstance(r, dict)]
            if results:
                break
            logger.info("[tavily_searcher] nothing in the last %s — widening", window)

        synthesized_answer = _sanitize((response.get("answer") or "").strip())

        for r in results:
            title   = _sanitize(r.get("title", ""))
            url     = r.get("url", "")
            content = _sanitize(r.get("raw_content") or r.get("content") or "")
            published = str(r.get("published_date") or "").strip()
            if url:
                top_urls.append(url)
                domain = urlparse(url).netloc.removeprefix("www.")
                structured_sources.append({"title": title or domain, "url": url, "domain": domain,
                                           **({"published": published} if published else {})})
            if title or content:
                header = f"### {title}\n{url}" if title else url
                if published:
                    header += f"\nPublished: {published}"
                body   = f"\n{content[:cfg['snippet_cap']]}" if content else ""
                snippets.append(header + body)

        logger.info(
            "[tavily_searcher] phase1 → answer=%d chars  results=%d  urls=%d",
            len(synthesized_answer), len(results), len(top_urls),
        )

    except Exception as exc:
        logger.warning("[tavily_searcher] phase1 failed: %s", exc)

    # ── Phase 2: TavilyExtract (skipped for low tier) ────────────────────────
    urls_to_extract = top_urls[:cfg["ext_urls"]]
    if urls_to_extract:
        try:
            extract_tool = TavilyExtract(extract_depth=cfg["ext_depth"], format="markdown")
            raw_extract  = await extract_tool.ainvoke({"urls": urls_to_extract})
            extract_content = _sanitize(_parse_extract_response(raw_extract, cap=cfg["cap"]))
            logger.info("[tavily_searcher] phase2 → extracted=%d chars  urls=%d", len(extract_content), len(urls_to_extract))
        except Exception as exc:
            logger.warning("[tavily_searcher] phase2 extract failed: %s", exc)

    # ── Consolidate (with tier character budget) ──────────────────────────────
    if not synthesized_answer and not snippets and not extract_content:
        logger.info("[tavily_searcher] ◀ no content retrieved")
        return {"retrieved_research": None, "retrieved_sources": None}

    parts: list[str] = []

    if synthesized_answer:
        parts.append(f"## Synthesized Answer\n{synthesized_answer}")

    if snippets:
        parts.append("## Source Snippets\n" + "\n\n".join(snippets))

    if extract_content:
        budget_used = sum(len(p) for p in parts)
        remaining   = cfg["cap"] - budget_used
        if remaining > 500:
            parts.append(f"## Detailed Page Content\n{extract_content[:remaining]}")

    research = "\n\n".join(parts)[:cfg["cap"]]

    logger.info(
        "[tavily_searcher] ◀ research ready — %d chars  (answer=%s  snippets=%d  extract=%d)",
        len(research), bool(synthesized_answer), len(snippets), len(extract_content),
    )

    if DEV_MODE:
        topic_line  = f"{search_kwargs.get('topic', 'general')}  time_range={window or 'none'} (asked {recency})"
        anchor_disp = repr(_anchor) if _anchor else "— (year already in query)"
        dev_print(
            f"\n┌─ Tavily Searcher ──────────────────────────────────────────\n"
            f"│ effort       : {effort}  (depth={cfg['depth']}  max_res={cfg['max_res']}  cap={cfg['cap']})\n"
            f"│ topic        : {topic_line}\n"
            f"│ date anchor  : {anchor_disp}\n"
            f"│ location_aware: {location_aware}  location={user_location or '—'}\n"
            f"│ query        : {query[:120]}\n"
            f"│ phase1       : {len(results)} results  synthesized={bool(synthesized_answer)}\n"
            + "".join(f"│   [{i+1}] {r.get('title','?')[:80]}\n" for i, r in enumerate(results))
            + f"│ phase2       : {len(extract_content)} chars extracted  urls={len(urls_to_extract)}\n"
            f"│ total        : {len(research)} chars ({round(len(research)/4)} ~tokens)\n"
            f"└────────────────────────────────────────────────────────────"
        )

    today = _current_time[:10] or "unknown"
    if not window and recency == "any":
        freshness = (f"No date filter was used (stable fact, documentation or history). Today is {today}; prefer the most "
                     "recent source and say the date of anything that may have changed.")
    elif not window:
        freshness = (f"Nothing was published in the last month, so the search ran without a date filter. Today is {today}. "
                     "Tell the user the information may not be recent.")
    elif window == recency:
        freshness = f"Only pages published in the last {window} were searched. Today is {today}."
    else:
        freshness = (f"Nothing was published in the last {recency}, so the search was widened to the last {window}. "
                     f"Today is {today}. Tell the user the information is not from the last {recency}.")

    return {
        "retrieved_research": research,
        "retrieved_sources":  structured_sources or None,
        "research_freshness": freshness,
    }

