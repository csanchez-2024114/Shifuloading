"""Error unico de la capa de funciones. Los handlers y la conexion lo lanzan; el runner lo convierte en Result."""
from app.functions.spec import ErrorCode


class FunctionError(Exception):
    def __init__(self, code: ErrorCode, message: str = ""):
        super().__init__(f"{code.value}: {message}" if message else code.value)
        self.code = code
        self.message = message
