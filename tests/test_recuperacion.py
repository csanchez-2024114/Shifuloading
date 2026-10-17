"""Recuperación de contraseña por correo (PASSWORD_RESET_ENABLED, con AUTH_ENABLED). Servicio con las dos bases de
negocio (memoria y Mongo app_test) y endpoints con un correo falso. Sin tokens ni SMTP real."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from test_auth import app_db, appdata  # noqa: F401 - fixtures
from test_propiedad import ORIGIN, PW, _app

NUEVA = "contraseña-nueva-123"


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})


def _token(body: str) -> str:
    return re.search(r"#reset=([A-Za-z0-9_-]+)", body).group(1)


def _svc(appdata):  # noqa: F811
    from assistant.auth import AuthService

    return AuthService(appdata)


# --------------------------------------------------------------------------- servicio


def test_enlace_de_un_solo_uso_cambia_la_contraseña_y_cierra_sesiones(appdata):  # noqa: F811
    from assistant.auth import RESET_INVALID, AuthError, token_hash

    svc = _svc(appdata)
    svc.register("ana@ejemplo.com", PW)
    _, sesion = svc.login("ana@ejemplo.com", PW, "1.1.1.1")
    user, token = svc.request_reset("  Ana@Ejemplo.com ", "1.1.1.1")
    assert user["email"] == "ana@ejemplo.com"
    assert appdata.resets.consume(token) is None  # en la base solo está el hash, nunca el token
    with pytest.raises(AuthError):  # contraseña corta: no gasta el enlace
        svc.reset_password(token, "corta")
    svc.reset_password(token, NUEVA)
    assert svc.session_user(sesion) is None  # la sesión anterior quedó cerrada
    with pytest.raises(AuthError):
        svc.login("ana@ejemplo.com", PW, "1.1.1.1")
    assert svc.login("ana@ejemplo.com", NUEVA, "1.1.1.1")[1]
    with pytest.raises(AuthError) as e:  # un solo uso
        svc.reset_password(token, "otra-contraseña-456")
    assert e.value.message == RESET_INVALID
    assert appdata.resets.consume(token_hash(token)) is None


def test_correo_inexistente_enlace_caducado_y_solo_vale_el_ultimo(appdata):  # noqa: F811
    from assistant.auth import AuthError, token_hash

    svc = _svc(appdata)
    svc.register("ana@ejemplo.com", PW)
    assert svc.request_reset("nadie@ejemplo.com", "1.1.1.1") is None
    _, viejo = svc.request_reset("ana@ejemplo.com", "1.1.1.2")
    _, nuevo = svc.request_reset("ana@ejemplo.com", "1.1.1.3")
    with pytest.raises(AuthError):  # pedir otro invalida el anterior
        svc.reset_password(viejo, NUEVA)
    # caducado
    row = appdata.resets.consume(token_hash(nuevo))
    appdata.resets.create(row["token_hash"], row["user_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(AuthError):
        svc.reset_password(nuevo, NUEVA)
    with pytest.raises(AuthError):
        svc.reset_password("", NUEVA)


def test_limite_de_solicitudes_por_correo_y_por_ip(appdata):  # noqa: F811
    svc = _svc(appdata)
    svc.register("ana@ejemplo.com", PW)
    assert all(svc.request_reset("ana@ejemplo.com", f"2.2.2.{i}") for i in range(3))
    assert svc.request_reset("ana@ejemplo.com", "2.2.2.9") is None  # 4ª del mismo correo: se ignora
    for i in range(10):
        svc.request_reset(f"x{i}@ejemplo.com", "3.3.3.3")
    svc.register("beto@ejemplo.com", PW)
    assert svc.request_reset("beto@ejemplo.com", "3.3.3.3") is None  # 11ª de la misma IP
    assert svc.request_reset("beto@ejemplo.com", "4.4.4.4")


# --------------------------------------------------------------------------- endpoints


def agent_settings(make_settings, **kw):
    return make_settings(auth_enabled=True, password_reset_enabled=True, **kw)


def _reset_app(make_settings, **kw):
    """App con recuperación activada y un correo falso (el agente sale de _app, que no la activa)."""
    from assistant.server import create_app

    _, agent, appdata_, store = _app(make_settings)
    mailer = FakeMailer()
    app = create_app(agent=agent, settings=agent_settings(make_settings, **kw), store=store, appdata=appdata_,
                     mailer=mailer)
    return app, appdata_, mailer


def test_endpoints_respuesta_generica_enlace_por_correo_y_cambio(make_settings):
    from assistant.auth import RESET_DONE, RESET_SENT

    app, appdata_, mailer = _reset_app(make_settings, app_base_url="https://agente.ejemplo.com")
    c = TestClient(app, headers=ORIGIN)
    assert c.get("/auth/me").json()["password_reset"] is True
    reg = c.post("/auth/register", json={"email": "ana@ejemplo.com", "password": PW, "display_name": "Ana"})
    assert reg.status_code == 200

    r1 = c.post("/auth/forgot", json={"email": "nadie@ejemplo.com"})
    r2 = c.post("/auth/forgot", json={"email": "ana@ejemplo.com"})
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json() == {"ok": True, "message": RESET_SENT}
    assert [m["to"] for m in mailer.sent] == ["ana@ejemplo.com"]  # solo al que existe
    body = mailer.sent[0]["body"]
    assert "Hola, Ana" in body and "https://agente.ejemplo.com/#reset=" in body  # fragmento: no llega al servidor
    token = _token(body)

    bad = c.post("/auth/reset", json={"token": token, "password": "corta"})
    assert bad.status_code == 400
    ok = c.post("/auth/reset", json={"token": token, "password": NUEVA})
    assert ok.status_code == 200 and ok.json()["message"] == RESET_DONE
    assert c.get("/threads").status_code == 401  # la sesión del registro quedó cerrada
    assert c.post("/auth/reset", json={"token": token, "password": NUEVA}).status_code == 400  # un solo uso
    assert c.post("/auth/login", json={"email": "ana@ejemplo.com", "password": PW}).status_code == 401
    assert c.post("/auth/login", json={"email": "ana@ejemplo.com", "password": NUEVA}).status_code == 200


def test_sin_activar_o_sin_smtp_no_hay_recuperacion(make_settings):
    from assistant.config import ConfigError
    from assistant.server import create_app

    app, *_ = _app(make_settings)  # AUTH_ENABLED=1 sin PASSWORD_RESET_ENABLED
    c = TestClient(app, headers=ORIGIN)
    assert c.get("/auth/me").json()["password_reset"] is False
    assert c.post("/auth/forgot", json={"email": "a@b.co"}).status_code == 404
    assert c.post("/auth/reset", json={"token": "x", "password": NUEVA}).status_code == 404
    _, agent, appdata_, store = _app(make_settings)
    with pytest.raises(ConfigError, match="SMTP_HOST"):
        create_app(agent=agent, settings=agent_settings(make_settings), store=store, appdata=appdata_)


def test_otro_origen_no_puede_pedir_enlaces(make_settings):
    app, _, mailer = _reset_app(make_settings)
    c = TestClient(app, headers={"Origin": "https://malo.ejemplo.com"})
    assert c.post("/auth/forgot", json={"email": "ana@ejemplo.com"}).status_code == 403
    assert mailer.sent == []


def test_borrar_cuenta_borra_sus_enlaces(make_settings):
    app, appdata_, mailer = _reset_app(make_settings)
    c = TestClient(app, headers=ORIGIN)
    reg = c.post("/auth/register", json={"email": "ana@ejemplo.com", "password": PW})
    c.headers["X-CSRF-Token"] = reg.json()["csrf"]
    c.post("/auth/forgot", json={"email": "ana@ejemplo.com"})
    token = _token(mailer.sent[0]["body"])
    assert c.post("/auth/delete-account", json={"password": PW}).json()["deleted"]
    assert c.post("/auth/reset", json={"token": token, "password": NUEVA}).status_code == 400
