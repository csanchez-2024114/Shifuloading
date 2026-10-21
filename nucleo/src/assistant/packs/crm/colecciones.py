"""Nombres de las colecciones de Mongo que usa el CRM. Los mismos que `app.core.constants.Collections` del producto, para que el
pack no dependa del backend de Carlos (las dos bases comparten los datos)."""


class Collections:
    USERS = 'users'
    USER_NOTIFICATIONS = 'user_notifications'
    CRM = 'crm_workspaces'  # un documento por persona: su CRM
    CRM_CONVERSACIONES = 'crm_conversaciones'  # su historial con Shifu y lo que Shifu recuerda de ella
    CRM_PUNTOS = 'crm_puntos'  # puntos de deshacer: uno por cambio, los últimos 30 por persona (puntos.py)
    CRM_LOGOS = 'crm_logos'  # el logo del negocio (data URL) por id, aparte del CRM
    CRM_DESCARGAS = 'crm_descargas'  # archivos que la persona pidió descargar (descarga.py); se borran solos a las 24 h
    CRM_DOCUMENTOS = 'crm_documentos'  # documentos con número (documento.py): la foto congelada de cada recibo, orden, cotización…
