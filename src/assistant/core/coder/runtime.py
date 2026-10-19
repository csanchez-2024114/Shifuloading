"""Los proyectos del codificador de este proceso. create_app los fija al instalar el codificador
(install_coder_routes) y las herramientas del perfil los buscan aquí al ejecutarse: el agente se construye antes que
la app, así que no puede recibirlos como argumento. Un proceso sirve una sola app (un worker de uvicorn)."""
_current = None


def set_current(projects) -> None:
    global _current
    _current = projects


def current():
    """Los proyectos activos, o None si el codificador no está instalado en este proceso."""
    return _current
