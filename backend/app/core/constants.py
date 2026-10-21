class ConnectedAccountStatus:
    """Formal status values for user_connected_accounts.status field."""
    ACTIVE        = "active"        # Token valid and working
    NEEDS_REFRESH = "needs_refresh" # Token expiring soon — auto-refresh will handle it
    EXPIRED       = "expired"       # Token expired, no refresh possible — needs re-auth
    REVOKED       = "revoked"       # Provider rejected token (user revoked access)

    # States the agent considers usable (auth_validator treats these as "connected")
    USABLE = {ACTIVE, NEEDS_REFRESH}


class Collections:
    USERS = 'users'
    PROCESSES = 'processes'
    PROCESSES_TEMP = 'processes_temp'
    CONVERSATIONS = 'conversations'
    OAUTH_VAULT = 'oauth_vault'
    MEMORIES = 'user_memories'
    SCHEDULED_PROCESSES = 'scheduled_processes'
    REWARD_REDEEM = 'reward_redeem'
    REWARDS = 'rewards'
    CHALLENGE_COMPLETIONS = 'challenge_completions'
    POSTS = 'posts'
    USER_CONNECTED_ACCOUNTS = 'user_connected_accounts'
    USER_SECRETS = 'user_secrets'
    INTEGRATIONS = 'integrations'
    MEMORY_CHAT_HISTORY = 'memory_chat_history'
    MEMORY_CHAT_SUMMARIES = 'memory_chat_summaries'
    MEMORY_USERS_PREFERENCES = 'memory_users_preferences'
    LANGGRAPH_PENDING_STATES = 'langgraph_pending_states'
    PASSWORD_RESETS = 'password_resets'
    PROCESOS_TEMP_COLLECTION = 'procesos_temp_collection'
    PROCESS_COLLECTION = 'process_collection'
    USER_AUTH_METHODS = 'user_auth_methods'
    USER_SESSIONS = 'user_sessions'
    USER_PROFILES = 'user_profiles'
    USER_ONBOARDING = 'user_onboarding'
    USER_GOALS = 'user_goals'
    USER_USE_CASES = 'user_use_cases'
    WORKSPACES = 'workspaces'
    WORKSPACE_MEMBERS = 'workspace_members'
    BOARDS = 'boards'
    STRIPE_EVENTS = 'stripe_events'
    CUSTOM_CONNECTOR_REQUESTS = 'custom_connector_requests'
    USER_NOTIFICATIONS = 'user_notifications'
    CRM = 'crm_workspaces'  # un documento por persona: su CRM (app/crm)
    CRM_CONVERSACIONES = 'crm_conversaciones'  # un documento por persona: su historial con Shifu y lo que Shifu recuerda de ella
    CRM_PUNTOS = 'crm_puntos'  # puntos de deshacer del CRM: uno por cambio, los últimos 30 por persona (app/crm/puntos.py)
    CRM_LOGOS = 'crm_logos'  # el logo del negocio (data URL) por id: aparte del CRM para que la imagen no viaje en cada respuesta
    CRM_DESCARGAS = 'crm_descargas'  # archivos que la persona pidió descargar (app/crm/descarga.py); se borran solos a las 24 h
    FUNCTIONS = 'functions'
    FUNCTION_APPS = 'function_apps'
    ACTION_LOG = 'action_log'  # escrituras que el agente ejecuto en una app del usuario (modo act)

    # ── Cognitive Architecture V2 ─────────────────────────────────────────────
    # Agent identity (global, one doc each — cached in process, rarely updated)
    AGENT_IDENTITY   = 'agent_identity'
    AGENT_PERSONALITY = 'agent_personality'
    AGENT_GOALS      = 'agent_goals'
    AGENT_SYSTEM_MODEL = 'agent_system_model'

    # Per-user cognitive state (new architecture)
    USER_STATE           = 'user_state'           # replaces user_summary_context
    USER_WORLD_MODEL     = 'user_world_model'      # structured active knowledge
    WORLD_EVENTS         = 'world_events'          # immutable event log
    AGENT_INTERNAL_STATE = 'agent_internal_state'  # per-user, persists across convs
    OBJECTIVE_STATE      = 'objective_state'       # tracked objectives with steps
    AGENT_LEARNING_MEMORY = 'agent_learning_memory' # longitudinal failure/success patterns

    # World State — live snapshots of the user's external environment (per-user, TTL 24h)
    USER_WORLD_STATE = 'user_world_state'
