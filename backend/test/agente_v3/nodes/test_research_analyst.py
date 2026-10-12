"""research_analyst: la resta de fechas y la segunda busqueda las decide el codigo; el juicio va al inicio de la investigacion."""
import pytest

from app.agent.shared.nodes import research_analyst as ra

TODAY = "2026-10-11T19:00:00Z"


def _j(**kw):
    return ra._Judgment(**{"reasoning": "r", "conclusion": "c", "confidence": "high", **kw})


def _announced(date):
    return ra._Announced(what="iPhone 18", date=date, check_query="iPhone 18 release")


def test_already_past_compares_at_the_precision_of_the_source():
    dates = ["2026-09", "2026-10", "2026-10-05", "2026-10-11", "2026-12", "2027", "soon"]
    assert [a.date for a in ra._already_past([_announced(d) for d in dates], TODAY)] == ["2026-09", "2026-10-05"]


def test_each_source_date_is_stamped_against_the_system_date():
    block = ra._sources_block([{"title": "a", "domain": "a.test", "published": "Fri, 19 Sep 2025 10:00:00 GMT"},
                               {"title": "b", "domain": "b.test", "published": "2026-10-11"},
                               {"title": "c", "domain": "c.test", "published": "ayer"},
                               {"title": "d", "domain": "d.test"}], TODAY)
    a, b, c, d = block.split("\n")[::2]
    assert "(387 days before TODAY)" in a and b.endswith("(TODAY)")
    assert c.endswith("published ayer") and d.endswith("no publication date")  # lo que no se entiende no se inventa


def test_every_near_date_in_the_text_is_stamped_against_the_system_date():
    text = ("available Sept. 18, 2026; the Duo ships October 23, 2026; standard model in March 2027; el 18 de septiembre de "
            "2026; ISO 2026-10-11; iPhone 4 on June 24, 2010; it may 2026 times")
    out = ra._stamp_dates(text, TODAY)
    assert "Sept. 18, 2026 [PAST: 23 days before TODAY]" in out and "October 23, 2026 [FUTURE: in 12 days]" in out
    assert "March 2027 [FUTURE month]" in out and "18 de septiembre de 2026 [PAST: 23 days before TODAY]" in out
    assert "2026-10-11 [TODAY]" in out
    assert "June 24, 2010;" in out and "may 2026 times" in out  # lejana: sin marca; "may" en minuscula no es un mes
    assert ra._stamp_dates(text, "sin fecha") == text


def test_a_conclusion_that_speaks_in_future_about_a_past_date_is_caught():
    stale = "The iPhone 17 is the latest. The 18 Pro will be available on September 18, 2026. The Duo is set for October 23, 2026."
    assert ra._future_about_past(stale, TODAY) == ["September 18, 2026"]  # la del 23 de octubre si es futura
    assert ra._future_about_past("The 18 Pro was released on September 18, 2026.", TODAY) == []
    assert ra._future_about_past("Bitcoin is at $83,000 as of October 9, 2026.", TODAY) == []


@pytest.fixture
def wired(monkeypatch):
    seen = {"judge": [], "search": []}

    async def personality():
        return {}

    async def search(state):
        seen["search"].append(state)
        return {"retrieved_research": "iPhone 18 Pro on sale September 18, 2026", "retrieved_sources": [{"url": "https://b.test"}]}
    monkeypatch.setattr(ra, "get_agent_personality", personality)
    monkeypatch.setattr(ra, "tavily_searcher_node", search)

    def judge_with(*answers):
        queue = list(answers)

        async def judge(model, criteria, state, research, sources, note=""):
            seen["judge"].append({"research": research, "note": note})
            return queue.pop(0)
        monkeypatch.setattr(ra, "_judge", judge)
        return seen
    return judge_with


def _state():
    return {"retrieved_research": "iPhone 18 expected in September 2026", "curated_research": "curated",
            "retrieved_sources": [{"url": "https://a.test"}], "current_time_utc": TODAY, "search_recency": "day"}


async def test_announcement_already_past_forces_a_second_search_even_with_high_confidence(wired):
    seen = wired(_j(conclusion="iPhone 17 is the latest", announced=[_announced("2026-09")]), _j(conclusion="iPhone 18 Pro"))
    out = await ra.research_analyst_node(_state())
    assert seen["search"][0]["optimized_search_query"] == "iPhone 18 release" and seen["search"][0]["search_recency"] == "any"
    assert "in the PAST" in seen["judge"][1]["note"]
    assert seen["judge"][1]["research"].startswith("## Second search")  # lo nuevo se lee antes que las paginas viejas
    assert "September 18, 2026" in seen["judge"][1]["research"] and "## First search" in seen["judge"][1]["research"]
    assert out["curated_research"].startswith("## Analyst judgment") and "Conclusion: iPhone 18 Pro" in out["curated_research"]
    assert "curated" in out["curated_research"] and "September 18, 2026" in out["curated_research"]
    assert [s["url"] for s in out["retrieved_sources"]] == ["https://a.test", "https://b.test"]  # los [N] viejos no se mueven


async def test_a_stale_conclusion_is_rewritten_once_without_another_search(wired):
    # La fuente no lo llamaba "proximo", asi que no hubo segunda busqueda; el codigo lo atrapa en la conclusion.
    seen = wired(_j(conclusion="iPhone 17 is the latest; the 18 Pro will be available on September 18, 2026."),
                 _j(conclusion="The 18 Pro, released on September 18, 2026, is the latest."))
    out = await ra.research_analyst_node(_state())
    assert not seen["search"] and len(seen["judge"]) == 2
    assert "September 18, 2026 is in the PAST" in seen["judge"][1]["note"]
    assert "Conclusion: The 18 Pro, released on September 18, 2026" in out["curated_research"]


async def test_high_confidence_and_nothing_past_does_not_search_again(wired):
    seen = wired(_j(follow_up_query="anything", announced=[_announced("2027-03")]))
    out = await ra.research_analyst_node(_state())
    assert not seen["search"] and "Confidence: high" in out["curated_research"]


async def test_low_confidence_uses_the_follow_up_query_once(wired):
    seen = wired(_j(confidence="low", follow_up_query="better query"), _j(confidence="low", follow_up_query="again"))
    await ra.research_analyst_node(_state())
    assert [s["optimized_search_query"] for s in seen["search"]] == ["better query"]


async def test_no_research_or_a_failing_judge_leaves_the_turn_alone(wired, monkeypatch):
    wired()
    assert await ra.research_analyst_node({"retrieved_research": None}) == {}

    async def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(ra, "_judge", boom)
    assert await ra.research_analyst_node(_state()) == {}
