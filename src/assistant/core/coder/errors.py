"""Error único del codificador: `code` identifica el caso (las herramientas lo traducen a "Not run: ..." para el
modelo y las rutas a un aviso en español) y `values` lleva sus datos."""


class CoderError(Exception):
    def __init__(self, code: str, **values):
        super().__init__(code)
        self.code = code
        self.values = values
