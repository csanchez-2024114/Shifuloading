"""
AI Processing BigTools — LLM-powered transformation steps for workflows.

These tools act as intelligent middleware between integration steps:
  emails → ai_summarize → insert into Google Doc
  spreadsheet rows → ai_extract → classify → send to Slack
  user data → ai_generate → send email

All tools accept plain text or JSON string inputs (typically {{step_N}} or {{step_N.field}})
and return a string result that can be chained into subsequent steps.
"""
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Type

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MODEL = os.getenv("V3_CHAT_MODEL", "gpt-4o-mini")
_MAX_INPUT = 8000  # chars — keep LLM calls cheap


@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


# ── Input schemas ──────────────────────────────────────────────────────────────

class AISummarizeInput(BaseModel):
    text: str = Field(
        ...,
        description="Text or JSON to summarize. Typically {{step_N}} or {{step_N.field}}.",
    )
    language: str = Field(default="es", description="Output language: 'es' or 'en'")
    max_words: int = Field(default=150, description="Max words in the summary")
    focus: str = Field(
        default="",
        description="What to focus on (e.g. 'key decisions', 'action items', 'amounts')",
    )


class AITransformInput(BaseModel):
    text: str = Field(
        ...,
        description="Input text or data to transform. Typically {{step_N}} or {{step_N.field}}.",
    )
    instruction: str = Field(
        ...,
        description=(
            "Plain-language transformation instruction. "
            "Examples: 'Translate to English', 'Format as a bullet list', "
            "'Extract only the names and emails', 'Rewrite in a formal tone'."
        ),
    )
    language: str = Field(default="es", description="Output language: 'es' or 'en'")


class AIExtractInput(BaseModel):
    text: str = Field(
        ...,
        description="Source text to extract structured data from. Typically {{step_N}}.",
    )
    fields: str = Field(
        default="",
        description=(
            "Comma-separated field names to extract as JSON. "
            "Example: 'name, email, phone, date, amount'. "
            "If empty, extracts all relevant structured data automatically."
        ),
    )


class AIClassifyInput(BaseModel):
    text: str = Field(..., description="Text to classify.")
    categories: str = Field(
        ...,
        description=(
            "Comma-separated categories. "
            "Example: 'urgent, normal, spam' or 'positive, negative, neutral'"
        ),
    )


class AIGenerateInput(BaseModel):
    instruction: str = Field(
        ...,
        description=(
            "What to generate. "
            "Example: 'Write a professional follow-up email', "
            "'Create a weekly report summary', 'Draft a Slack message'"
        ),
    )
    context: str = Field(
        default="",
        description=(
            "Data or context to base the generation on. "
            "Typically {{step_N}} — the output of a previous step."
        ),
    )
    language: str = Field(default="es", description="Output language: 'es' or 'en'")
    format: str = Field(
        default="text",
        description="Output format: 'text', 'markdown', 'html', 'json'",
    )


class AIFilterInput(BaseModel):
    items: str = Field(
        ...,
        description=(
            "JSON array of items to filter. Typically {{step_N}} from a list/search step."
        ),
    )
    criteria: str = Field(
        ...,
        description=(
            "Filter criteria in plain language. "
            "Examples: 'only items from the last 24 hours', "
            "'only emails where subject contains invoice', "
            "'only rows where amount > 100'"
        ),
    )


class AIDecideInput(BaseModel):
    context: str = Field(
        ...,
        description="Data or situation to reason about. Typically {{step_N}}.",
    )
    question: str = Field(
        ...,
        description=(
            "Yes/no question for the AI to answer. "
            "Example: 'Does this email require urgent attention?', "
            "'Is this amount above the monthly budget?'"
        ),
    )


# ── Tool factory ───────────────────────────────────────────────────────────────

def get_ai_bigtools(user_email: str = "", **kwargs) -> List[BigTool]:
    """AI processing tools — no auth required, always available."""

    def _llm(temperature: float = 0.0) -> ChatOpenAI:
        return ChatOpenAI(model=_MODEL, temperature=temperature)

    async def _summarize(
        text: str, language: str = "es", max_words: int = 150, focus: str = ""
    ) -> str:
        focus_clause = f" Focus specifically on: {focus}." if focus else ""
        prompt = (
            f"Summarize the following in {language} in at most {max_words} words.{focus_clause} "
            "Be concise and factual. Return only the summary, no preamble.\n\n"
            f"Content:\n{text[:_MAX_INPUT]}"
        )
        result = await _llm().ainvoke(prompt)
        return result.content.strip()

    async def _transform(text: str, instruction: str, language: str = "es") -> str:
        prompt = (
            f"Instruction: {instruction}\n"
            f"Respond in {language}. Return only the result, no explanation.\n\n"
            f"Input:\n{text[:_MAX_INPUT]}"
        )
        result = await _llm(0.2).ainvoke(prompt)
        return result.content.strip()

    async def _extract(text: str, fields: str = "") -> str:
        field_list = [f.strip() for f in (fields or "").split(",") if f.strip()]
        if field_list:
            target = (
                f"Extract the following fields from the text and return a JSON object: "
                f"{', '.join(field_list)}.\n"
                "If a field is not found, use null."
            )
        else:
            target = (
                "Extract all relevant structured data from the text (names, emails, dates, "
                "amounts, companies, subjects, and any other useful fields) and return a JSON object."
            )
        prompt = (
            f"{target}\n"
            "Return ONLY valid JSON — no markdown, no explanation.\n\n"
            f"Text:\n{text[:_MAX_INPUT]}"
        )
        result = await _llm().ainvoke(prompt)
        raw = result.content.strip().strip("```json").strip("```").strip()
        try:
            json.loads(raw)
            return raw
        except Exception:
            return json.dumps({f: None for f in field_list} if field_list else {})

    async def _classify(text: str, categories: str) -> str:
        cats = [c.strip() for c in categories.split(",") if c.strip()]
        prompt = (
            f"Classify the following text into exactly one of these categories: {', '.join(cats)}.\n"
            "Return ONLY the category name, nothing else.\n\n"
            f"Text:\n{text[:4000]}"
        )
        result = await _llm().ainvoke(prompt)
        label = result.content.strip()
        for cat in cats:
            if cat.lower() in label.lower():
                return cat
        return cats[0]

    async def _generate(
        instruction: str, context: str = "", language: str = "es", format: str = "text"
    ) -> str:
        format_note = {
            "markdown": "Format the response in Markdown.",
            "html": "Format the response in clean HTML (no full-page wrapper).",
            "json": "Return a valid JSON object or array. No markdown, no explanation.",
            "text": "Return plain text only.",
        }.get(format, "Return plain text only.")
        context_block = f"\n\nContext / data to use:\n{context[:6000]}" if context else ""
        prompt = (
            f"Task: {instruction}\n"
            f"Language: {language}\n"
            f"{format_note}"
            f"{context_block}"
        )
        result = await _llm(0.5).ainvoke(prompt)
        return result.content.strip()

    async def _filter_items(items: str, criteria: str) -> str:
        prompt = (
            f"Filter the following JSON array keeping ONLY items that match: {criteria}.\n"
            "Return ONLY the filtered JSON array. No explanation, no markdown.\n\n"
            f"Array:\n{items[:_MAX_INPUT]}"
        )
        result = await _llm().ainvoke(prompt)
        raw = result.content.strip().strip("```json").strip("```").strip()
        try:
            json.loads(raw)
            return raw
        except Exception:
            logger.warning("[AI BigTools] ai_filter returned invalid JSON, returning empty array")
            return "[]"

    async def _decide(context: str, question: str) -> str:
        prompt = (
            f"Based on the following context, answer this yes/no question: {question}\n"
            "Return a JSON object with keys: 'answer' (true or false) and 'reason' (one sentence).\n"
            "Return ONLY valid JSON, no markdown.\n\n"
            f"Context:\n{context[:_MAX_INPUT]}"
        )
        result = await _llm().ainvoke(prompt)
        raw = result.content.strip().strip("```json").strip("```").strip()
        try:
            json.loads(raw)
            return raw
        except Exception:
            return json.dumps({"answer": False, "reason": "Could not evaluate."})

    return [
        BigTool(
            name="ai_summarize",
            description=(
                "Summarizes text or data from a previous step using AI. "
                "Use to condense email content, long reports, or search results "
                "before writing them to Docs, Sheets, or Slides."
            ),
            tool=_summarize,
            args_schema=AISummarizeInput,
        ),
        BigTool(
            name="ai_transform",
            description=(
                "Transforms text following a plain-language instruction. "
                "Use to reformat, translate, rewrite, extract, or restructure "
                "content between workflow steps."
            ),
            tool=_transform,
            args_schema=AITransformInput,
        ),
        BigTool(
            name="ai_extract",
            description=(
                "Extracts structured data as JSON from unstructured text. "
                "Use to pull names, emails, dates, amounts, or any specific fields "
                "from raw email content, documents, or search results."
            ),
            tool=_extract,
            args_schema=AIExtractInput,
        ),
        BigTool(
            name="ai_classify",
            description=(
                "Classifies text into one of the provided categories. "
                "Use to tag emails as urgent/normal, sentiment as positive/negative, "
                "or any custom taxonomy."
            ),
            tool=_classify,
            args_schema=AIClassifyInput,
        ),
        BigTool(
            name="ai_generate",
            description=(
                "Generates content (email body, report, summary, social post) "
                "based on an instruction and optional context data from previous steps. "
                "Use when a step needs to CREATE text, not just pass data through."
            ),
            tool=_generate,
            args_schema=AIGenerateInput,
        ),
        BigTool(
            name="ai_filter",
            description=(
                "Filters a JSON array from a previous step keeping only items "
                "that match plain-language criteria. "
                "Use before a foreach step to process only relevant items "
                "(e.g. 'only unread emails', 'only rows where status is pending')."
            ),
            tool=_filter_items,
            args_schema=AIFilterInput,
        ),
        BigTool(
            name="ai_decide",
            description=(
                "Asks the AI a yes/no question about data from a previous step. "
                "Returns JSON {answer: true/false, reason: '...'}. "
                "Use as the source for a condition step that branches the workflow."
            ),
            tool=_decide,
            args_schema=AIDecideInput,
        ),
    ]
