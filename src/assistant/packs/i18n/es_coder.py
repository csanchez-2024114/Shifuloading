"""Textos al usuario del agente codificador, en español: tarjetas de aprobación y avisos de arranque. Se suman encima
de es.TEXTS en el catálogo del perfil coder; el perfil por defecto no los usa."""

TEXTS = {
    # tarjetas de aprobación (la descripción se arma con los datos reales del proyecto)
    "coder.card_restore": ("Restaurar «{name}» a la versión {version} ({files} archivos). Se crea la versión {new} con "
                           "esos archivos; la versión actual ({current}) queda en el historial."),
    "coder.card_delete_project": ("Borrar el proyecto «{name}» con sus {files} archivos y {versions} versiones. No se "
                                  "puede deshacer."),
    "coder.card_unknown_project": ("El proyecto {project_id} no existe o no es tuyo: si apruebas, la herramienta no "
                                   "hará nada."),
    "coder.card_unknown_version": ("La versión {version} de «{name}» no existe: si apruebas, la herramienta no hará "
                                   "nada."),
    # rutas del dueño
    "coder.project_not_found": "No existe ese proyecto.",
    # arranque (core/coder/routes.py tiene el mismo texto de respaldo)
    "startup.coder_profile_needs_coder": "El perfil coder necesita CODER_ENABLED=1 (y AUTH_ENABLED=1).",
    "startup.coder_flag_needs_coder": ("CODER_DATA_ENABLED, CODER_SHARING_ENABLED y CODER_PUBLIC_WRITE_ENABLED "
                                       "necesitan CODER_ENABLED=1."),
    "startup.coder_needs_auth": ("CODER_ENABLED=1 necesita AUTH_ENABLED=1 y la base de negocio (APP_MONGODB_URI y "
                                 "APP_MONGODB_DB): los proyectos son por usuario y el usuario sale de la sesión."),
    "startup.coder_public_write_needs": ("CODER_PUBLIC_WRITE_ENABLED=1 necesita también CODER_DATA_ENABLED=1 y "
                                         "CODER_SHARING_ENABLED=1."),
    "startup.coder_bigtool": ("CODER_ENABLED=1 no funciona con USE_BIGTOOL=1: bigtool no aplica las aprobaciones del "
                              "perfil (borrar, restaurar y compartir proyectos las necesitan)."),
    "startup.coder_sandbox_origin": ("CODER_SANDBOX_ORIGIN debe ser un origen http(s) sin ruta, p. ej. "
                                     "http://127.0.0.2:8100 (es «{origin}»)."),
    "startup.coder_sandbox_host_shared": ("El host de CODER_SANDBOX_ORIGIN ({host}) también está en TRUSTED_HOSTS: la "
                                          "vista previa y lo publicado deben servirse desde otro host que la app (las "
                                          "cookies no se separan por puerto). Usa en TRUSTED_HOSTS solo el host de la "
                                          "app (p. ej. 127.0.0.1) u otro host para el sandbox."),
}
