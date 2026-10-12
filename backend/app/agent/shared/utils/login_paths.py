"""
Shared OAuth login paths and auth-type classification for all integrations.

Single source of truth — used by auth_validator (to build auth_url) and
catalog_apps_routes (to enrich catalog GET response for the frontend).

Keys use canonical nameApi values (Capa-1 normalization output).
To add a new integration: add its nameApi to LOGIN_PATHS and, if needed,
to APIKEY_APPS or OAUTH1_APPS.
"""

LOGIN_PATHS: dict[str, str] = {
    # Google Suite
    "gmail":           "/auth/google/gmail/login",
    "google_drive":    "/auth/google/drive/login",
    "google_docs":     "/auth/google/docs/login",
    "google_sheets":   "/auth/google/sheets/login",
    "google_slides":   "/auth/google/slides/login",
    "google_calendar": "/auth/google/calendar/login",
    # Gestión de Proyectos
    "asana":    "/auth/asana/login",
    "jira":     "/auth/jira/login",
    "trello":   "/auth/trello/login",
    "monday":   "/auth/monday/login",
    "notion":   "/auth/notion/login",
    "clickup":  "/auth/clickup/login",
    # Comunicación
    "slack":    "/auth/slack/login",
    "discord":  "/auth/discord/login",
    "teams":    "/auth/teams/login",
    "telegram": "/auth/telegram/login",
    # Social Media
    "facebook":  "/auth/facebook/login",
    "instagram": "/auth/instagram/login",
    "twitter":   "/auth/twitter/login",
    "linkedin":  "/auth/linkedin/login",
    "tiktok":    "/auth/tiktok/login",
    "kick":      "/auth/kick/login",
    "threads":   "/auth/threads/login",
    # CRM & Marketing
    "hubspot":    "/auth/hubspot/login",
    "salesforce": "/auth/salesforce/login",
    # mailchimp — desactivada (sin API pública suficiente)
    # Storage & Cloud
    "dropbox":  "/auth/dropbox/login",
    "onedrive": "/auth/onedrive/login",
    "outlook":  "/auth/outlook/login",
    # Delivery
    # ubereats  — desactivada
    # pedidosya — desactivada
}

# Apps that authenticate via API key provided by the user — no OAuth route.
APIKEY_APPS: set[str] = {"openai", "openai_api", "anthropic", "huggingface", "replicate"}

# Apps that use OAuth 1.0 — handled differently in the frontend popup.
OAUTH1_APPS: set[str] = {"trello"}


def get_login_path(name_api: str) -> str | None:
    return LOGIN_PATHS.get(name_api)


def get_auth_type(name_api: str) -> str:
    if name_api in APIKEY_APPS:
        return "apikey"
    if name_api in OAUTH1_APPS:
        return "oauth1"
    if name_api in LOGIN_PATHS:
        return "oauth2"
    return "unknown"
