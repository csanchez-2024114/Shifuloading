"""
Shared fixtures for agente_v3 tests.

FakeDB/FakeCollection/FakeCursor replace motor (async MongoDB) without
touching the real database. All equality-filter keys are matched; operator
filters (e.g. $in) are ignored and all docs are returned.
"""

import pytest
from langchain_core.messages import HumanMessage
from unittest.mock import MagicMock


# ── Fake async MongoDB stack ──────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, docs, filter=None):
        if filter:
            out = []
            for doc in docs:
                if all(
                    doc.get(k) == v
                    for k, v in filter.items()
                    if not isinstance(v, dict)
                ):
                    out.append(doc)
            self._docs = out
        else:
            self._docs = list(docs)

    async def to_list(self, length=None):
        return list(self._docs)


class FakeCollection:
    def __init__(self, docs=None):
        self._docs = list(docs or [])

    def find(self, filter=None, projection=None):
        return FakeCursor(self._docs, filter=filter)

    async def find_one(self, filter=None, projection=None):
        cursor = FakeCursor(self._docs, filter=filter)
        docs = await cursor.to_list()
        return docs[0] if docs else None

    async def insert_one(self, doc):
        return MagicMock(inserted_id="fake_id")

    async def update_one(self, *a, **kw):
        return MagicMock(modified_count=1)


class FakeDB:
    """
    Usage: FakeDB(catalog_apps=[doc1, doc2], user_connected_accounts=[doc3])
    Any collection not listed returns an empty FakeCollection.
    """
    def __init__(self, **collections):
        self._cols = {k: FakeCollection(v) for k, v in collections.items()}

    def __getitem__(self, name):
        return self._cols.get(name, FakeCollection([]))


# ── Common fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def base_state():
    return {
        "messages":                [HumanMessage("conectar gmail con sheets")],
        "user_id":                 "user_test_001",
        "conversation_id":         "conv_001",
        "apps_involved":           [],
        "validation_reports":      [],
        "selected_accounts":       None,
        "available_accounts":      None,
        "catalog_query_mode":      None,
        "is_closing":              False,
        "structured_prompt":       None,
        "effort_level":            "medio",
        "model_name":              "gpt-4o-mini",
        "current_time_utc":        "2026-06-16T00:00:00Z",
        "user_timezone":           None,
        "user_location":           None,
        "user_country_code":       None,
        "user_preferences_context": None,
        "missing_variables":       [],
    }
