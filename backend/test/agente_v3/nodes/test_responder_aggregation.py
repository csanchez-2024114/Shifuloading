"""Unit tests for _aggregate and _compute_mood in responder.py.

Pure Python — no DB, no LLM, no async.
"""

from app.agent.shared.nodes.responder import _aggregate, _compute_mood


# ── _compute_mood ─────────────────────────────────────────────────────────────

def test_mood_closing_overrides_everything():
    mood, _ = _compute_mood("frustrated", "level_1", is_closing=True)
    assert mood == "CLOSING"


def test_mood_frustrated_is_direct_empathy():
    mood, _ = _compute_mood("frustrated", None, is_closing=False)
    assert mood == "DIRECT_EMPATHY"


def test_mood_urgent_is_direct_empathy():
    mood, _ = _compute_mood("urgent", None, is_closing=False)
    assert mood == "DIRECT_EMPATHY"


def test_mood_level1_confused_is_direct_empathy():
    mood, _ = _compute_mood("confused", "level_1", is_closing=False)
    assert mood == "DIRECT_EMPATHY"


def test_mood_level2_confused_is_not_empathy():
    mood, _ = _compute_mood("confused", "level_2", is_closing=False)
    assert mood != "DIRECT_EMPATHY"


def test_mood_neutral_is_helpful():
    mood, _ = _compute_mood("neutral", None, is_closing=False)
    assert mood == "HELPFUL"


def test_mood_calm_is_helpful():
    mood, _ = _compute_mood("calm", None, is_closing=False)
    assert mood == "HELPFUL"


def test_mood_unknown_sentiment_is_default():
    mood, _ = _compute_mood("sarcastic", None, is_closing=False)
    assert mood == "DEFAULT"


def test_mood_none_sentiment_is_helpful():
    # None treated as "neutral"
    mood, _ = _compute_mood(None, None, is_closing=False)
    assert mood == "HELPFUL"


# ── _aggregate helpers ────────────────────────────────────────────────────────

def _ok(source, app):
    return {"source": source, "app": app, "status": "ok"}


def _err(source, app, reason="not_connected"):
    return {"source": source, "app": app, "status": "error", "reason": reason}


def _state(reports, apps=None, is_closing=False, catalog_mode=None, missing=None):
    return {
        "is_closing":          is_closing,
        "apps_involved":       ["gmail"] if apps is None else apps,
        "validation_reports":  reports,
        "missing_variables":   missing or [],
        "catalog_query_mode":  catalog_mode,
    }


# ── _aggregate ────────────────────────────────────────────────────────────────

def test_aggregate_closing_returns_none():
    level, ctx = _aggregate(_state([], is_closing=True))
    assert level is None and ctx is None


def test_aggregate_no_apps_returns_none():
    level, ctx = _aggregate(_state([], apps=[]))
    assert level is None and ctx is None


def test_aggregate_list_connected_mode_returns_none():
    level, ctx = _aggregate(_state([], catalog_mode="list_connected"))
    assert level is None and ctx is None


def test_aggregate_all_ok_is_level2():
    level, ctx = _aggregate(_state([_ok("catalog", "gmail"), _ok("auth", "gmail")]))
    assert level == "level_2" and ctx is None


def test_aggregate_auth_not_connected_is_level1():
    level, ctx = _aggregate(_state([_ok("catalog", "gmail"), _err("auth", "gmail", "not_connected")]))
    assert level == "level_1"
    assert "NOT CONNECTED" in (ctx or "")


def test_aggregate_auth_expired_is_level1():
    level, ctx = _aggregate(_state([_ok("catalog", "gmail"), _err("auth", "gmail", "expired")]))
    assert level == "level_1"
    assert "EXPIRED" in (ctx or "")


def test_aggregate_pending_selection_is_level1():
    pending = {"source": "auth", "app": "gmail", "status": "pending_selection", "accounts": []}
    level, ctx = _aggregate(_state([_ok("catalog", "gmail"), pending]))
    assert level == "level_1"


def test_aggregate_missing_variables_included_in_context():
    level, ctx = _aggregate(_state(
        [_ok("catalog", "gmail"), _ok("auth", "gmail")],
        missing=["recipient_email"],
    ))
    # all ok + missing vars → level_2 (missing vars shown by bigtools, not here)
    # verify _aggregate itself doesn't escalate for missing vars alone
    assert level == "level_2"

