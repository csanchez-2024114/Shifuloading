import logging
import os
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from config import Config
logger = logging.getLogger(__name__)

# IPs de los proxies propios (balanceador). Solo si la peticion llega desde uno de ellos se cree X-Forwarded-For; si no,
# cualquier cliente podia mandar el encabezado con una IP inventada y saltarse el limite (o bloquear a otro).
_TRUSTED = {ip.strip() for ip in os.getenv('TRUSTED_PROXY_IPS', '').split(',') if ip.strip()}


def get_real_ip(request: Request) -> str:
    """IP del cliente. Detras de un proxy de confianza toma, de derecha a izquierda, la primera IP de X-Forwarded-For
    que no sea de un proxy propio (la de la izquierda la escribe el cliente y se puede falsificar)."""
    peer = get_remote_address(request)
    if peer not in _TRUSTED:
        return peer
    hops = [h.strip() for h in (request.headers.get('X-Forwarded-For') or '').split(',') if h.strip()]
    for hop in reversed(hops):
        if hop not in _TRUSTED:
            return hop
    return (request.headers.get('X-Real-IP') or peer).strip()


storage_uri = Config.REDIS_URL if Config.REDIS_URL else 'memory://'
# RATE_LIMIT_ENABLED=false solo en local: scripts/eval_agent.py registra un usuario por conversacion (3/min no alcanza).
limiter = Limiter(enabled=os.getenv('RATE_LIMIT_ENABLED', 'true').lower() != 'false', key_func=get_real_ip, storage_uri=storage_uri, strategy='moving-window', in_memory_fallback_enabled=True, storage_options={'socket_timeout': 2, 'socket_connect_timeout': 2})
logger.info(f" Rate Limiter inicializado. Storage: {('Redis' if Config.REDIS_URL else 'Memory')}")
