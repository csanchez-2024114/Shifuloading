"""
eval/judge.py — LLM judge that evaluates whether a Shifu response satisfies
                the expected behaviors defined in a test case.

Inputs:
  - message: the user message sent to Shifu
  - expected_behavior: list of behavior tags (e.g. ["describe_capabilities", "not_require_connection"])
                       Tags prefixed with "not_" are FORBIDDEN behaviors.
  - actual_response: the text reply from Shifu

Output:
  JudgeResult(passed: bool, score: int 1-10, reason: str)

Uses OpenAI gpt-4o-mini by default. On JSON parse failure returns passed=False, score=0.
"""

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an evaluation judge for an AI assistant called Shifu.

You receive:
1. The user message sent to Shifu.
2. A list of expected behavior tags:
   - Tags WITHOUT a "not_" prefix = behaviors that MUST be present.
   - Tags WITH a "not_" prefix = behaviors that must NOT be present (forbidden).
3. Shifu's actual response.

Your task: determine whether the response satisfies ALL required behaviors and violates NONE of the forbidden behaviors.

Return ONLY valid JSON with this exact structure:
{"passed": true|false, "score": <integer 1-10>, "reason": "<one concise sentence>"}

Scoring guide:
  10 = perfect response, all expectations met with high quality
  7-9 = passes, minor quality issues
  4-6 = partially meets expectations
  1-3 = mostly fails
  0 = judge error (do not use)

Examples of tag semantics:
  "describe_capabilities"       → response explains what Shifu can do
  "not_require_connection"      → response must NOT ask user to connect an app they didn't mention
  "offer_connection"            → response offers to connect an app (shows connect flow/button hint)
  "intent_execute_send"         → response treats the request as a send action
  "not_ask_to_connect_gmail"    → response must NOT ask user to connect Gmail (it is already connected)
  "clarification_requested"     → response asks the user to clarify their intent
  "recall_name_correctly"       → response uses the name the user provided earlier in the conversation
  "propose_workflow"            → response proposes an automation workflow
  "confirm_before_delete"       → response asks for confirmation before deleting
"""

_USER_TEMPLATE = """\
User message: {message}

Expected behaviors: {behaviors}

Shifu's response:
{response}
"""


@dataclass
class JudgeResult:
    passed: bool
    score: int
    reason: str


async def judge(
    message: str,
    expected_behavior: list[str],
    actual_response: str,
    model: str = "gpt-4o-mini",
) -> JudgeResult:
    client = AsyncOpenAI()

    behaviors_formatted = ", ".join(expected_behavior)
    user_content = _USER_TEMPLATE.format(
        message=message,
        behaviors=behaviors_formatted,
        response=actual_response[:3000],
    )

    try:
        completion = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or ""
        data = json.loads(raw)
        return JudgeResult(
            passed=bool(data.get("passed", False)),
            score=int(data.get("score", 0)),
            reason=str(data.get("reason", "")),
        )
    except json.JSONDecodeError as exc:
        logger.warning("[judge] JSON parse error: %s | raw=%r", exc, raw[:200])
        return JudgeResult(passed=False, score=0, reason=f"Judge parse error: {raw[:100]}")
    except Exception as exc:
        logger.error("[judge] Unexpected error: %s", exc, exc_info=True)
        return JudgeResult(passed=False, score=0, reason=f"Judge error: {exc}")
