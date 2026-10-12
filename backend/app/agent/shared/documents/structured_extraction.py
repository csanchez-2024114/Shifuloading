"""
structured_extraction — agente_v3

Extracts structured data from documents when the user explicitly requests it
(document_intent == "extract_structured" with extraction_hint:
"invoice" | "contract" | "generic").

Uses gpt-4o-mini to produce a typed JSON result, then cross-checks invoice
totals (sum line items vs stated total). The extraction result is returned
as structured_extraction in ShifuState so the responder can present it to the
user; low-confidence fields trigger HITL via extraction_review_pending.
"""

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from config import Config

logger = logging.getLogger(__name__)

_INVOICE_SYSTEM_PROMPT = """Eres un extractor de datos de facturas. Analiza el texto del documento y extrae
los siguientes campos en JSON. Si un campo no es visible o no aplica, usa null.
NO inventes valores.

Campos a extraer:
  vendor_name          — nombre del emisor/proveedor
  vendor_tax_id        — RUT/NIT/CIF del emisor (si visible)
  client_name          — nombre del cliente/receptor
  client_tax_id        — RUT/NIT/CIF del cliente (si visible)
  invoice_number       — número de factura o folio
  invoice_date         — fecha de emisión (formato YYYY-MM-DD)
  due_date             — fecha de vencimiento (formato YYYY-MM-DD, null si no visible)
  currency             — código ISO de moneda (CLP, USD, EUR, etc.)
  subtotal             — monto neto antes de impuestos (número)
  tax_amount           — total de impuestos (número, null si no visible)
  tax_rate             — tasa de impuesto aplicada (ej. 0.19 para 19%, null si no visible)
  discount             — descuento si aplica (número, null si no)
  total                — monto total de la factura (número)
  line_items           — array de objetos {description, quantity, unit_price, total}
  notes                — texto de notas/observaciones (string, null si no hay)
  uncertain_fields     — array de nombres de campos que no pudiste extraer con certeza
  needs_review         — true si hay campos que una persona debe verificar

Responde SOLO con el JSON, sin markdown ni texto adicional."""

_CONTRACT_SYSTEM_PROMPT = """Eres un extractor de datos de contratos. Analiza el texto del documento y extrae
los siguientes campos en JSON. Si un campo no es visible o no aplica, usa null.
NO inventes valores.

Campos a extraer:
  contract_title       — título o nombre del contrato
  parties              — array de {name, role} (partes firmantes)
  effective_date       — fecha de inicio (YYYY-MM-DD)
  expiration_date      — fecha de término (YYYY-MM-DD, null si indefinido)
  renewal_terms        — descripción de renovación automática o manual
  payment_terms        — condiciones de pago (ej. "30 días")
  jurisdiction         — ley aplicable / tribunal competente
  key_clauses          — array de {title, summary} cláusulas importantes
  total_value          — monto total del contrato (número, null si no visible)
  currency             — código ISO de moneda
  signatory_names      — array de nombres de quienes firman
  uncertain_fields     — array de nombres de campos inciertos
  needs_review         — true si hay campos que verificar manualmente

Responde SOLO con el JSON, sin markdown ni texto adicional."""

_GENERIC_SYSTEM_PROMPT = """Eres un extractor de datos genérico. Analiza el texto del documento y extrae
la información importante en formato estructurado. Si un campo no aplica, usa null.
NO inventes valores.

Campos a extraer:
  document_title       — título o asunto del documento
  document_type        — tipo de documento detectado (reporte, carta, formulario, etc.)
  date                 — fecha principal del documento (YYYY-MM-DD, null si no hay)
  key_values           — array de {field, value} con los datos numéricos o valores clave
  summary              — resumen de 1-3 oraciones del contenido
  people_mentioned     — array de nombres de personas mencionadas
  uncertain_fields     — array de nombres de campos inciertos
  needs_review         — true si hay campos que verificar manualmente

Responde SOLO con el JSON, sin markdown ni texto adicional."""


def _check_invoice_totals(extraction: dict) -> list[str]:
    """Cross-checks line-item totals against the stated total. Returns a list
    of discrepancy messages (empty = all consistent)."""
    issues: list[str] = []
    line_items = extraction.get("line_items") or []
    stated_total = extraction.get("total")

    if line_items and stated_total is not None:
        try:
            calculated_total = sum(
                float(item.get("total", 0) or 0) for item in line_items
            )
            diff = abs(calculated_total - float(stated_total))
            if diff > 0.01:
                issues.append(
                    f"La suma de line items ({calculated_total:.2f}) no coincide "
                    f"con el total declarado ({float(stated_total):.2f})"
                )
        except (ValueError, TypeError):
            issues.append("No se pudieron verificar los totales (valores no numéricos)")

    subtotal = extraction.get("subtotal")
    tax_amount = extraction.get("tax_amount")
    if subtotal is not None and tax_amount is not None and stated_total is not None:
        try:
            implied_total = float(subtotal) + float(tax_amount)
            diff2 = abs(implied_total - float(stated_total))
            if diff2 > 0.01:
                issues.append(
                    f"subtotal + tax ({implied_total:.2f}) no coincide con total ({float(stated_total):.2f})"
                )
        except (ValueError, TypeError):
            pass

    return issues


async def extract_structured_data(
    text: str, hint: str, filename: str, openai_api_key: str | None = None,
) -> dict[str, Any]:
    """Sends document text to gpt-4o-mini with a schema prompt matching the
    extraction hint (invoice | contract | generic). Returns the parsed JSON
    dict with an extra 'validation_notes' field for cross-check results."""
    if not text or not text.strip():
        return {"error": "No text to extract from", "needs_review": False}

    system_prompt = {
        "invoice": _INVOICE_SYSTEM_PROMPT,
        "contract": _CONTRACT_SYSTEM_PROMPT,
        "generic": _GENERIC_SYSTEM_PROMPT,
    }.get(hint, _GENERIC_SYSTEM_PROMPT)

    try:
        client = AsyncOpenAI(api_key=openai_api_key or Config.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    f"Documento: {filename}\n\n{text[:40_000]}"
                )},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
        extraction = json.loads(raw)
    except Exception as exc:
        logger.error("[structured_extraction] LLM call failed file=%s hint=%s: %s", filename, hint, exc)
        return {"error": f"Extraction failed: {exc}", "needs_review": False, "hint": hint}

    if not isinstance(extraction, dict):
        return {"error": "LLM returned non-object", "needs_review": False, "hint": hint}

    extraction["hint"] = hint
    extraction["filename"] = filename

    validation_notes: list[str] = []
    if hint == "invoice":
        validation_notes = _check_invoice_totals(extraction)
        if validation_notes:
            extraction.setdefault("uncertain_fields", []).append("total (cross-check failed)")

    needs_review = extraction.get("needs_review", False) or bool(validation_notes)
    extraction["needs_review"] = needs_review
    extraction["validation_notes"] = validation_notes

    return extraction
