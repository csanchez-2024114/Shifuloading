"""
observation_verifiers — Tool-specific verifiers for workflow step observation.

Used by WorkflowExecutor after each step to check if the expected outcome occurred.
Unregistered tools → status=None (unknown, not failed).
"""

from abc import ABC, abstractmethod


class ObservationResult:
    __slots__ = ("expected", "actual", "status", "tool")

    def __init__(self, expected: str, actual: str, status: bool | None, tool: str):
        self.expected = expected
        self.actual = actual
        self.status = status
        self.tool = tool


class BaseVerifier(ABC):
    @abstractmethod
    def verify(self, tool_response: dict, intent_type: str, requested_action: str) -> ObservationResult:
        ...


class GmailVerifier(BaseVerifier):
    def verify(self, tool_response: dict, intent_type: str, requested_action: str) -> ObservationResult:
        if "send" in (intent_type or "") or "send" in (requested_action or "").lower():
            success = bool(tool_response.get("message_id") or tool_response.get("id"))
            return ObservationResult(
                expected="email sent",
                actual="message_id present" if success else "no message_id in response",
                status=success,
                tool="gmail",
            )
        return ObservationResult(expected="gmail action", actual=str(tool_response)[:100], status=None, tool="gmail")


class GoogleDocsVerifier(BaseVerifier):
    def verify(self, tool_response: dict, intent_type: str, requested_action: str) -> ObservationResult:
        success = bool(tool_response.get("documentId") or tool_response.get("doc_id") or tool_response.get("id"))
        return ObservationResult(
            expected="document created",
            actual="doc_id present" if success else "no doc_id in response",
            status=success,
            tool="google_docs",
        )


class GoogleCalendarVerifier(BaseVerifier):
    def verify(self, tool_response: dict, intent_type: str, requested_action: str) -> ObservationResult:
        success = bool(tool_response.get("id") or tool_response.get("event_id"))
        return ObservationResult(
            expected="event scheduled",
            actual="event_id present" if success else "no event_id in response",
            status=success,
            tool="google_calendar",
        )


VERIFIERS: dict[str, BaseVerifier] = {
    "gmail": GmailVerifier(),
    "google_docs": GoogleDocsVerifier(),
    "google_calendar": GoogleCalendarVerifier(),
}
