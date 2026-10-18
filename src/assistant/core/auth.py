"""Cuentas y sesiones (AUTH_ENABLED). Contraseñas con argon2id; sesiones del lado del servidor: el navegador guarda un
token aleatorio en una cookie HttpOnly y la base solo su hash (sha256). Nunca se registran contraseñas ni tokens.

El token CSRF se deriva del token de sesión (no se guarda): /auth/me lo devuelve y las peticiones que cambian estado
lo mandan en la cabecera X-CSRF-Token. Sin la cookie no sirve de nada."""
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from assistant.core.appdata.repos import AppData, DuplicateEmail

MIN_PASSWORD_LEN = 10
MAX_PASSWORD_LEN = 256
SESSION_COOKIE = "agente0_session"
CSRF_HEADER = "X-CSRF-Token"
TOUCH_EVERY = timedelta(hours=1)  # renovación deslizante: como mucho una escritura por hora y sesión

# mensajes genéricos: no revelan si un correo existe
LOGIN_ERROR = "Correo o contraseña incorrectos."
REGISTER_ERROR = "No se pudo crear la cuenta con esos datos."
LOCKED_ERROR = "Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo."
PASSWORD_RULE = f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres."

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_for(token: str) -> str:
    return hashlib.sha256(f"csrf:{token}".encode()).hexdigest()[:40]


def csrf_ok(token: str, sent: str | None) -> bool:
    return bool(sent) and hmac.compare_digest(csrf_for(token), sent)


class AuthService:
    def __init__(self, data: AppData, ttl_days: int = 14, max_fails: int = 5, lock_minutes: int = 10,
                 max_fails_ip: int = 20):
        self.data = data
        self.ttl = timedelta(days=ttl_days)
        # umbral por correo y, más alto, por IP: varios usuarios detrás de un mismo NAT no se bloquean entre sí
        self.max_fails = {"email": max_fails, "ip": max_fails_ip}
        self.window = timedelta(minutes=lock_minutes)  # fallos dentro de la ventana -> bloqueo de la misma duración
        self.ph = PasswordHasher()  # argon2id con los parámetros por defecto de argon2-cffi
        self._dummy = self.ph.hash(secrets.token_urlsafe(16))  # iguala tiempos con correos inexistentes

    def _verify(self, password_hash: str, password: str) -> bool:
        try:
            return self.ph.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def register(self, email: str, password: str, display_name: str = "") -> dict:
        email = normalize_email(email)
        if not _EMAIL_RE.match(email) or len(email) > 254:
            raise AuthError(400, REGISTER_ERROR)
        if not isinstance(password, str) or not MIN_PASSWORD_LEN <= len(password) <= MAX_PASSWORD_LEN:
            raise AuthError(400, PASSWORD_RULE)
        name = " ".join((display_name or "").split())[:60] or email.split("@")[0]
        try:
            return self.data.users.create(str(uuid.uuid4()), email, name, self.ph.hash(password))
        except DuplicateEmail:
            raise AuthError(400, REGISTER_ERROR) from None

    def login(self, email: str, password: str, ip: str) -> tuple[dict, str]:
        """(usuario, token de sesión). AuthError 401 genérico o 429 si la clave (correo o IP) está bloqueada."""
        email = normalize_email(email)
        now = datetime.now(timezone.utc)
        keys = [f"email:{email}", f"ip:{ip or 'desconocida'}"]
        if any((until := self.data.attempts.locked_until(k)) and until > now for k in keys):
            raise AuthError(429, LOCKED_ERROR)
        user = self.data.users.get_by_email(email) if email else None
        ok = self._verify(user["password_hash"] if user else self._dummy, password or "")
        if not (ok and user and user.get("status") == "active"):
            for k in keys:
                self.data.attempts.record_failure(k, now)
                if self.data.attempts.failures_since(k, now - self.window) >= self.max_fails[k.split(":", 1)[0]]:
                    self.data.attempts.lock(k, now + self.window)
            raise AuthError(401, LOGIN_ERROR)
        self.data.attempts.clear(keys[0])
        token = secrets.token_urlsafe(32)
        self.data.sessions.create(token_hash(token), user["user_id"], now + self.ttl)
        return user, token

    def session_user(self, token: str | None) -> dict | None:
        """Usuario de la sesión (renovando su caducidad) o None si no hay, caducó o el usuario ya no existe."""
        if not token:
            return None
        th = token_hash(token)
        session = self.data.sessions.get(th)
        now = datetime.now(timezone.utc)
        if session is None:
            return None
        if session["expires_at"] <= now:
            self.data.sessions.delete(th)
            return None
        user = self.data.users.get(session["user_id"])
        if user is None or user.get("status") != "active":
            return None
        if now - session.get("last_seen", now) >= TOUCH_EVERY:
            self.data.sessions.touch(th, now + self.ttl)
        return user

    def logout(self, token: str | None) -> None:
        if token:
            self.data.sessions.delete(token_hash(token))

    def check_password(self, user: dict, password: str) -> bool:
        return self._verify(user["password_hash"], password or "")
