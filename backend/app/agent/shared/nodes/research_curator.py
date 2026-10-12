"""
research_curator — agente_v3 Semantic Preservation node

Domain-agnostic pipeline that transforms long research text into a compact
representation preserving ALL information relevant to the user's query.
No lossy compression — the curator classifies and acts, never compresses.

Pipeline:
  A. Adaptive segmentation  — chunk_size = f(total_chars, effort_tier)
  B. Parallel extraction    — each chunk → information units (bullets)
  C. Deterministic dedup    — exact hash + near-similarity (no LLM)
  D. Batch classify (LLM)   — keep / merge / conflict
  E. Apply groups           — build refined list
  F. Conflict resolution    — Tavily search per conflict (conditional)
  G. Fact verification      — Tavily cross-check (conditional on needs_fact_verification)
  H. Time enrichment        — deterministic timezone conversion (Python, no LLM)

Output size is determined by the volume of unique facts, not by a token cap.
"""

import asyncio
import logging
import os
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.agent.shared.context.timezone_converter import convert_times_in_text
from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print

logger = logging.getLogger(__name__)

_CURATOR_CONFIG: dict[str, dict] = {
    "low":   {"target_chunk": 0,      "max_batches": 0,   "ext_tokens": 0},
    "medio": {"target_chunk": 10_000, "max_batches": 8,   "ext_tokens": 800},
    "high":  {"target_chunk": 10_000, "max_batches": 12,  "ext_tokens": 1_000},
    "max":   {"target_chunk": 12_000, "max_batches": 15,  "ext_tokens": 1_200},
}
_DEFAULT_EFFORT       = "medio"
_CLASSIFY_BATCH_SIZE  = 40   # bullets per sub-batch when classify must split

# ── Pydantic schemas ───────────────────────────────────────────────────────────

class BulletGroup(BaseModel):
    action: Literal["keep", "merge", "conflict"]
    bullets: list[int]
    merged: Optional[str] = None
    conflict_note: Optional[str] = None

class ClassifyResult(BaseModel):
    groups: list[BulletGroup]

class RankResult(BaseModel):
    ranked_indices: list[int]

# ── Prompts ────────────────────────────────────────────────────────────────────

_EXTRACTOR_SYSTEM = """\
You are a research information extractor for Shifu AI.

Given a research segment and the user's query, extract all units of information
that are relevant to answering the query.

Information units include: facts, values, dates, times, relationships,
entities (people, objects, concepts, events), and contextual references.

Rules:
- Preserve all values verbatim: numbers, dates, times, names — never paraphrase
- When the segment shows when a fact was published or which date it refers to ("Published:", "as of", a dated
  headline), keep that date inside the bullet — the reader must be able to tell a current fact from an old one
- Include a unit if it could help answer the query (relevance check)
- Do not include units that are clearly unrelated to the query
- Output: bullet points, one information unit per bullet
- Include ONLY what is present in this segment. Do not invent.
"""

_CLASSIFY_SYSTEM = """\
You are a fact deduplicator for Shifu AI research pipeline.

Given a numbered list of extracted facts and the user's query, classify each fact:

- "keep"     : ANY fact with unique information — keep as its own entry.
               Use this even when multiple facts concern the same story, as long as
               they contain different details (different numbers, dates, names,
               quotes, or angles). When in doubt, keep.

- "merge"    : ONLY when two or more bullets express THE EXACT SAME CLAIM in
               different words — same fact, same value, just paraphrased.
               Do NOT merge facts just because they relate to the same event or topic.
               The merged field must be the most complete single version.

- "conflict" : Two facts that directly CONTRADICT each other on the same specific
               claim (e.g., "35 dead" vs "42 dead" for the same event).
               Flag with a brief conflict_note for external verification.

CRITICAL: Every unique detail, number, name, date, or perspective is a separate
fact — keep them all. Only collapse truly redundant content (same claim, same value).

Every bullet must appear in exactly one group.
Preserve all numbers, dates, names, and values verbatim.
"""

_RANK_SYSTEM = """\
You are a news relevance ranker for Shifu AI.

Given a numbered list of extracted news facts and the user's query and context,
return the indices reordered from most to least relevant and interesting for THIS user.

Use the NEWS CONTENT ITSELF as the primary ranking signal:
1. Facts that directly answer or closely relate to what the user asked (query match)
2. Facts with high impact, concrete data, or surprising/notable developments
3. Facts that affect the user's region or country (if location is provided)
4. Less directly relevant or background facts last

Do NOT rank by topic category alone — read each fact and judge its actual relevance
to this user's interest as expressed in their query.

Return ONLY: {"ranked_indices": [<all original indices in new order>]}
Every index must appear exactly once.
"""

_VERIFY_SYSTEM = """\
You are a fact checker. Given a list of facts and fresh web evidence,
verify each fact. If confirmed or unrelated to the evidence, keep it as-is.
If clearly contradicted by the evidence, correct it using the evidence.
Return the same number of facts, in the same order.
Preserve all values verbatim. Output: one fact per line, no bullets, no numbering.
"""

# ── Regexes ────────────────────────────────────────────────────────────────────

_BULLET_START = re.compile(r'^\s*[-•*]\s+')
_NON_WORD_RE  = re.compile(r'[^\w\s]')


# ── Phase A helpers ────────────────────────────────────────────────────────────

def _compute_chunks(research: str, target_chunk: int, max_batches: int) -> list[str]:
    total = len(research)
    n = max(2, min(max_batches, total // target_chunk))
    chunk_size = total // n
    return [research[i : i + chunk_size] for i in range(0, total, chunk_size)][:n]


async def _extract_batch(
    chunk: str,
    query: str,
    batch_num: int,
    total: int,
    max_tokens: int,
) -> str:
    logger.info(
        "[research_curator] chunk %d/%d — extracting  (%d chars  max_tokens=%d)",
        batch_num, total, len(chunk), max_tokens,
    )
    user_msg = (
        f"USER QUERY: {query}\n\n"
        f"RESEARCH SEGMENT {batch_num}/{total}:\n{chunk}"
    )
    try:
        llm  = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=max_tokens, timeout=25).with_retry(
            stop_after_attempt=3, wait_exponential_jitter=True
        )
        resp = await llm.ainvoke([
            SystemMessage(content=_EXTRACTOR_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        result = (resp.content or "").strip()
        bullets = result.count("\n- ") + (1 if result.startswith("- ") else 0)
        logger.info(
            "[research_curator] chunk %d/%d — done  (%d bullets  %d chars out)",
            batch_num, total, bullets, len(result),
        )
        return result
    except Exception as exc:
        logger.warning("[research_curator] chunk %d/%d — failed: %s", batch_num, total, exc)
        return ""


# ── Phase B: flatten ───────────────────────────────────────────────────────────

def _extract_bullets(units: list[str]) -> list[str]:
    bullets = []
    for u in units:
        for line in u.splitlines():
            if _BULLET_START.match(line):
                bullets.append(line.strip().lstrip("-•* ").strip())
    return bullets


# ── Phase C: deterministic dedup ──────────────────────────────────────────────

def _normalize_bullet(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = _NON_WORD_RE.sub("", text)
    return " ".join(text.split())


def _deterministic_dedup(bullets: list[str], threshold: float = 0.92) -> tuple[list[str], int, int]:
    """Returns (unique_bullets, exact_removed, near_removed)."""
    normalized: list[str] = []
    unique: list[str] = []
    exact_removed = 0
    near_removed  = 0

    for bullet in bullets:
        norm = _normalize_bullet(bullet)
        if not norm:
            continue
        if norm in normalized:
            exact_removed += 1
            continue
        is_near_dup = any(
            SequenceMatcher(None, norm, prev).ratio() >= threshold
            for prev in normalized
        )
        if is_near_dup:
            near_removed += 1
            continue
        normalized.append(norm)
        unique.append(bullet)

    return unique, exact_removed, near_removed


# ── Phase D: batch classify ────────────────────────────────────────────────────

def _classify_max_tokens(n: int) -> int:
    # Per-bullet cost in ClassifyResult JSON:
    #   keep     → ~9 tok   {"action":"keep","bullets":[i]}
    #   merge    → ~45 tok  (includes merged text ~150 chars)
    #   conflict → ~30 tok  (includes conflict_note)
    # Typical distribution 70/25/5 → real average ~20 tok/bullet.
    # Factor 40 = 2× headroom for verbose merged text.
    # With sub-batching ≤40 bullets → real ceiling = 40×40 = 1600 tok/call.
    return min(3_000, max(800, n * 40))


async def _classify_single(bullets: list[str], query: str, offset: int = 0) -> ClassifyResult:
    """Single LLM classify call. `offset` shifts bullet indices for sub-batch merging."""
    numbered = "\n".join(f"[{i}] {b}" for i, b in enumerate(bullets))
    user_msg = f"USER QUERY: {query}\n\nFACTS:\n{numbered}"
    try:
        llm   = ChatOpenAI(model="gpt-4o-mini", temperature=0,
                           max_tokens=_classify_max_tokens(len(bullets)), timeout=30)
        llm_s = llm.with_structured_output(ClassifyResult).with_retry(
            stop_after_attempt=3, wait_exponential_jitter=True
        )
        result: ClassifyResult = await llm_s.ainvoke([
            SystemMessage(content=_CLASSIFY_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        if offset == 0:
            return result
        # Re-index bullet indices to global space
        shifted_groups = []
        for g in result.groups:
            shifted_groups.append(BulletGroup(
                action=g.action,
                bullets=[i + offset for i in g.bullets],
                merged=g.merged,
                conflict_note=g.conflict_note,
            ))
        return ClassifyResult(groups=shifted_groups)
    except Exception as exc:
        logger.error("[research_curator] classify_single failed (offset=%d): %s — keeping batch as-is", offset, exc)
        return ClassifyResult(groups=[
            BulletGroup(action="keep", bullets=[i + offset]) for i in range(len(bullets))
        ])


async def _classify_batched(bullets: list[str], query: str) -> ClassifyResult:
    """Split bullets into sub-batches, classify each in parallel, merge results."""
    batches = [
        bullets[i : i + _CLASSIFY_BATCH_SIZE]
        for i in range(0, len(bullets), _CLASSIFY_BATCH_SIZE)
    ]
    offsets = [i * _CLASSIFY_BATCH_SIZE for i in range(len(batches))]
    tasks   = [_classify_single(batch, query, offset) for batch, offset in zip(batches, offsets)]
    results = await asyncio.gather(*tasks)
    merged_groups = [g for r in results for g in r.groups]
    return ClassifyResult(groups=merged_groups)


async def _batch_classify(bullets: list[str], query: str) -> ClassifyResult:
    """Dispatcher: single call for ≤40 bullets, parallel sub-batches for larger sets."""
    if len(bullets) > _CLASSIFY_BATCH_SIZE:
        return await _classify_batched(bullets, query)
    return await _classify_single(bullets, query)


# ── Phase E.5: relevance ranking ──────────────────────────────────────────

async def _rank_by_relevance(
    facts: list[str], query: str,
    user_location: str, user_country_code: str,
) -> list[str]:
    if len(facts) <= 1:
        return facts
    numbered = "\n".join(f"[{i}] {f}" for i, f in enumerate(facts))
    context  = f"User location: {user_location or 'unknown'} ({user_country_code or '?'})"
    user_msg = f"USER QUERY: {query}\n{context}\n\nFACTS:\n{numbered}"
    try:
        llm    = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=200, timeout=15)
        result: RankResult = await llm.with_structured_output(RankResult).with_retry(
            stop_after_attempt=3, wait_exponential_jitter=True
        ).ainvoke([
            SystemMessage(content=_RANK_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        indices = result.ranked_indices
        if sorted(indices) != list(range(len(facts))):
            logger.warning("[research_curator] ranking returned invalid permutation — keeping original order")
            return facts
        return [facts[i] for i in indices]
    except Exception as exc:
        logger.error("[research_curator] ranking failed: %s — keeping original order", exc)
        return facts


# ── Phase F: conflict resolution ───────────────────────────────────────────────

async def _resolve_conflict(conflict_note: str, query: str) -> str:
    from langchain_tavily import TavilySearch
    try:
        tool = TavilySearch(max_results=3, search_depth="basic", include_answer=True)
        raw  = await tool.ainvoke({"query": f"{query} {conflict_note}"})
        resp = raw if isinstance(raw, dict) else {}
        evidence = (resp.get("answer") or "").strip()
        if not evidence:
            evidence = " | ".join(
                r.get("content", "")[:200] for r in (resp.get("results") or [])[:2]
            )
        if not evidence:
            logger.error("[research_curator] conflict resolution — no evidence found for: %s", conflict_note)
            return None
        llm    = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=150, timeout=20).with_retry(
            stop_after_attempt=3, wait_exponential_jitter=True
        )
        result = await llm.ainvoke([HumanMessage(content=(
            f"CONFLICT: {conflict_note}\n"
            f"EVIDENCE: {evidence}\n\n"
            f"State the correct fact in one concise sentence. Preserve all values verbatim."
        ))])
        return (result.content or "").strip() or None
    except Exception as exc:
        logger.error("[research_curator] conflict resolution failed: %s", exc)
        return None


# ── Phase G: fact verification ─────────────────────────────────────────────────

async def _verify_facts(facts: list[str], query: str) -> tuple[list[str], int]:
    """Returns (verified_facts, changes_count)."""
    from langchain_tavily import TavilySearch
    try:
        tool = TavilySearch(max_results=5, search_depth="basic", include_answer=True)
        raw  = await tool.ainvoke({"query": query})
        resp = raw if isinstance(raw, dict) else {}
        evidence = (resp.get("answer") or "").strip()
        evidence_preview = evidence[:120]
        if not evidence:
            evidence = "\n".join(
                r.get("content", "")[:300] for r in (resp.get("results") or [])[:3]
            )
            evidence_preview = evidence[:120]
        if not evidence:
            return facts, 0

        numbered = "\n".join(f"[{i+1}] {f}" for i, f in enumerate(facts))
        llm      = ChatOpenAI(model="gpt-4o-mini", temperature=0,
                             max_tokens=min(2_000, max(500, len(facts) * 60)), timeout=30).with_retry(
            stop_after_attempt=3, wait_exponential_jitter=True
        )
        result   = await llm.ainvoke([
            SystemMessage(content=_VERIFY_SYSTEM),
            HumanMessage(content=f"FACTS:\n{numbered}\n\nEVIDENCE:\n{evidence}"),
        ])
        lines = [l.strip() for l in (result.content or "").splitlines() if l.strip()]
        if len(lines) < len(facts) // 2:
            return facts, 0

        changes = sum(1 for a, b in zip(facts, lines) if a.strip() != b.strip())
        return lines, changes
    except Exception as exc:
        logger.error("[research_curator] verification failed: %s — keeping unverified", exc)
        return facts, 0


# ── Main node ──────────────────────────────────────────────────────────────────

async def research_curator_node(state: ShifuState) -> dict:
    research      = (state.get("retrieved_research") or "").strip()
    user_timezone = state.get("user_timezone")

    if not research:
        logger.info("[research_curator] skip — no retrieved_research")
        return {"curated_research": None}

    effort = state.get("effort_level") or _DEFAULT_EFFORT
    cfg    = _CURATOR_CONFIG.get(effort, _CURATOR_CONFIG[_DEFAULT_EFFORT])

    if cfg["target_chunk"] == 0:
        logger.info("[research_curator] low effort — pass-through (%d chars)", len(research))
        return {"curated_research": convert_times_in_text(research, user_timezone) or research}

    # Dynamic cap: process up to max_batches × target_chunk × 3 chars.
    # Overhead factor 3 gives each chunk ~3× its target size of source material
    # so the extractor can select the most relevant content from richer input.
    max_processable = cfg["target_chunk"] * cfg["max_batches"] * 3
    if len(research) > max_processable:
        logger.info(
            "[research_curator] research capped: %d → %d chars (max_batches=%d target=%d overhead=3×)",
            len(research), max_processable, cfg["max_batches"], cfg["target_chunk"],
        )
        research = research[:max_processable]

    chunks = _compute_chunks(research, cfg["target_chunk"], cfg["max_batches"])
    real_chunk_size = len(chunks[0]) if chunks else cfg["target_chunk"]

    if len(chunks) <= 1:
        logger.info("[research_curator] 1 chunk (%d chars) — pass-through", len(research))
        return {"curated_research": convert_times_in_text(research, user_timezone) or research}

    query = (
        state.get("optimized_search_query") or
        state.get("structured_prompt") or
        ""
    ).strip()

    needs_verification = bool(state.get("needs_fact_verification", False))

    logger.info(
        "[research_curator] ▶ effort=%s  target=%d  actual_chunk=%d  raw=%d chars  chunks=%d  verify=%s",
        effort, cfg["target_chunk"], real_chunk_size, len(research), len(chunks), needs_verification,
    )

    t0 = datetime.now()

    # ── Phase A: parallel extraction ──────────────────────────────────────────
    # ext_tokens from tier is the ceiling; actual tokens scale with chunk length.
    # ~10 chars per relevant output token is a conservative estimate.
    tasks = [
        _extract_batch(chunk, query, i + 1, len(chunks),
                       min(cfg["ext_tokens"], max(400, len(chunk) // 10)))
        for i, chunk in enumerate(chunks)
    ]
    extracted: list[str] = list(await asyncio.gather(*tasks))
    valid = [e for e in extracted if e]

    if not valid:
        logger.warning("[research_curator] all extractors failed — returning raw")
        return {"curated_research": convert_times_in_text(research, user_timezone) or research}

    # ── Phase B: flatten ──────────────────────────────────────────────────────
    all_bullets = _extract_bullets(valid)
    total_bullets = len(all_bullets)

    if not all_bullets:
        curated_raw = "\n\n---\n\n".join(u for u in valid if u)
        logger.info("[research_curator] no bullets found — returning extracted units")
    else:
        # ── Phase C: deterministic dedup ──────────────────────────────────────
        before_dedup = len(all_bullets)
        all_bullets, exact_removed, near_removed = _deterministic_dedup(all_bullets, threshold=0.85)

        logger.info(
            "[research_curator] dedup: %d → %d bullets (exact=%d near=%d)",
            before_dedup, len(all_bullets), exact_removed, near_removed,
        )
        if DEV_MODE:
            dev_print(
                f"\n┌─ Curator Phase C — Deterministic Dedup ─────────────────────────\n"
                f"│ input         : {before_dedup} bullets (from {len(valid)} chunks)\n"
                f"│ removed exact : {exact_removed}\n"
                f"│ removed near  : {near_removed}  (threshold=0.85)\n"
                f"│ remaining     : {len(all_bullets)} bullets → LLM classify\n"
                f"└──────────────────────────────────────────────────────────────────"
            )

        # ── Phase D: batch classify ───────────────────────────────────────────
        classify_result = await _batch_classify(all_bullets, query)

        # ── Phase E: apply groups ─────────────────────────────────────────────
        refined: list[str]             = []
        conflicts: list[tuple[str, list[str]]] = []
        kept = merged_count = 0

        for g in classify_result.groups:
            if g.action == "keep" and g.bullets:
                idx = g.bullets[0]
                if 0 <= idx < len(all_bullets):
                    refined.append(all_bullets[idx])
                    kept += 1
            elif g.action == "merge" and g.merged:
                refined.append(g.merged)
                merged_count += 1
            elif g.action == "conflict" and g.conflict_note:
                conflicts.append((g.conflict_note, [all_bullets[i] for i in g.bullets if 0 <= i < len(all_bullets)]))

        if DEV_MODE:
            n_subbatches = max(1, (len(all_bullets) + _CLASSIFY_BATCH_SIZE - 1) // _CLASSIFY_BATCH_SIZE)
            tok_per_batch = _classify_max_tokens(min(len(all_bullets), _CLASSIFY_BATCH_SIZE))
            fact_preview = "".join(
                f"│ fact[{i}]  : {f[:90]}\n" for i, f in enumerate(refined[:3])
            )
            dev_print(
                f"\n┌─ Curator Phase D — Batch Classify ──────────────────────────────\n"
                f"│ bullets in    : {len(all_bullets)}\n"
                f"│ sub_batches   : {n_subbatches}  (size≤{_CLASSIFY_BATCH_SIZE}  tokens={tok_per_batch}/batch)\n"
                f"│ kept          : {kept}  (unique, independent)\n"
                f"│ merged        : {merged_count}  pairs → {merged_count} facts\n"
                f"│ conflicts     : {len(conflicts)}  → flagged for Tavily\n"
                + fact_preview
                + f"└──────────────────────────────────────────────────────────────────"
            )

        # ── Phase E.5: relevance ranking ─────────────────────────────────────
        if needs_verification and refined:
            before_rank = refined[0][:70] if refined else ""
            refined = await _rank_by_relevance(
                refined, query,
                state.get("user_location") or "",
                state.get("user_country_code") or "",
            )
            if DEV_MODE:
                dev_print(
                    f"\n┌─ Curator Phase E.5 — Relevance Ranking ─────────────────────────\n"
                    f"│ ranked        : {len(refined)} facts\n"
                    f"│ top fact      : {refined[0][:80] if refined else '—'}\n"
                    f"└──────────────────────────────────────────────────────────────────"
                )

        # ── Phase F: conflict resolution ──────────────────────────────────────
        if conflicts:
            resolution_lines = []
            for note, originals in conflicts:
                resolved = await _resolve_conflict(note, query)
                if resolved:
                    refined.append(resolved)
                    logger.info("[research_curator] conflict resolved: %s", resolved[:80])
                else:
                    logger.error("[research_curator] conflict unresolvable — dropped: %s", note)
                resolution_lines.append(f"│   → \"{resolved[:70]}\"")

            if DEV_MODE:
                dev_print(
                    f"\n┌─ Curator Phase F — Conflict Resolution ─────────────────────────\n"
                    f"│ conflicts     : {len(conflicts)} detected\n"
                    f"│ resolved      :\n"
                    + "\n".join(resolution_lines) + "\n"
                    + f"└──────────────────────────────────────────────────────────────────"
                )

        # ── Phase G: fact verification ────────────────────────────────────────
        verify_evidence_preview = ""
        if needs_verification:
            refined, changes = await _verify_facts(refined, query)
            logger.info(
                "[research_curator] verification ran — %d facts  %d changes",
                len(refined), changes,
            )
            if DEV_MODE:
                dev_print(
                    f"\n┌─ Curator Phase G — Fact Verification ───────────────────────────\n"
                    f"│ needs_fact_verification : True\n"
                    f"│ facts in      : {len(refined)}\n"
                    f"│ facts out     : {len(refined)}\n"
                    f"│ changes       : {changes} corrected\n"
                    f"└──────────────────────────────────────────────────────────────────"
                )
        else:
            logger.info("[research_curator] skip verification — static query type")
            if DEV_MODE:
                dev_print(
                    f"\n┌─ Curator Phase G — Fact Verification ───────────────────────────\n"
                    f"│ skipped — query type is static (needs_fact_verification=False)\n"
                    f"└──────────────────────────────────────────────────────────────────"
                )

        curated_raw = "\n".join(f"- {f}" for f in refined)

        logger.info(
            "[research_curator] classify: %d bullets → %d refined  conflicts=%d  chars=%d",
            len(all_bullets), len(refined), len(conflicts), len(curated_raw),
        )

    elapsed = (datetime.now() - t0).total_seconds()

    # ── Phase H: time enrichment ──────────────────────────────────────────────
    curated_enriched = convert_times_in_text(curated_raw, user_timezone) or curated_raw

    # Output-ratio check (replaces old coverage metric)
    output_ratio = len(curated_enriched) / max(len(research), 1)
    if output_ratio < 0.10:
        logger.warning(
            "[research_curator] very low output ratio=%.0f%% — extraction may have failed",
            output_ratio * 100,
        )

    # ── Metrics ───────────────────────────────────────────────────────────────
    metrics = {
        "total_bullets":      total_bullets,
        "unique_bullets":     len(all_bullets) if all_bullets else 0,
        "refined_bullets":    len(refined) if all_bullets else 0,
        "conflicts_detected": len(conflicts) if all_bullets else 0,
        "curated_chars":      len(curated_enriched),
        "verification_ran":   needs_verification,
        "elapsed_ms":         round((datetime.now() - t0).total_seconds() * 1000),
    }
    logger.info("[research_curator] metrics: %s", metrics)

    # ── Dev summary box ───────────────────────────────────────────────────────
    if DEV_MODE:
        tz_line = f"│ timezone      : {user_timezone}\n" if user_timezone else ""
        max_processable = cfg["target_chunk"] * cfg["max_batches"] * 3
        dev_print(
            f"\n┌─ Research Curator ──────────────────────────────────────────────\n"
            f"│ effort        : {effort}\n"
            f"│ chunks        : {len(chunks)}  raw={len(research):,} chars  cap={max_processable:,}\n"
            f"│ bullets       : {total_bullets} total → {metrics['unique_bullets']} unique "
            f"(dedup -{total_bullets - metrics['unique_bullets']}) → {metrics['refined_bullets']} refined\n"
            f"│ conflicts     : {metrics['conflicts_detected']} resolved via Tavily\n"
            f"│ verification  : {'enabled' if needs_verification else 'skipped (static)'}\n"
            f"│ output        : {len(curated_enriched):,} chars\n"
            f"{tz_line}"
            f"│ elapsed       : {elapsed:.1f}s\n"
            f"└─────────────────────────────────────────────────────────────────"
        )

    return {"curated_research": curated_enriched}

