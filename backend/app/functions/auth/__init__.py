from app.functions.auth import strategies  # noqa: F401  (importarlo registra las estrategias)
from app.functions.auth.base import (  # noqa: F401
    AuthStrategy, Credentials, RequestParts, get_strategy, implemented_types, register_auth,
)
