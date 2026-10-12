"""Constantes compartidas de las pruebas de funciones."""

# Descripcion valida (ingles, completa, >= 200 caracteres) para las funciones de prueba.
DESC = (
    "Test function used by the automated tests. It returns a small value for a given input so the registry, the runner and the publisher "
    "can be checked without any real app. Use it only inside tests: it is read-only, takes simple parameters and never touches an external service."
)


# --- Cuentas de prueba en el formato del sistema de funciones (credenciales en un solo blob cifrado) ---
import json  # noqa: E402

from app.core.security import decrypt_data, encrypt_data  # noqa: E402


def seal(fields: dict) -> str:
    return encrypt_data(json.dumps(fields))


def unseal(token: str) -> dict:
    return json.loads(decrypt_data(token))


def connection_doc(*, space="u1", account="A", provider="demo", token="tok-A", refresh=None, status="active", **extra) -> dict:
    fields = {"token": token}
    if refresh:
        fields["refresh_token"] = refresh
    return {"user_id": space, "provider": provider, "account_id": account, "status": status, "credentials_enc": seal(fields), **extra}
