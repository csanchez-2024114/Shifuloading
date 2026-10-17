"""Cuentas y sesiones (AUTH_ENABLED): servicio, repositorios de la base de negocio y borrado en la base de la IA.
Sin tokens. Mongo solo en assistant_test (IA) y app_test (negocio)."""
from datetime import datetime, timedelta, timezone

import pytest

from conftest import uid

APP_TEST_DB = "app_test"  # NUNCA una base real


@pytest.fixture
def app_db(mongo_client):
    mongo_client.drop_database(APP_TEST_DB)
    yield APP_TEST_DB
    mongo_client.drop_database(APP_TEST_DB)


@pytest.fixture(params=["memoria", "mongo"])
def appdata(request):
    if request.param == "memoria":
        from assistant.appdata.memory import MemoryAppData

        return MemoryAppData()
    from assistant.appdata.mongo import MongoAppData

    return MongoAppData(request.getfixturevalue("mongo_client"), request.getfixturevalue("app_db"))


def _svc(appdata, **kw):
    from assistant.auth import AuthService

    return AuthService(appdata, **kw)


def test_registro_guarda_hash_argon2id_y_correo_normalizado(appdata):
    svc = _svc(appdata)
    user = svc.register("  Ana@Ejemplo.COM ", "contraseña-larga-1", "Ana")
    stored = appdata.users.get_by_email("ana@ejemplo.com")
    assert stored["user_id"] == user["user_id"] and len(user["user_id"]) == 36  # UUID opaco
    assert stored["password_hash"].startswith("$argon2id$") and "contraseña-larga-1" not in str(stored)
    assert stored["status"] == "active" and stored["display_name"] == "Ana"


def test_registro_rechaza_contraseña_corta_y_correo_repetido_con_mensaje_generico(appdata):
    from assistant.auth import PASSWORD_RULE, REGISTER_ERROR, AuthError

    svc = _svc(appdata)
    with pytest.raises(AuthError) as e:
        svc.register("ana@ejemplo.com", "corta", "Ana")
    assert e.value.message == PASSWORD_RULE
    svc.register("ana@ejemplo.com", "contraseña-larga-1")
    with pytest.raises(AuthError) as e:
        svc.register("ANA@ejemplo.com", "otra-contraseña-2")
    assert e.value.message == REGISTER_ERROR and "existe" not in e.value.message


def test_login_correcto_crea_sesion_guardada_solo_como_hash(appdata):
    from assistant.auth import token_hash

    svc = _svc(appdata)
    svc.register("ana@ejemplo.com", "contraseña-larga-1")
    user, token = svc.login("ANA@ejemplo.com", "contraseña-larga-1", "1.2.3.4")
    assert len(token) >= 40
    assert appdata.sessions.get(token) is None and appdata.sessions.get(token_hash(token))["user_id"] == user["user_id"]
    assert svc.session_user(token)["user_id"] == user["user_id"]
    svc.logout(token)
    assert svc.session_user(token) is None


def test_login_incorrecto_es_generico_y_se_bloquea_tras_5_fallos(appdata):
    from assistant.auth import LOCKED_ERROR, LOGIN_ERROR, AuthError

    svc = _svc(appdata)
    svc.register("ana@ejemplo.com", "contraseña-larga-1")
    mensajes = set()
    for email in ["ana@ejemplo.com", "nadie@ejemplo.com"]:  # correo existente o no: mismo mensaje
        with pytest.raises(AuthError) as e:
            svc.login(email, "mala-contraseña", "9.9.9.9")
        mensajes.add((e.value.status, e.value.message))
    assert mensajes == {(401, LOGIN_ERROR)}
    for _ in range(4):
        with pytest.raises(AuthError):
            svc.login("ana@ejemplo.com", "mala-contraseña", "5.5.5.5")
    with pytest.raises(AuthError) as e:  # bloqueado: ni con la contraseña correcta
        svc.login("ana@ejemplo.com", "contraseña-larga-1", "7.7.7.7")
    assert (e.value.status, e.value.message) == (429, LOCKED_ERROR)


def test_ip_con_10_fallos_en_correos_distintos_no_se_bloquea_y_a_los_20_si(appdata):
    from assistant.auth import AuthError

    svc = _svc(appdata)
    svc.register("ana@ejemplo.com", "contraseña-larga-1")
    for i in range(10):
        with pytest.raises(AuthError):
            svc.login(f"x{i}@ejemplo.com", "mala-contraseña", "6.6.6.6")
    assert svc.login("ana@ejemplo.com", "contraseña-larga-1", "6.6.6.6")[1]  # 10 fallos repartidos: entra
    for i in range(10, 20):
        with pytest.raises(AuthError):
            svc.login(f"x{i}@ejemplo.com", "mala-contraseña", "6.6.6.6")
    with pytest.raises(AuthError) as e:
        svc.login("ana@ejemplo.com", "contraseña-larga-1", "6.6.6.6")
    assert e.value.status == 429
    assert svc.login("ana@ejemplo.com", "contraseña-larga-1", "8.8.8.8")[1]  # otra IP sí entra


def test_umbrales_configurables(appdata, monkeypatch):
    from assistant.auth import AuthError
    from assistant.config import Settings

    monkeypatch.setenv("LOGIN_MAX_FAILS_PER_EMAIL", "2")
    monkeypatch.setenv("LOGIN_MAX_FAILS_PER_IP", "3")
    s = Settings.from_env()
    assert (s.login_max_fails, s.login_max_fails_ip) == (2, 3)
    svc = _svc(appdata, max_fails=s.login_max_fails, max_fails_ip=s.login_max_fails_ip)
    svc.register("ana@ejemplo.com", "contraseña-larga-1")
    for i in range(3):
        with pytest.raises(AuthError):
            svc.login(f"x{i}@ejemplo.com", "mala-contraseña", "6.6.6.6")
    with pytest.raises(AuthError) as e:
        svc.login("ana@ejemplo.com", "contraseña-larga-1", "6.6.6.6")
    assert e.value.status == 429


def test_sesion_caducada_y_renovacion_deslizante(appdata):
    from assistant.auth import token_hash

    svc = _svc(appdata, ttl_days=14)
    svc.register("ana@ejemplo.com", "contraseña-larga-1")
    _, token = svc.login("ana@ejemplo.com", "contraseña-larga-1", "1.1.1.1")
    th = token_hash(token)
    viejo = datetime.now(timezone.utc) - timedelta(hours=2)
    appdata.sessions.touch(th, datetime.now(timezone.utc) + timedelta(days=1))
    if hasattr(appdata.sessions, "rows"):
        appdata.sessions.rows[th]["last_seen"] = viejo
    else:
        appdata.sessions.col.update_one({"token_hash": th}, {"$set": {"last_seen": viejo}})
    assert svc.session_user(token)
    assert appdata.sessions.get(th)["expires_at"] > datetime.now(timezone.utc) + timedelta(days=13)  # renovada
    appdata.sessions.touch(th, datetime.now(timezone.utc) - timedelta(seconds=1))
    assert svc.session_user(token) is None and appdata.sessions.get(th) is None  # caducada: se borra


def test_csrf_derivado_del_token():
    from assistant.auth import csrf_for, csrf_ok

    assert csrf_ok("tok", csrf_for("tok")) and not csrf_ok("tok", csrf_for("otro")) and not csrf_ok("tok", None)
