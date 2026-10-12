"""Lo que recibe un handler: la conexion ya lista y poco mas. Nunca el vault ni el secreto."""
from dataclasses import dataclass
from typing import Optional

from app.functions.connections import Connection


@dataclass
class Context:
    user_id: str
    conn: Connection
    account_id: Optional[str]
    dry_run: bool = False
