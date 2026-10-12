"""get_real_ip: X-Forwarded-For solo cuenta si la peticion llega de un proxy propio."""
from types import SimpleNamespace

from app.core import limiter


def _req(peer, xff=None):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers={"X-Forwarded-For": xff} if xff else {})


def test_spoofed_header_from_client_is_ignored(monkeypatch):
    monkeypatch.setattr(limiter, "_TRUSTED", set())
    assert limiter.get_real_ip(_req("9.9.9.9", "1.2.3.4")) == "9.9.9.9"


def test_behind_trusted_proxy_takes_rightmost_untrusted_hop(monkeypatch):
    monkeypatch.setattr(limiter, "_TRUSTED", {"10.0.0.1"})
    # el cliente escribio 1.2.3.4 (falso); el proxy agrego la IP real 9.9.9.9
    assert limiter.get_real_ip(_req("10.0.0.1", "1.2.3.4, 9.9.9.9")) == "9.9.9.9"
