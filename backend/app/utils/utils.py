import datetime
from typing import Optional, Any
from app.core.db_utils import find_user_by_email, canonicalize_email

def get_user_from_db(email: str, cache, mongo) -> Optional[dict]:
    """
    Obtiene un usuario desde caché o MongoDB sin refrescar tokens.
    Usa `find_user_by_email` para mantener compatibilidad legacy/english.
    """
    email_safe = canonicalize_email(email)
    if not email_safe:
        return None
    cached_user = cache.get(email_safe) if cache else None
    if cached_user:
        print(f'[INFO] Usuario {email_safe} encontrado en caché')
        return cached_user
    print(f'[INFO] Usuario {email_safe} no está en caché, consultando MongoDB')
    user = find_user_by_email(mongo.database if hasattr(mongo, 'database') else mongo, email_safe)
    if not user:
        print(f'[ERROR] Usuario {email_safe} no encontrado en MongoDB')
        return None
    if cache:
        cache.set(email_safe, user, timeout=1800)
        print(f'[INFO] Usuario {email_safe} cargado desde MongoDB y cacheado')
    return user
