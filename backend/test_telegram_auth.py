"""
Script assert-based (no framework) para validar la verificación HMAC-SHA256
del Telegram Login Widget implementada en app/routes/auth/authRoutes.py,
sin depender de tener un bot real de Telegram.

Corre: python test_telegram_auth.py
"""
import hashlib
import hmac
import time

from app.routes.auth.authRoutes import (
    telegram_data_check_string,
    verify_telegram_login_hash,
)

FAKE_BOT_TOKEN = "000000000:TOKEN_DE_PRUEBA"


def build_signed_payload(bot_token: str, **fields) -> dict:
    """Construye un payload de Telegram Login Widget con un hash válido para bot_token."""
    data_check_string = telegram_data_check_string(fields)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return {**fields, "hash": computed_hash}


def test_valid_hash_matches():
    payload = build_signed_payload(
        FAKE_BOT_TOKEN,
        id=123456789,
        first_name="John",
        last_name="Doe",
        username="johndoe",
        photo_url="https://t.me/i/userpic/320/johndoe.jpg",
        auth_date=int(time.time()),
    )
    assert verify_telegram_login_hash(payload, FAKE_BOT_TOKEN) is True, "El hash válido debería matchear"


def test_wrong_bot_token_fails():
    payload = build_signed_payload(
        FAKE_BOT_TOKEN,
        id=123456789,
        first_name="John",
        auth_date=int(time.time()),
    )
    assert verify_telegram_login_hash(payload, "987654321:OtroBotTokenDistinto") is False, (
        "Un bot token distinto no debería validar el hash"
    )


def test_tampered_field_fails():
    payload = build_signed_payload(
        FAKE_BOT_TOKEN,
        id=123456789,
        first_name="John",
        auth_date=int(time.time()),
    )
    payload["first_name"] = "Jane"  # alterar un campo después de firmar
    assert verify_telegram_login_hash(payload, FAKE_BOT_TOKEN) is False, (
        "Un payload alterado post-firma no debería validar"
    )


def test_missing_hash_fails():
    payload = {"id": 123456789, "first_name": "John", "auth_date": int(time.time())}
    assert verify_telegram_login_hash(payload, FAKE_BOT_TOKEN) is False, (
        "Un payload sin hash nunca debería validar"
    )


def test_data_check_string_ordering_and_exclusion():
    fields = {"z_field": "last", "a_field": "first", "hash": "should-be-excluded", "id": 1}
    dcs = telegram_data_check_string(fields)
    lines = dcs.split("\n")
    assert lines == ["a_field=first", "id=1", "z_field=last"], (
        f"data_check_string debe estar ordenado alfabéticamente y excluir 'hash', obtuvo: {lines}"
    )


if __name__ == "__main__":
    tests = [
        test_valid_hash_matches,
        test_wrong_bot_token_fails,
        test_tampered_field_fails,
        test_missing_hash_fails,
        test_data_check_string_ordering_and_exclusion,
    ]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests pasaron.")
