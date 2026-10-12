"""
Rutas de Autenticación e Identidad — Sistema Oficial Shifu
Modelos: User (users), UserAuthMethod (user_auth_methods), UserSession (user_sessions)
Providers soportados: GOOGLE, PASSWORD, TELEGRAM. Arquitectura preparada para futuros providers.
Seguridad: Argon2, JWT 15min, Refresh Token 30d con rotación, timing-attack mitigation.
"""

import hmac
import httpx
import jwt
import hashlib
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, List
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from bson import ObjectId
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from werkzeug.security import check_password_hash
from pymongo.errors import DuplicateKeyError

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from app.core.limiter import limiter
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email
from config import Config

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

SECRET_KEY = Config.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = Config.JWT_REFRESH_TOKEN_EXPIRE_DAYS

pwd_context = CryptContext(schemes=["argon2", "pbkdf2_sha256"], deprecated="auto")
DUMMY_PASSWORD_HASH = pwd_context.hash("hyper-shifu-dummy-password")

PROVIDER_GOOGLE = "GOOGLE"
PROVIDER_PASSWORD = "PASSWORD"
PROVIDER_TELEGRAM = "TELEGRAM"

TELEGRAM_AUTH_MAX_AGE_SECONDS = 24 * 60 * 60  # rechaza payloads de más de 24hs (anti-replay)

_GOOGLE_SIGNIN_SCOPES = "openid email profile"


def _make_oauth_state() -> str:
    nonce = secrets.token_urlsafe(16)
    sig = hmac.new(SECRET_KEY.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{sig}"


def _verify_oauth_state(state: str) -> bool:
    try:
        nonce, sig = state.rsplit(".", 1)
        expected = hmac.new(SECRET_KEY.encode(), nonce.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def telegram_data_check_string(data: Dict[str, Any]) -> str:
    """
    Construye el `data_check_string` estándar del Telegram Login Widget:
    todos los campos del payload excepto `hash`, ordenados alfabéticamente
    como `key=value`, unidos por `\\n`.
    Referencia: https://core.telegram.org/widgets/login#checking-authorization
    """
    pairs = [f"{k}={v}" for k, v in sorted(data.items()) if k != "hash" and v is not None]
    return "\n".join(pairs)


def verify_telegram_login_hash(data: Dict[str, Any], bot_token: str) -> bool:
    """
    Verifica el `hash` HMAC-SHA256 enviado por el Telegram Login Widget contra el bot token.
    secret_key = SHA256(bot_token); hmac = HMAC-SHA256(data_check_string, secret_key) en hex.
    """
    received_hash = data.get("hash")
    if not received_hash or not bot_token:
        return False
    data_check_string = telegram_data_check_string(data)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_hash, received_hash)


# ── Pydantic Models ──────────────────────────────────────────────────────────

class RegisterModel(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    referral_code: Optional[str] = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("La contraseña debe contener al menos una letra y un número.")
        return v


class LoginModel(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginModel(BaseModel):
    credential: str  # Google ID token from frontend


class TelegramLoginModel(BaseModel):
    """Payload tal cual lo envía el Telegram Login Widget."""
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str
    model_config = ConfigDict(extra="allow")  # el widget puede mandar campos futuros; deben entrar al data_check_string


class RefreshModel(BaseModel):
    refresh_token: str


class LogoutModel(BaseModel):
    refresh_token: str


# ── Private Helpers ──────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _build_access_token(user_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "user_id": user_id,  # ponytail: kept for backward compat with 30+ existing endpoints
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def _create_session(mongo, user_id: str, request: Request) -> Tuple[str, Any]:
    """Creates a UserSession. Returns (raw_refresh_token, session_id)."""
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    now = datetime.now(timezone.utc)
    user_agent = request.headers.get("user-agent", "")
    doc = {
        "user_id": ObjectId(user_id),
        "refresh_token_hash": token_hash,
        "device_name": user_agent[:120] if user_agent else "unknown",
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": user_agent[:512],
        "created_at": now,
        "last_used_at": now,
        "expires_at": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "revoked_at": None,
    }
    res = await mongo[Collections.USER_SESSIONS].insert_one(doc)
    return raw, res.inserted_id


async def _create_initial_onboarding(mongo, user_id: str, display_name: str = "") -> None:
    """Creates UserProfile and UserOnboarding for a brand-new user. Safe to call once; ignored on duplicates."""
    now = datetime.now(timezone.utc)
    user_oid = ObjectId(user_id)
    await mongo[Collections.USER_PROFILES].update_one(
        {"user_id": user_oid},
        {"$setOnInsert": {"user_id": user_oid, "avatar_url": None, "display_name": display_name, "created_at": now, "updated_at": now}},
        upsert=True,
    )
    await mongo[Collections.USER_ONBOARDING].update_one(
        {"user_id": user_oid},
        {"$setOnInsert": {"user_id": user_oid, "current_step": 1, "completed": False, "completed_at": None, "created_at": now, "updated_at": now}},
        upsert=True,
    )


async def _complete_pending_workspace_invites(mongo, user_id: str, email: str) -> None:
    """
    Claims any pending workspace invitations for this email (workspace_members with
    status="invited", user_id=None — created by POST /api/v1/workspaces/{id}/members/invite
    before the invited person had an account). Called on every register/login success so an
    invite gets attached to the account as soon as it exists, without a separate "accept" step.
    Safe/idempotent to call repeatedly (no-op once already claimed).
    """
    if not email:
        return
    await mongo[Collections.WORKSPACE_MEMBERS].update_many(
        {"email": email, "status": "invited", "user_id": None},
        {"$set": {
            "user_id": user_id,
            "status": "active",
            "joined_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }},
    )


async def _ensure_auth_method(mongo, user_id: str, provider: str, provider_user_id: str) -> None:
    """Upsert a UserAuthMethod. Safe to call even if the method already exists."""
    now = datetime.now(timezone.utc)
    await mongo[Collections.USER_AUTH_METHODS].update_one(
        {"user_id": ObjectId(user_id), "provider": provider},
        {
            "$setOnInsert": {"created_at": now, "provider_user_id": provider_user_id},
            "$set": {"updated_at": now},
        },
        upsert=True,
    )


async def _get_auth_methods(mongo, user_id: str) -> List[str]:
    cursor = mongo[Collections.USER_AUTH_METHODS].find(
        {"user_id": ObjectId(user_id)}, {"provider": 1}
    )
    return [doc["provider"] async for doc in cursor]


def _auth_response(user_doc: dict, access_token: str, refresh_token: str, auth_methods: List[str]) -> dict:
    user_id = str(user_doc["_id"])
    return {
        "user": {
            "id": user_id,
            "name": user_doc.get("name", ""),
            "last_name": user_doc.get("last_name", ""),
            "email": user_doc.get("email", ""),
            "avatar": user_doc.get("avatar"),
            "plan": user_doc.get("plan", "free"),
        },
        "access_token": access_token,
        "refresh_token": refresh_token,
        "auth_methods": auth_methods,
    }


# ── Auth functions reused by other modules ───────────────────────────────────

def verify_password_and_upgrade(
    plain_password: str, stored_hash: Optional[str]
) -> Tuple[bool, Optional[str]]:
    if not stored_hash or not isinstance(stored_hash, str):
        pwd_context.verify(plain_password, DUMMY_PASSWORD_HASH)
        return (False, None)
    try:
        return pwd_context.verify_and_update(plain_password, stored_hash)
    except UnknownHashError:
        if stored_hash.startswith(("scrypt:", "pbkdf2:")):
            if check_password_hash(stored_hash, plain_password):
                return (True, pwd_context.hash(plain_password))
            return (False, None)
        logger.warning("Formato de hash no soportado detectado durante login.")
        pwd_context.verify(plain_password, DUMMY_PASSWORD_HASH)
        return (False, None)


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if "user_id" not in payload:
            raise ValueError("Payload incompleto: falta user_id")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ha expirado. Re-autentique.",
        )
    except Exception as e:
        logger.error(f"Error de validación de token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de acceso inválidas",
        )


# ── Utilities ────────────────────────────────────────────────────────────────

async def generate_unique_referral_code(mongo) -> str:
    for _ in range(10):
        code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        if not await mongo[Collections.USERS].find_one({"code_referrals_uniq": code}, {"_id": 1}):
            return code
    raise HTTPException(status_code=500, detail="Error interno al generar código de referido.")


async def update_login_streak(mongo, user_id: str):
    user_oid = ObjectId(user_id)
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    await mongo.login_streaks.update_one(
        {"user_id": user_oid, "login_date": today},
        {"$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    last_login = await mongo.login_streaks.find_one(
        {"user_id": user_oid, "login_date": {"$lt": today}}, sort=[("login_date", -1)]
    )
    if last_login:
        db_date = (
            last_login["login_date"].replace(tzinfo=timezone.utc)
            if last_login["login_date"].tzinfo is None
            else last_login["login_date"]
        )
        if db_date >= yesterday:
            await mongo[Collections.USERS].update_one(
                {"_id": user_oid}, {"$inc": {"login_streak": 1}}
            )
            return
    await mongo[Collections.USERS].update_one({"_id": user_oid}, {"$set": {"login_streak": 1}})


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register_user(request: Request, data: RegisterModel):
    mongo = request.app.state.db
    email_clean = data.email.lower().strip()

    existing = await mongo[Collections.USERS].find_one({"email": email_clean}, {"_id": 1, "password": 1})
    if existing:
        # If user exists with PASSWORD method, reject. If only GOOGLE, add password.
        has_password = await mongo[Collections.USER_AUTH_METHODS].find_one(
            {"user_id": existing["_id"], "provider": PROVIDER_PASSWORD}
        )
        if has_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La cuenta ya existe. Inicia sesión con tu contraseña.",
            )
        # Existing user (GOOGLE only) → add password method
        hashed_pw = pwd_context.hash(data.password)
        await mongo[Collections.USERS].update_one(
            {"_id": existing["_id"]},
            {"$set": {"password": hashed_pw, "name": data.name.strip(), "last_name": data.last_name.strip()}},
        )
        user_id = str(existing["_id"])
        await _ensure_auth_method(mongo, user_id, PROVIDER_PASSWORD, user_id)
        user_doc = await mongo[Collections.USERS].find_one({"_id": existing["_id"]})
        raw_refresh, _ = await _create_session(mongo, user_id, request)
        access_token = _build_access_token(user_id, email_clean)
        auth_methods = await _get_auth_methods(mongo, user_id)
        await _complete_pending_workspace_invites(mongo, user_id, email_clean)
        return _auth_response(user_doc, access_token, raw_refresh, auth_methods)

    hashed_pw = pwd_context.hash(data.password)
    referral_code = await generate_unique_referral_code(mongo)
    now = datetime.now(timezone.utc)
    user_doc = {
        "name": data.name.strip(),
        "last_name": data.last_name.strip(),
        "email": email_clean,
        "password": hashed_pw,
        "rol": "user",
        "login_streak": 1,
        "code_referrals_uniq": referral_code,
        "referral_code": referral_code,
        "created_at": now,
        "date_registered": now,
        "account_status": "active",
        "is_active": True,
        "plan": "free",
        "integrations": {},
        "preferences": {},
    }
    try:
        res = await mongo[Collections.USERS].insert_one(user_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El registro no pudo completarse. El usuario ya existe.",
        )

    user_id = str(res.inserted_id)
    user_doc["_id"] = res.inserted_id
    await _ensure_auth_method(mongo, user_id, PROVIDER_PASSWORD, user_id)
    await _create_initial_onboarding(mongo, user_id, display_name=data.name.strip())
    raw_refresh, _ = await _create_session(mongo, user_id, request)
    access_token = _build_access_token(user_id, email_clean)
    auth_methods = await _get_auth_methods(mongo, user_id)
    await _complete_pending_workspace_invites(mongo, user_id, email_clean)

    if data.referral_code:
        try:
            code = data.referral_code.strip().upper()
            referrer = await mongo[Collections.USERS].find_one({"code_referrals_uniq": code})
            if referrer and str(referrer["_id"]) != user_id:
                already_referred = await mongo[Collections.USERS].find_one(
                    {"_id": res.inserted_id, "referred_by": {"$exists": True, "$ne": None}}
                )
                if not already_referred:
                    now = datetime.now(timezone.utc)
                    await mongo.referrals.insert_one({
                        "referrer_id": str(referrer["_id"]),
                        "referred_id": user_id,
                        "referral_code": code,
                        "date_registered": now,
                    })
                    await mongo[Collections.USERS].update_one(
                        {"_id": referrer["_id"]},
                        {"$inc": {"count_referrals": 1}},
                    )
                    await mongo[Collections.USERS].update_one(
                        {"_id": res.inserted_id},
                        {"$set": {"referred_by": str(referrer["_id"])}},
                    )
                    logger.info(f"Referral aplicado: {code} → {user_id} (referrer: {referrer['_id']})")
        except Exception as e:
            logger.warning(f"Error procesando referral_code '{data.referral_code}': {e}")

    logger.info("Nuevo usuario registrado: %s", email_clean)
    return _auth_response(user_doc, access_token, raw_refresh, auth_methods)


@router.post("/login")
@limiter.limit("5/minute")
async def login_user(request: Request, data: LoginModel):
    mongo = request.app.state.db
    email_clean = data.email.lower().strip()

    user_doc = await mongo[Collections.USERS].find_one({"email": email_clean})
    if not user_doc:
        pwd_context.verify(data.password, DUMMY_PASSWORD_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    db_hash = user_doc.get("password")
    is_valid, new_hash = verify_password_and_upgrade(data.password, db_hash)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    if new_hash:
        await mongo[Collections.USERS].update_one(
            {"_id": user_doc["_id"]}, {"$set": {"password": new_hash}}
        )

    user_id = str(user_doc["_id"])
    await update_login_streak(mongo, user_id)

    # Auto-migrate: create UserAuthMethod for users that existed before this system
    await _ensure_auth_method(mongo, user_id, PROVIDER_PASSWORD, user_id)

    raw_refresh, _ = await _create_session(mongo, user_id, request)
    access_token = _build_access_token(user_id, email_clean)
    auth_methods = await _get_auth_methods(mongo, user_id)
    await _complete_pending_workspace_invites(mongo, user_id, email_clean)
    return _auth_response(user_doc, access_token, raw_refresh, auth_methods)


@router.post("/google/login")
@limiter.limit("5/minute")
async def google_login(request: Request, data: GoogleLoginModel):
    mongo = request.app.state.db

    client_id = Config.GOOGLE_SIGNIN_CLIENT_ID
    if not client_id:
        raise HTTPException(status_code=500, detail="Google Sign-In no configurado.")

    try:
        id_info = google_id_token.verify_oauth2_token(
            data.credential,
            google_requests.Request(),
            client_id,
        )
    except ValueError as e:
        logger.warning("Google ID token inválido: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de Google inválido.")

    google_sub = id_info["sub"]
    email_clean = id_info.get("email", "").lower().strip()
    name = id_info.get("given_name") or id_info.get("name", "")
    picture = id_info.get("picture")

    if not email_clean:
        raise HTTPException(status_code=400, detail="El token de Google no incluye email.")

    user_doc = await mongo[Collections.USERS].find_one({"email": email_clean})

    if user_doc is None:
        referral_code = await generate_unique_referral_code(mongo)
        now = datetime.now(timezone.utc)
        new_user = {
            "name": name,
            "last_name": "",
            "email": email_clean,
            "password": None,
            "avatar": picture,
            "rol": "user",
            "login_streak": 1,
            "code_referrals_uniq": referral_code,
            "referral_code": referral_code,
            "created_at": now,
            "date_registered": now,
            "account_status": "active",
            "is_active": True,
            "plan": "free",
            "integrations": {},
            "preferences": {},
        }
        try:
            res = await mongo[Collections.USERS].insert_one(new_user)
        except DuplicateKeyError:
            user_doc = await mongo[Collections.USERS].find_one({"email": email_clean})
        else:
            new_user["_id"] = res.inserted_id
            user_doc = new_user
        await _create_initial_onboarding(mongo, str(new_user["_id"]), display_name=name)
        logger.info("Nuevo usuario registrado vía Google: %s", email_clean)

    user_id = str(user_doc["_id"])
    await _ensure_auth_method(mongo, user_id, PROVIDER_GOOGLE, google_sub)
    await update_login_streak(mongo, user_id)

    raw_refresh, _ = await _create_session(mongo, user_id, request)
    access_token = _build_access_token(user_id, email_clean)
    auth_methods = await _get_auth_methods(mongo, user_id)
    await _complete_pending_workspace_invites(mongo, user_id, email_clean)
    return _auth_response(user_doc, access_token, raw_refresh, auth_methods)


@router.post("/telegram")
@limiter.limit("5/minute")
async def telegram_login(request: Request, data: TelegramLoginModel):
    """
    Inicia sesión en HyperShifu usando el Telegram Login Widget.
    Distinto de `/api/v1/integrations/telegram/login` (conectar Telegram como app integrada) —
    esto es un método de AUTENTICACIÓN nuevo, paralelo a login con email/password o Google.
    """
    mongo = request.app.state.db

    bot_token = Config.TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise HTTPException(status_code=500, detail="Telegram Login no configurado en el servidor.")

    payload = data.model_dump(exclude_none=True)
    if not verify_telegram_login_hash(payload, bot_token):
        logger.warning("Firma de Telegram Login inválida para id=%s", data.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma de Telegram inválida.")

    now = datetime.now(timezone.utc)
    auth_age_seconds = now.timestamp() - data.auth_date
    if auth_age_seconds > TELEGRAM_AUTH_MAX_AGE_SECONDS or auth_age_seconds < -60:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El payload de Telegram expiró. Reintenta el login.",
        )

    telegram_id = str(data.id)

    auth_method = await mongo[Collections.USER_AUTH_METHODS].find_one(
        {"provider": PROVIDER_TELEGRAM, "provider_user_id": telegram_id}
    )

    if auth_method:
        user_doc = await mongo[Collections.USERS].find_one({"_id": auth_method["user_id"]})
        if not user_doc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado.")
    else:
        # Telegram no siempre entrega email en el payload del widget: no hay campo confiable para
        # reconciliar con una cuenta existente por email, así que el telegram_id es el identificador
        # único. Se genera un email placeholder determinístico (no se le envía nada) para satisfacer
        # el requisito de UserModel.email, con el mismo patrón defensivo anti-duplicado que google_login.
        placeholder_email = f"telegram_{telegram_id}@telegram.hypershifu.local"
        user_doc = await mongo[Collections.USERS].find_one({"email": placeholder_email})
        if user_doc is None:
            referral_code = await generate_unique_referral_code(mongo)
            new_user = {
                "name": data.first_name,
                "last_name": data.last_name or "",
                "email": placeholder_email,
                "password": None,
                "avatar": data.photo_url,
                "rol": "user",
                "login_streak": 1,
                "code_referrals_uniq": referral_code,
                "referral_code": referral_code,
                "created_at": now,
                "date_registered": now,
                "account_status": "active",
                "is_active": True,
                "plan": "free",
                "integrations": {},
                "preferences": {},
            }
            try:
                res = await mongo[Collections.USERS].insert_one(new_user)
            except DuplicateKeyError:
                user_doc = await mongo[Collections.USERS].find_one({"email": placeholder_email})
            else:
                new_user["_id"] = res.inserted_id
                user_doc = new_user
            await _create_initial_onboarding(mongo, str(user_doc["_id"]), display_name=data.first_name)
            logger.info("Nuevo usuario registrado vía Telegram Login: telegram_id=%s", telegram_id)

    user_id = str(user_doc["_id"])
    await _ensure_auth_method(mongo, user_id, PROVIDER_TELEGRAM, telegram_id)
    await update_login_streak(mongo, user_id)

    raw_refresh, _ = await _create_session(mongo, user_id, request)
    access_token = _build_access_token(user_id, user_doc.get("email", ""))
    auth_methods = await _get_auth_methods(mongo, user_id)
    return _auth_response(user_doc, access_token, raw_refresh, auth_methods)


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_token(request: Request, data: RefreshModel):
    mongo = request.app.state.db
    token_hash = _hash_token(data.refresh_token)
    now = datetime.now(timezone.utc)

    session = await mongo[Collections.USER_SESSIONS].find_one({"refresh_token_hash": token_hash})
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido.")
    if session.get("revoked_at") is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión revocada.")
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión expirada.")

    user_id = str(session["user_id"])
    user_doc = await mongo[Collections.USERS].find_one({"_id": session["user_id"]}, {"email": 1})
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado.")

    email = user_doc.get("email", "")

    # Rotation: generate new refresh token, invalidate old session
    new_raw = secrets.token_urlsafe(32)
    new_hash = _hash_token(new_raw)
    await mongo[Collections.USER_SESSIONS].update_one(
        {"_id": session["_id"]},
        {"$set": {"revoked_at": now, "last_used_at": now}},
    )
    new_session_doc = {
        "user_id": session["user_id"],
        "refresh_token_hash": new_hash,
        "device_name": session.get("device_name", "unknown"),
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": session.get("user_agent", ""),
        "created_at": now,
        "last_used_at": now,
        "expires_at": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "revoked_at": None,
    }
    await mongo[Collections.USER_SESSIONS].insert_one(new_session_doc)

    access_token = _build_access_token(user_id, email)
    return {"access_token": access_token, "refresh_token": new_raw}


@router.post("/logout")
async def logout(request: Request, data: LogoutModel, payload: Dict[str, Any] = Depends(verify_token)):
    mongo = request.app.state.db
    token_hash = _hash_token(data.refresh_token)
    now = datetime.now(timezone.utc)
    result = await mongo[Collections.USER_SESSIONS].update_one(
        {
            "refresh_token_hash": token_hash,
            "user_id": ObjectId(payload["user_id"]),
            "revoked_at": None,
        },
        {"$set": {"revoked_at": now}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión no encontrada.")
    return {"success": True, "message": "Sesión cerrada."}


# ── Server-side Google OAuth ─────────────────────────────────────────────────

@router.get("/google/authorize")
async def google_authorize():
    """Inicia el flujo OAuth server-side. Redirige al consentimiento de Google."""
    client_id = Config.GOOGLE_SIGNIN_CLIENT_ID
    redirect_uri = Config.GOOGLE_SIGNIN_REDIRECT_URI
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="Google Sign-In no configurado en el servidor.")

    state = _make_oauth_state()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _GOOGLE_SIGNIN_SCOPES,
        "access_type": "offline",
        "state": state,
        "prompt": "select_account",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Recibe el authorization code de Google, crea/actualiza el usuario y redirige al frontend."""
    frontend_url = Config.FRONTEND_URL

    if error:
        return RedirectResponse(url=f"{frontend_url}/login?error=google_denied")
    if not state or not _verify_oauth_state(state):
        return RedirectResponse(url=f"{frontend_url}/login?error=invalid_state")
    if not code:
        return RedirectResponse(url=f"{frontend_url}/login?error=missing_code")

    client_id = Config.GOOGLE_SIGNIN_CLIENT_ID
    client_secret = Config.GOOGLE_SIGNIN_CLIENT_SECRET
    redirect_uri = Config.GOOGLE_SIGNIN_REDIRECT_URI

    if not client_secret:
        logger.error("[google_callback] GOOGLE_SIGNIN_CLIENT_SECRET no configurado.")
        return RedirectResponse(url=f"{frontend_url}/login?error=server_config")

    # Intercambio de authorization code por tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    token_data = token_resp.json()
    id_token_str = token_data.get("id_token")

    if not id_token_str:
        logger.error("[google_callback] Sin id_token en respuesta de Google: %s", token_data)
        return RedirectResponse(url=f"{frontend_url}/login?error=google_token")

    # Verificar id_token con google-auth
    try:
        id_info = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            client_id,
        )
    except ValueError as e:
        logger.warning("[google_callback] Verificación de ID token fallida: %s", e)
        return RedirectResponse(url=f"{frontend_url}/login?error=google_verify")

    google_sub = id_info["sub"]
    email_clean = id_info.get("email", "").lower().strip()
    name = id_info.get("given_name") or id_info.get("name", "")
    picture = id_info.get("picture")

    if not email_clean:
        return RedirectResponse(url=f"{frontend_url}/login?error=no_email")

    mongo = request.app.state.db
    user_doc = await mongo[Collections.USERS].find_one({"email": email_clean})

    if user_doc is None:
        referral_code = await generate_unique_referral_code(mongo)
        now = datetime.now(timezone.utc)
        new_user = {
            "name": name, "last_name": "", "email": email_clean, "password": None,
            "avatar": picture, "rol": "user", "login_streak": 1,
            "code_referrals_uniq": referral_code, "referral_code": referral_code,
            "created_at": now, "date_registered": now, "account_status": "active",
            "is_active": True, "plan": "free", "integrations": {}, "preferences": {},
        }
        try:
            res = await mongo[Collections.USERS].insert_one(new_user)
        except DuplicateKeyError:
            user_doc = await mongo[Collections.USERS].find_one({"email": email_clean})
        else:
            new_user["_id"] = res.inserted_id
            user_doc = new_user
        await _create_initial_onboarding(mongo, str(user_doc["_id"]), display_name=name)
        logger.info("[google_callback] Nuevo usuario vía Google OAuth: %s", email_clean)

    user_id = str(user_doc["_id"])
    await _ensure_auth_method(mongo, user_id, PROVIDER_GOOGLE, google_sub)
    await update_login_streak(mongo, user_id)

    raw_refresh, _ = await _create_session(mongo, user_id, request)
    access_token_str = _build_access_token(user_id, email_clean)
    await _complete_pending_workspace_invites(mongo, user_id, email_clean)

    qs = urlencode({"at": access_token_str, "rt": raw_refresh})
    return RedirectResponse(url=f"{frontend_url}/onboarding?{qs}")
