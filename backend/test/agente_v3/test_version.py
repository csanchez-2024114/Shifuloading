"""La huella de version cambia si cambia un prompt en Mongo, y no por _id ni fechas."""
from app.agent.version import fingerprint


def test_fingerprint_tracks_behavior_data_only():
    p = {"voice": {"tone": "calido"}, "_id": "a", "updated_at": "2026-10-10"}
    assert fingerprint({}, p) == fingerprint({}, {**p, "_id": "b", "updated_at": "2026-10-11"})
    assert fingerprint({}, p) != fingerprint({}, {**p, "voice": {"tone": "seco"}})
