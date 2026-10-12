import redis
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from pymongo.errors import PyMongoError
from app.utils.utils import get_user_from_db

router = APIRouter(tags=["Messages"])
mongo = None
cache = None
refresh_functions = None


def safe_cache_get(key, default=None):
    try:
        return cache.get(key)
    except (
        redis.exceptions.TimeoutError,
        redis.exceptions.ConnectionError,
        Exception,
    ) as e:
        print(f"[WARNING] Cache error getting {key}: {e}")
        return default


def safe_cache_set(key, value, timeout=1800):
    try:
        cache.set(key, value, timeout=timeout)
        return True
    except (
        redis.exceptions.TimeoutError,
        redis.exceptions.ConnectionError,
        Exception,
    ) as e:
        print(f"[WARNING] Cache error setting {key}: {e}")
        return False


def should_refresh_tokens(email):
    last_refresh_key = f"last_refresh_{email}"
    last_refresh = safe_cache_get(last_refresh_key)
    current_time = datetime.utcnow()
    if last_refresh is None:
        return True
    try:
        last_refresh_time = datetime.fromtimestamp(last_refresh)
        return current_time - last_refresh_time >= timedelta(minutes=30)
    except Exception:
        return True


def get_user_with_refreshed_tokens(email):
    try:
        user = safe_cache_get(email)
        if not user:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return None
            safe_cache_set(email, user, timeout=1800)
        if not should_refresh_tokens(email):
            return user
        get_refresh_tokens_from_db = refresh_functions["get_refresh_tokens_from_db"]
        refresh_tokens_func = refresh_functions["refresh_tokens"]
        refresh_tokens_dict = get_refresh_tokens_from_db(email)
        if not refresh_tokens_dict:
            safe_cache_set(f"last_refresh_{email}", datetime.utcnow().timestamp())
            return user
        integrations = user.get("integrations", {})
        tokens_to_refresh = {
            service: refresh_tokens_dict[service]
            for service in integrations
            if service in refresh_tokens_dict
            and integrations[service].get("refresh_token") not in (None, "n/a")
        }
        if not tokens_to_refresh:
            safe_cache_set(f"last_refresh_{email}", datetime.utcnow().timestamp())
            return user
        refreshed_tokens, errors = refresh_tokens_func(tokens_to_refresh, email)
        if refreshed_tokens:
            user = get_user_from_db(email, cache, mongo)
            safe_cache_set(f"last_refresh_{email}", datetime.utcnow().timestamp())
            return user
        safe_cache_set(f"last_refresh_{email}", datetime.utcnow().timestamp())
        return user
    except Exception as e:
        print(f"[ERROR] Token refresh error for {email}: {e}")
        return None


@router.get("/latest")
def get_latest_messages(email: str = Query(..., description="Email del usuario")):
    email = email.strip()
    try:
        user = safe_cache_get(email)
        if not user:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
            safe_cache_set(email, user)
    except Exception:
        user = get_user_from_db(email, cache, mongo)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
    chats = user.get("chats", [])
    latest_messages = []
    try:
        for chat in chats:
            messages = chat.get("messages", [])
            if not messages:
                continue
            latest_message = max(
                messages, key=lambda m: m.get("timestamp", datetime.min)
            )
            unread_count = sum(
                (
                    1
                    for msg in messages
                    if msg.get("source") == "notification"
                    and (not msg.get("read", False))
                )
            )
            notification_icon = None
            if unread_count > 0:
                notification_icon = {
                    "type": "circle",
                    "color": "blue",
                    "count": unread_count,
                }
            latest_messages.append(
                {
                    "chat_id": str(chat.get("_id", "")),
                    "chat_name": chat.get("name", "Unnamed Chat"),
                    "content": latest_message.get("content", ""),
                    "timestamp": latest_message.get("timestamp", datetime.utcnow()),
                    "role": latest_message.get("role", "unknown"),
                    "is_notification": latest_message.get("source") == "notification",
                    "notification_icon": notification_icon,
                    "unread_count": unread_count,
                }
            )
        latest_messages.sort(key=lambda x: x["timestamp"], reverse=True)
        if not latest_messages:
            raise HTTPException(status_code=404, detail="No hay mensajes")
        return {
            "success": "Últimos mensajes obtenidos",
            "messages": latest_messages,
            "count": len(latest_messages),
        }
    except PyMongoError:
        raise HTTPException(status_code=500, detail="Error de base de datos")
    except Exception:
        raise HTTPException(status_code=500, detail="Error inesperado")