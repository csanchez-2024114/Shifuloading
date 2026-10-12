"""
document_analyzer — agente_v3

Added to _route_from_intake's fan-out in builder_standard.py — runs in
parallel with catalog_checker/auth_validator/tavily_subgraph (same fan-in
into bigtools_inspector). Ingests any files the user attached this turn
(turn_resources), extracts their text, and prepares context for the
responder: short documents are inlined directly into turn_document_context;
large documents (chunking + Atlas Vector Search retrieval) and structured
extraction + HITL review are wired in later phases on top of this same node.

Extractions are cached (document_cache.py) by file_id so re-referencing a
document already seen in this conversation (needs_document_context, set by
semantic_intake) never re-downloads/re-OCRs it — it's read straight back from
Mongo via session_documents (persisted across turns by the checkpointer).

Errors on individual files are written to validation_reports (the same
channel catalog_checker/auth_validator already use) so one broken upload
never breaks the turn or requires new UI.
"""

import hashlib
import json
import logging
import os
import zipfile
from io import BytesIO

from bson import ObjectId
from langchain_core.messages import HumanMessage
from openai import AsyncOpenAI

from config import Config
from app.agent.shared.documents.document_cache import get_cached_extraction, save_extraction, touch_extraction
from app.agent.shared.documents.document_chunks import chunk_and_embed, search_document_chunks
from app.agent.shared.documents.structured_extraction import extract_structured_data, _check_invoice_totals
from app.agent.shared.documents.youtube_transcript import (
    fetch_youtube_transcript, file_id_for_youtube, find_youtube_video_ids,
)
from app.agent.shared.memory.memory_embedder import embed_text
from app.agent.shifu_base_v1.graph.state import ShifuState
from app.billing.plans import get_plan_rules
from app.core.constants import Collections
from app.core.mongo import mongo_manager
from app.services import file_store
from app.tools.connectors.file_tool import FileProvider

logger = logging.getLogger(__name__)

# Per-document char budget injected into the prompt, and a total cap across
# all short documents attached/referenced this turn (~8k tokens each, ~10k
# tokens total). Documents that don't fit get flagged instead of silently
# truncated — chunking+retrieval for oversized documents lands in Fase 3.
_SHORT_DOC_CHAR_BUDGET = 32_000
_TOTAL_CONTEXT_CHAR_CAP = 40_000
_CHUNK_THRESHOLD = 32_000  # chars (~8k tokens) — docs above this get chunked+embedded

# YouTube links pasted as plain text — capped like the WS handler's own
# turn_resources cap (10/turn), but tighter since each one is a network call.
_YOUTUBE_MAX_PER_TURN = 3

# ZIP expansion limits — the second check (declared size, read from the local
# header) runs BEFORE any zf.read(), so a zip bomb never gets decompressed
# into memory in the first place.
_ZIP_MAX_MEMBERS = 20
_ZIP_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB
_ZIP_ALLOWED_EXTS = {"pdf", "docx", "xlsx", "xls", "csv", "json", "png", "jpg", "jpeg", "webp", "pptx", "msg"}

_file_provider = FileProvider()


def file_id_for(resource: dict) -> str:
    """Cloudinary public_id when available; otherwise a stable hash of the URL."""
    file_id = resource.get("file_id")
    if file_id:
        return file_id
    return hashlib.sha256((resource.get("url") or "").encode("utf-8")).hexdigest()[:32]


async def _get_user_plan(user_id: str | None) -> dict:
    """Same lookup pattern as memory_retriever.py/workflow_service.py — fails
    closed to 'free' on any error, never lets OCR run on a lookup failure."""
    if not user_id:
        return get_plan_rules("free")
    try:
        db = mongo_manager.db
        user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
    except Exception:
        user_doc = None
    plan_name = (user_doc or {}).get("plan") or "free"
    return get_plan_rules(plan_name)


async def document_analyzer_node(state: ShifuState) -> dict:
    if state.get("extraction_review_pending"):
        return await _resolve_extraction_review(state)
    return await _ingest_and_analyze(state)


async def _extract_one(db, resource: dict, *, ocr_allowed: bool, user_id: str | None, conversation_id: str | None):
    """Downloads + extracts a single resource, going through document_cache
    first. Returns (file_id, title, url, result_dict) where result_dict has
    the same shape as FileProvider.get_text_and_meta()'s return value."""
    url = resource.get("url")
    title = resource.get("title") or (url.rsplit("/", 1)[-1] if url else "archivo")
    file_id = file_id_for(resource)

    if not url:
        return file_id, title, url, {"text": "", "engine": None, "page_count": None, "ocr_used": False, "error": "missing_url"}

    cached = await get_cached_extraction(db, file_id)
    if cached is not None:
        await touch_extraction(db, file_id)
        logger.info("[document_analyzer] cache hit file=%s engine=%s", title, cached.get("engine"))
        return file_id, title, url, {
            "text": cached.get("text", ""), "engine": cached.get("engine"),
            "page_count": cached.get("page_count"), "ocr_used": cached.get("ocr_used", False),
            "error": cached.get("extraction_error"),
        }

    try:
        if url.startswith(file_store.SCHEME):  # subido por POST /api/v1/files: se lee de Mongo, filtrado por dueno
            found = await file_store.read(db, user_id or "", file_id)
            if not found:
                raise FileNotFoundError(file_id)
            raw_bytes = found[1]
        else:
            raw_bytes = await FileProvider.fetch_bytes(url)
    except Exception as e:
        logger.error("[document_analyzer] fetch failed file=%s url=%s: %s", title, url, e)
        return file_id, title, url, {"text": "", "engine": None, "page_count": None, "ocr_used": False, "error": f"fetch_failed: {e}"}

    try:
        result = await _file_provider.get_text_and_meta(raw_bytes, title, ocr_allowed=ocr_allowed)
    except Exception as e:
        logger.error("[document_analyzer] extraction failed file=%s: %s", title, e)
        return file_id, title, url, {"text": "", "engine": None, "page_count": None, "ocr_used": False, "error": f"extraction_failed: {e}"}

    await save_extraction(
        db, file_id, url=url, filename=title, engine=result["engine"], text=result["text"],
        page_count=result.get("page_count"), ocr_used=result.get("ocr_used", False),
        error=result.get("error"), user_id=user_id, conversation_id=conversation_id,
    )
    return file_id, title, url, result


def _report_and_register(
    validation_reports: list, session_documents: dict, file_id: str, title: str, url: str | None,
    result: dict,
) -> str | None:
    """Writes the validation_reports/session_documents entries for one file.
    Returns the text to inject into context, or None if unavailable."""
    if result.get("error") == "missing_url":
        validation_reports.append({
            "source": "document", "app": title, "status": "error",
            "message": f"'{title}' no tiene una URL válida.",
        })
        session_documents[file_id] = {"title": title, "status": "error"}
        return None

    if result.get("error") and not result.get("text"):
        blocked_by_plan = result.get("engine") == "vision_blocked_by_plan" or result.get("error") == "ocr_blocked_by_plan"
        message = (
            f"'{title}' necesita OCR para leerse y tu plan actual no lo incluye. Considera actualizar tu plan."
            if blocked_by_plan else
            f"No se pudo extraer contenido legible de '{title}'."
        )
        validation_reports.append({"source": "document", "app": title, "status": "error", "message": message})
        session_documents[file_id] = {"title": title, "url": url, "status": "error", "engine": result.get("engine")}
        return None

    char_count = len(result["text"])
    is_chunked = char_count > _CHUNK_THRESHOLD
    session_documents[file_id] = {
        "title": title, "url": url, "status": "ok",
        "engine": result["engine"], "char_count": char_count,
        "is_chunked": is_chunked,
    }
    logger.info(
        "[document_analyzer] extracted file=%s engine=%s chars=%d ocr_used=%s",
        title, result["engine"], char_count, result.get("ocr_used"),
    )
    return result["text"]


async def _expand_zip(
    db, parent_file_id: str, parent_title: str, zip_bytes: bytes,
    *, ocr_allowed: bool, user_id: str | None, conversation_id: str | None,
    validation_reports: list,
) -> list[tuple[str, str, str | None, dict]]:
    """Expands a ZIP into N sub-results, one per supported member file, going
    through the same cache-or-extract path as _extract_one for each. Never
    raises — full-ZIP rejections (too many members, too large) and per-member
    errors (unsupported extension, read failure) are appended directly to
    validation_reports; only successfully-openable members are returned as
    (sub_file_id, title, url, result_dict) tuples, same shape as _extract_one,
    for the caller to run through _process_extraction_result like any resource."""
    try:
        zf = zipfile.ZipFile(BytesIO(zip_bytes))
        infolist = zf.infolist()
    except Exception as e:
        validation_reports.append({
            "source": "document", "app": parent_title, "status": "error",
            "message": f"'{parent_title}' no es un ZIP válido: {e}",
        })
        return []

    if len(infolist) > _ZIP_MAX_MEMBERS:
        validation_reports.append({
            "source": "document", "app": parent_title, "status": "error",
            "message": f"'{parent_title}' contiene más de {_ZIP_MAX_MEMBERS} archivos, no se pudo procesar.",
        })
        return []

    # Declared size from the local file header — checked before any zf.read()
    # so a zip bomb is rejected without ever materializing its bytes.
    total_uncompressed = sum(zi.file_size for zi in infolist)
    if total_uncompressed > _ZIP_MAX_UNCOMPRESSED_BYTES:
        validation_reports.append({
            "source": "document", "app": parent_title, "status": "error",
            "message": f"'{parent_title}' excede el límite de {_ZIP_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)}MB descomprimido.",
        })
        return []

    results: list[tuple[str, str, str | None, dict]] = []
    for zi in infolist:
        if zi.is_dir():
            continue
        member_name = zi.filename
        base_name = member_name.rsplit("/", 1)[-1]
        if not base_name or base_name.startswith(".") or member_name.startswith("__MACOSX/"):
            continue  # directory markers / macOS junk — skipped silently, not an error

        ext = os.path.splitext(base_name)[1].lower().lstrip(".")
        sub_file_id = f"{parent_file_id}::{member_name}"

        if ext not in _ZIP_ALLOWED_EXTS:
            validation_reports.append({
                "source": "document", "app": parent_title, "status": "error",
                "message": f"'{member_name}' dentro de '{parent_title}': tipo de archivo no soportado, omitido.",
            })
            continue

        cached = await get_cached_extraction(db, sub_file_id)
        if cached is not None:
            await touch_extraction(db, sub_file_id)
            results.append((sub_file_id, base_name, None, {
                "text": cached.get("text", ""), "engine": cached.get("engine"),
                "page_count": cached.get("page_count"), "ocr_used": cached.get("ocr_used", False),
                "error": cached.get("extraction_error"),
            }))
            continue

        try:
            member_bytes = zf.read(zi)
        except Exception as e:
            logger.error("[document_analyzer] zip member read failed member=%s: %s", member_name, e)
            results.append((sub_file_id, base_name, None, {
                "text": "", "engine": None, "page_count": None, "ocr_used": False,
                "error": f"zip_read_failed: {e}",
            }))
            continue

        try:
            result = await _file_provider.get_text_and_meta(member_bytes, base_name, ocr_allowed=ocr_allowed)
        except Exception as e:
            logger.error("[document_analyzer] zip member extraction failed member=%s: %s", member_name, e)
            result = {"text": "", "engine": None, "page_count": None, "ocr_used": False, "error": f"extraction_failed: {e}"}

        await save_extraction(
            db, sub_file_id, url=f"zip://{parent_file_id}/{member_name}", filename=base_name,
            engine=result.get("engine"), text=result.get("text", ""),
            page_count=result.get("page_count"), ocr_used=result.get("ocr_used", False),
            error=result.get("error"), user_id=user_id, conversation_id=conversation_id,
        )
        results.append((sub_file_id, base_name, None, result))

    return results


async def _process_extraction_result(
    db, file_id: str, title: str, url: str | None, result: dict,
    *, validation_reports: list, session_documents: dict, conversation_id: str | None,
    user_id: str | None, context_blocks: list, total_chars: int, requested_ids: list,
) -> int:
    """Common post-processing for a single extraction result (register +
    chunk-or-inline), shared by normal resources, ZIP members, and YouTube
    transcripts — each may call this any number of times per turn, unlike the
    old inline loop body that assumed exactly one result per resource.
    Returns the updated total_chars (the other accumulators are mutated in place)."""
    text = _report_and_register(validation_reports, session_documents, file_id, title, url, result)
    if text is None:
        return total_chars

    is_chunked = len(text) > _CHUNK_THRESHOLD
    if is_chunked and conversation_id:
        num_chunks = await chunk_and_embed(db, file_id, conversation_id, user_id, title, text)
        if num_chunks > 0:
            logger.info("[document_analyzer] chunked file=%s chunks=%d", title, num_chunks)
            requested_ids.append(file_id)
        else:
            is_chunked = False  # Chunking failed — keep as regular doc (truncated below)
            session_documents[file_id]["is_chunked"] = False

    if not is_chunked and total_chars + len(text) <= _TOTAL_CONTEXT_CHAR_CAP:
        context_blocks.append(f"--- {title} ---\n{text[:_SHORT_DOC_CHAR_BUDGET]}")
        total_chars += len(text)
    elif not is_chunked:
        validation_reports.append({
            "source": "document", "app": title, "status": "ok",
            "message": f"'{title}' es muy extenso para incluirse completo este turno.",
        })
    return total_chars


def _extract_user_query(state: ShifuState) -> str:
    """Returns the text of the last human message, or empty string."""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            return msg.content or ""
    return ""


async def _ingest_and_analyze(state: ShifuState) -> dict:
    turn_resources = state.get("turn_resources") or []
    needs_document_context = bool(state.get("needs_document_context"))
    prior_session_documents = state.get("session_documents") or {}
    document_intent = state.get("document_intent")
    document_extraction_hint = state.get("document_extraction_hint") or "generic"

    # YouTube links pasted as plain text never arrive as turn_resources (the
    # WS handler only populates that from uploaded Cloudinary attachments) —
    # detected here via regex so a bare link in the chat still counts as
    # "there's a document to process this turn" for the early-return guard below.
    user_query_text = _extract_user_query(state)
    video_ids = find_youtube_video_ids(user_query_text)[:_YOUTUBE_MAX_PER_TURN]

    if not turn_resources and not needs_document_context and document_intent != "extract_structured" and not video_ids:
        # Nothing new or referenced this turn — clear per-turn context (never
        # inherited by omission) but leave session_documents alone (reducer
        # treats a missing key as "no update", so prior uploads are untouched).
        return {
            "turn_document_context": None,
            "retrieved_document_chunks": None,
            "structured_extraction": None,
        }

    db = mongo_manager.db
    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")
    plan = await _get_user_plan(user_id)
    ocr_allowed = bool(plan.get("ocr_enabled"))

    validation_reports: list[dict] = []
    session_documents: dict[str, dict] = {}
    context_blocks: list[str] = []
    total_chars = 0
    seen_file_ids: set[str] = set()
    # file_ids needing semantic retrieval THIS turn — populated both by newly
    # chunked attachments (so a huge PDF is searchable the instant it's
    # uploaded, not only from the following turn) and by needs_document_context
    # reactivating a previously-chunked document.
    requested_ids: list[str] = []

    # ── Phase 0: YouTube links pasted as plain text ──────────────────────
    for video_id in video_ids:
        file_id = file_id_for_youtube(video_id)
        if file_id in seen_file_ids:
            continue
        seen_file_ids.add(file_id)
        title = f"YouTube: {video_id}"
        url = f"https://youtu.be/{video_id}"

        cached = await get_cached_extraction(db, file_id)
        if cached is not None:
            await touch_extraction(db, file_id)
            result = {
                "text": cached.get("text", ""), "engine": cached.get("engine"),
                "page_count": cached.get("page_count"), "ocr_used": cached.get("ocr_used", False),
                "error": cached.get("extraction_error"),
            }
        else:
            result = fetch_youtube_transcript(video_id)
            await save_extraction(
                db, file_id, url=url, filename=title, engine=result["engine"], text=result["text"],
                page_count=result.get("page_count"), ocr_used=result.get("ocr_used", False),
                error=result.get("error"), user_id=user_id, conversation_id=conversation_id,
            )
        total_chars = await _process_extraction_result(
            db, file_id, title, url, result,
            validation_reports=validation_reports, session_documents=session_documents,
            conversation_id=conversation_id, user_id=user_id,
            context_blocks=context_blocks, total_chars=total_chars, requested_ids=requested_ids,
        )

    # ── Phase 1: Process new attachments ─────────────────────────────────
    for resource in turn_resources:
        resource_title = resource.get("title") or (resource.get("url", "").rsplit("/", 1)[-1] if resource.get("url") else "archivo")
        resource_ext = os.path.splitext(resource_title)[1].lower().lstrip(".")

        if resource_ext == "zip":
            parent_file_id = file_id_for(resource)
            if parent_file_id in seen_file_ids:
                continue
            seen_file_ids.add(parent_file_id)
            zip_url = resource.get("url")
            if not zip_url:
                validation_reports.append({
                    "source": "document", "app": resource_title, "status": "error",
                    "message": f"'{resource_title}' no tiene una URL válida.",
                })
                continue
            try:
                zip_bytes = await FileProvider.fetch_bytes(zip_url)
            except Exception as e:
                logger.error("[document_analyzer] zip fetch failed file=%s url=%s: %s", resource_title, zip_url, e)
                validation_reports.append({
                    "source": "document", "app": resource_title, "status": "error",
                    "message": f"No se pudo descargar '{resource_title}'.",
                })
                continue
            sub_results = await _expand_zip(
                db, parent_file_id, resource_title, zip_bytes,
                ocr_allowed=ocr_allowed, user_id=user_id, conversation_id=conversation_id,
                validation_reports=validation_reports,
            )
            for sub_file_id, sub_title, sub_url, sub_result in sub_results:
                if sub_file_id in seen_file_ids:
                    continue
                seen_file_ids.add(sub_file_id)
                total_chars = await _process_extraction_result(
                    db, sub_file_id, sub_title, sub_url, sub_result,
                    validation_reports=validation_reports, session_documents=session_documents,
                    conversation_id=conversation_id, user_id=user_id,
                    context_blocks=context_blocks, total_chars=total_chars, requested_ids=requested_ids,
                )
            continue

        file_id, title, url, result = await _extract_one(
            db, resource, ocr_allowed=ocr_allowed, user_id=user_id, conversation_id=conversation_id,
        )
        if file_id in seen_file_ids:
            continue
        seen_file_ids.add(file_id)
        total_chars = await _process_extraction_result(
            db, file_id, title, url, result,
            validation_reports=validation_reports, session_documents=session_documents,
            conversation_id=conversation_id, user_id=user_id,
            context_blocks=context_blocks, total_chars=total_chars, requested_ids=requested_ids,
        )

    # ── Phase 2: Reactivate previously-uploaded documents referenced without
    # a new attachment ("compara ese excel con la factura anterior") ────────
    if needs_document_context:
        for file_id, info in prior_session_documents.items():
            if file_id in seen_file_ids or info.get("status") != "ok":
                continue
            if info.get("is_chunked"):
                requested_ids.append(file_id)
            else:
                # Short docs: inline directly from cache.
                cached = await get_cached_extraction(db, file_id)
                if cached and cached.get("text") and total_chars + len(cached["text"]) <= _TOTAL_CONTEXT_CHAR_CAP:
                    await touch_extraction(db, file_id)
                    title = info.get("title") or file_id
                    context_blocks.append(
                        f"--- {title} (referenced from earlier) ---\n{cached['text'][:_SHORT_DOC_CHAR_BUDGET]}"
                    )
                    total_chars += len(cached["text"])

    # ── Phase 2b: Semantic retrieval for any large document collected above ─
    retrieved_document_chunks: list[dict] | None = None
    if requested_ids:
        # Embed the user's current query as the search vector.
        query_text = _extract_user_query(state)
        query_embedding = await embed_text(query_text) if query_text else None

        chunks = await search_document_chunks(
            db, conversation_id, query_embedding or [],
            file_ids=requested_ids, limit=12,
        )
        if chunks:
            retrieved_document_chunks = chunks

    # ── Phase 3: Structured extraction (Fase 4) ──────────────────────────
    structured_extraction: dict | None = None
    extraction_review_pending: dict | None = None
    if document_intent == "extract_structured":
        extraction_text = ""
        extraction_title = ""
        if turn_resources:
            # Use text from the most recently attached document.
            last_resource_info = None
            for res in reversed(turn_resources):
                fid = file_id_for(res)
                if fid in session_documents and session_documents[fid].get("status") == "ok":
                    cached = await get_cached_extraction(db, fid)
                    if cached and cached.get("text"):
                        extraction_text = cached["text"]
                        extraction_title = cached.get("filename") or session_documents[fid].get("title", "")
                        break
        elif needs_document_context:
            # Use the first available short prior doc or first chunk text.
            for fid, info in prior_session_documents.items():
                if info.get("status") != "ok":
                    continue
                cached = await get_cached_extraction(db, fid)
                if cached and cached.get("text"):
                    extraction_text = cached["text"]
                    extraction_title = cached.get("filename") or info.get("title", "")
                    break

        if extraction_text:
            structured_extraction = await extract_structured_data(
                extraction_text, document_extraction_hint, extraction_title,
            )
            if structured_extraction and structured_extraction.get("needs_review") and not structured_extraction.get("error"):
                # Arms the HITL cycle: next turn, document_analyzer_node sees
                # extraction_review_pending set and dispatches straight to
                # _resolve_extraction_review instead of re-ingesting attachments.
                extraction_review_pending = {**structured_extraction, "_full_text": extraction_text}
                logger.info("[document_analyzer] extraction needs review file=%s", extraction_title)
            elif structured_extraction:
                logger.info("[document_analyzer] extraction ok file=%s", extraction_title)

    return {
        "validation_reports": validation_reports,
        "session_documents": session_documents,
        "turn_document_context": "\n\n".join(context_blocks) if context_blocks else None,
        "retrieved_document_chunks": retrieved_document_chunks,
        "structured_extraction": structured_extraction,
        "extraction_review_pending": extraction_review_pending,
    }


async def _resolve_extraction_review(state: ShifuState) -> dict:
    """Handles the HITL follow-up turn when extraction_review_pending is set.

    The user has been shown uncertain fields by the responder. We check if
    their latest message resolves the uncertainty (confirms/corrects fields)
    by calling the LLM with the pending extraction + user feedback."""

    pending = state.get("extraction_review_pending")
    if not pending:
        return {"extraction_review_pending": None, "structured_extraction": None}

    user_feedback = _extract_user_query(state)
    if not user_feedback:
        return {"extraction_review_pending": None, "structured_extraction": None}

    pending_hint = pending.get("hint", "generic")
    pending_filename = pending.get("filename", "")
    pending_text = pending.get("_full_text", "")
    previous_extraction = {k: v for k, v in pending.items() if not k.startswith("_")}

    try:
        client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": (
                    "Eres un asistente que resuelve incertidumbre en extracción de datos. "
                    "El usuario está revisando campos que marcaste como inciertos. "
                    "Recibes: (1) la extracción previa, (2) el texto original del documento, "
                    "(3) el mensaje del usuario. "
                    "Devuelve el JSON completo de extracción con los campos corregidos según "
                    "la indicación del usuario. Responde SOLO con el JSON."
                )},
                {"role": "user", "content": (
                    f"Extracción previa:\n{json.dumps(previous_extraction, ensure_ascii=False)}\n\n"
                    f"Texto del documento:\n{pending_text[:20_000]}\n\n"
                    f"Feedback del usuario:\n{user_feedback}"
                )},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = __import__("re").sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
        resolved = json.loads(raw)
    except Exception as exc:
        logger.error("[document_analyzer] review resolution failed: %s", exc)
        return {"extraction_review_pending": None, "structured_extraction": None}

    if not isinstance(resolved, dict):
        return {"extraction_review_pending": None, "structured_extraction": None}

    resolved["hint"] = pending_hint
    resolved["filename"] = pending_filename
    resolved["needs_review"] = False  # Resolved
    resolved["validation_notes"] = []

    if pending_hint == "invoice":
        notes = _check_invoice_totals(resolved)
        if notes:
            resolved["validation_notes"] = notes

    return {
        "extraction_review_pending": None,
        "structured_extraction": resolved,
    }
