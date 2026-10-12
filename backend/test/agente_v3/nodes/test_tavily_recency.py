"""Ventana de fechas de tavily_searcher: que filtro manda a Tavily y que dice `research_freshness`."""
import pytest

from app.agent.shared.nodes import tavily_searcher as ts

HIT = {"answer": "", "results": [{"title": "T", "url": "https://x.test/a", "content": "c",
                                  "published_date": "Sun, 11 Oct 2026 10:00:00 GMT"}]}


@pytest.fixture
def calls(monkeypatch):
    made = []

    def fake(empty_for=()):
        class Search:
            def __init__(self, **kw):
                self.kw = kw

            async def ainvoke(self, _):
                made.append(self.kw)
                return {"results": []} if self.kw.get("time_range") in empty_for else HIT
        monkeypatch.setattr(ts, "TavilySearch", Search)
        return made
    monkeypatch.setattr(ts, "_TAVILY_API_KEY", "k")
    return fake


def _state(**kw):
    return {"needs_external_info": True, "optimized_search_query": "q", "effort_level": "low",
            "current_time_utc": "2026-10-11T19:00:00Z", **kw}


async def test_window_and_topic_go_to_tavily(calls):
    made = calls()
    out = await ts.tavily_searcher_node(_state(search_recency="day", search_topic="news"))
    assert made[0]["time_range"] == "day" and made[0]["topic"] == "news"
    assert "last day" in out["research_freshness"] and "2026-10-11" in out["research_freshness"]
    assert out["retrieved_sources"][0]["published"].startswith("Sun, 11 Oct 2026")
    assert "Published: Sun, 11 Oct 2026" in out["retrieved_research"]


async def test_any_means_no_filter_and_no_news_index(calls):
    made = calls()
    out = await ts.tavily_searcher_node(_state(search_recency="any", search_topic="news"))
    assert "time_range" not in made[0] and "topic" not in made[0]
    assert "No date filter" in out["research_freshness"]


async def test_empty_window_widens_and_says_so(calls):
    made = calls(empty_for=("day",))
    out = await ts.tavily_searcher_node(_state(search_recency="day"))
    assert [c.get("time_range") for c in made] == ["day", "week"]
    assert "widened to the last week" in out["research_freshness"]


async def test_location_is_not_appended_to_the_query(calls, monkeypatch):
    seen = []
    made = calls()
    real = ts.TavilySearch

    class Spy(real):
        async def ainvoke(self, payload):
            seen.append(payload["query"])
            return await super().ainvoke(payload)
    monkeypatch.setattr(ts, "TavilySearch", Spy)
    await ts.tavily_searcher_node(_state(location_aware=True, user_location="Guadalajara, Mexico"))
    assert seen == ["q"] and made
