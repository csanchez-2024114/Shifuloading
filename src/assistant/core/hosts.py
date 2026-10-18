"""S1 de la auditoría: sin cuentas (AUTH_ENABLED=0), el user_id lo elige el navegador, así que la app solo debe
atender en la propia máquina. Dos defensas, además de TrustedHostMiddleware (TRUSTED_HOSTS):
- al arrancar, con AUTH_ENABLED=0, TRUSTED_HOSTS solo puede tener nombres locales (si no, ConfigError);
- en cada petición, con AUTH_ENABLED=0, la conexión debe haber llegado a una dirección de loopback. Se mira
  scope["server"] (el socket local donde se aceptó la conexión, que el cliente no controla), no la IP del cliente
  ni la cabecera Host: así un `--host 0.0.0.0` no expone la app aunque alguien mande Host: localhost.
Vive en su propio módulo para no sumar constantes a los que fija la huella."""
import ipaddress

from starlette.responses import JSONResponse

# nombres locales para TRUSTED_HOSTS. "testserver" es el host en proceso del TestClient de Starlette: no resuelve a
# ninguna red, y con él una petición real igual tendría que llegar por loopback (comprobación por petición).
LOCAL_NAMES = frozenset({"localhost", "127.0.0.1", "::1", "testserver"})


def non_local_hosts(hosts) -> list[str]:
    """Los de `hosts` que no son locales (un comodín "*" tampoco lo es)."""
    return [h for h in hosts if h.lower() not in LOCAL_NAMES]


def is_loopback_server(server) -> bool:
    """True si scope["server"] es una dirección de loopback (127.0.0.0/8, ::1) o "localhost". Un nombre que no es IP
    no viene de un socket de red (TestClient en proceso, socket de Unix): también cuenta como local. Sin dato
    (None): no local."""
    if not server:
        return False
    host = str(server[0]).strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return True  # no es una IP: no es una conexión de red


class LoopbackOnly:
    """Middleware ASGI: responde 403 a las peticiones HTTP que no llegaron por loopback."""

    def __init__(self, app, message: str):
        self.app = app
        self.message = message

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not is_loopback_server(scope.get("server")):
            await JSONResponse({"detail": self.message}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
