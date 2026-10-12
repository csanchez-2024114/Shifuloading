"""Integrations helpers.

Centraliza la resolución de rutas de login/oauth para integraciones.
Usar `get_login_path(integration_name)` desde handlers y tools en lugar
de repetir un `login_map` en varios sitios.
"""

from typing import Optional

_LOGIN_MAP: dict[str, str] = {
    "gmail": "/auth/google/gmail/login",
    "google calendar": "/auth/google/calendar/login",
    "google_calendar": "/auth/google/calendar/login",
    "google drive": "/auth/google/drive/login",
    "google_drive": "/auth/google/drive/login",
    "google docs": "/auth/google/docs/login",
    "google_docs": "/auth/google/docs/login",
    "google sheets": "/auth/google/sheets/login",
    "google_sheets": "/auth/google/sheets/login",
    "google slides": "/auth/google/slides/login",
    "google_slides": "/auth/google/slides/login",
    "jira": "/auth/jira/login",
    "trello": "/auth/trello/login",
    "monday": "/auth/monday/login",
    "notion": "/auth/notion/login",
    "clickup": "/auth/clickup/login",
    "slack": "/auth/slack/login",
    "discord": "/auth/discord/login",
    "microsoft teams": "/auth/teams/login",
    "teams": "/auth/teams/login",
    "telegram": "/auth/telegram/login",
    "facebook": "/auth/facebook/login",
    "instagram": "/auth/instagram/login",
    "twitter": "/auth/twitter/login",
    "twitter/x": "/auth/twitter/login",
    "linkedin": "/auth/linkedin/login",
    "tiktok": "/auth/tiktok/login",
    "kick": "/auth/kick/login",
    "threads": "/auth/threads/login",
    "hubspot": "/auth/hubspot/login",
    "salesforce": "/auth/salesforce/login",
    "mailchimp": "/auth/mailchimp/login",
    "dropbox": "/auth/dropbox/login",
    "onedrive": "/auth/onedrive/login",
    "outlook": "/auth/outlook/login",
    "ubereats": "/auth/ubereats/login",
    "pedidosya": "/auth/pedidosya/login",
}


def _normalize(name: str) -> str:
    return (name or "").strip().lower()


def get_login_path(integration: str) -> Optional[str]:
    """Devuelve la ruta relativa de login para una integración.

    - Primero intenta una coincidencia exacta en el mapa.
    - Si no hay coincidencia exacta, intenta búsqueda por substring
      sobre las claves del mapa.
    """
    if not integration:
        return None
    key = _normalize(integration)
    if key in _LOGIN_MAP:
        return _LOGIN_MAP[key]
    # substring match
    for k, v in _LOGIN_MAP.items():
        if k in key:
            return v
    return None
