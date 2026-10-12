"""
base_bigtools — Base class standard for BigTool implementations.

Provides:
  - TOOL_TIMEOUT_SECONDS: configurable per-call timeout (env: TOOL_TIMEOUT_SECONDS, default 30)
  - MAX_RETRIES: 1-retry with exponential backoff for HTTP 429 / 503 transient errors
  - call_with_retry(): async wrapper — use in new tool implementations

Circuit breaker and tool_outcome_log are enforced at the WorkflowExecutor._call_tool()
level, so ALL tools (existing and new) get this behavior automatically without requiring
inheritance. Inheritance from BigToolBase is optional for new tools but recommended.

Usage for new tools:
    from app.agent.shared.tools.providers.base_bigtools import BigToolBase

    class MyNewTool(BigToolBase):
        async def invoke(self, **kwargs) -> str:
            return await self.call_with_retry(self._my_api_call, **kwargs)

        async def _my_api_call(self, **kwargs) -> str:
            ...
"""

import asyncio
import logging
import os
from typing import Any, Callable, Coroutine, Dict

logger = logging.getLogger(__name__)

_TOOL_TIMEOUT_SECONDS = int(os.getenv("TOOL_TIMEOUT_SECONDS", "30"))
_MAX_RETRIES = int(os.getenv("TOOL_MAX_RETRIES", "1"))
_RETRY_DELAY_SECONDS = float(os.getenv("TOOL_RETRY_DELAY_SECONDS", "2.0"))

# HTTP status codes considered transient (safe to retry)
_TRANSIENT_STATUS_CODES = frozenset({429, 503, 502, 504})


def _is_transient(exc: Exception) -> bool:
    """Returns True if the error is a transient HTTP error that should be retried."""
    msg = str(exc).lower()
    for code in _TRANSIENT_STATUS_CODES:
        if str(code) in msg:
            return True
    transient_keywords = ("rate limit", "too many requests", "service unavailable",
                          "gateway timeout", "temporarily", "retry after", "quota exceeded")
    return any(kw in msg for kw in transient_keywords)


class BigToolBase:
    """
    Base class for BigTool implementations.

    Subclass this for new tools. Existing tools receive timeout + circuit breaker
    + outcome logging automatically via WorkflowExecutor._call_tool().
    """

    TIMEOUT_SECONDS: int = _TOOL_TIMEOUT_SECONDS
    MAX_RETRIES: int = _MAX_RETRIES
    RETRY_DELAY: float = _RETRY_DELAY_SECONDS

    async def call_with_retry(
        self,
        fn: Callable[..., Coroutine[Any, Any, str]],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """
        Calls an async function with:
        - Per-call timeout (TOOL_TIMEOUT_SECONDS)
        - 1-retry with 2× exponential backoff for transient HTTP errors (429/503)

        Raises the original exception after all retries are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await asyncio.wait_for(
                    fn(*args, **kwargs),
                    timeout=self.TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError as exc:
                raise ValueError(
                    f"[{self.__class__.__name__}] Tool call timed out after {self.TIMEOUT_SECONDS}s."
                ) from exc
            except Exception as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES and _is_transient(exc):
                    wait = self.RETRY_DELAY * (2 ** attempt)
                    logger.info(
                        "[%s] Transient error on attempt %d, retrying in %.1fs: %s",
                        self.__class__.__name__, attempt + 1, wait, exc,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise
        raise last_exc  # type: ignore[misc]

    async def invoke_dry(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Returns a mock response for dry-run simulation without calling external APIs.
        Used by agente_v3 dry_run_tester to validate workflows before publishing.
        Subclasses can override _dry_run_mock() for richer, tool-specific fake data.
        """
        mock = self._dry_run_mock(**kwargs)
        logger.info(
            "[%s] dry_run invoked args=%s",
            self.__class__.__name__, list(kwargs.keys()),
        )
        return {
            "dry_run": True,
            "tool": self.__class__.__name__,
            "args": kwargs,
            "mock_result": mock,
            "status": "simulated_success",
        }

    def _dry_run_mock(self, **kwargs: Any) -> Any:
        """Override in subclasses to return tool-specific mock data."""
        return (
            f"[DRY RUN] {self.__class__.__name__} would execute "
            f"with args: {list(kwargs.keys())}"
        )

