"""
bigtools_loader — Platform tool loader for all user integrations.

Central instantiation engine for BigTools. Moved from agente_v2 — these are
platform-level tools, not agent-specific.
"""

import logging
import importlib
import inspect
import re
from typing import Any, Optional, Set, Type, List, Dict, Callable
from pydantic import BaseModel, Field
from dataclasses import dataclass
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.tools.global_memory_tool import SavePreferenceInput
from app.tools.tools import (
    SumaArgs,
    Concat2Args,
    Concat3Args,
    JoinArgs,
    RepeatArgs,
    suma_tool,
    concat2_tool,
    concat3_tool,
    join_tool,
    repeat_tool,
    tavily_tool,
    wikipedia_tool,
)

logger = logging.getLogger(__name__)


@dataclass
class BigTool:
    """Standardized tool container for LangGraph injection."""

    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


TOOL_ALIASES: Dict[str, str] = {
    "obtener_contenido_docs": "get_doc_content",
    "buscar_documento_por_nombre": "find_doc_by_name",
    "obtener_listas_documentos": "list_docs_by_names",
    "obtener_info_documento": "get_doc_info",
    "obtener_documento_con_sugerencias": "get_doc_with_suggestions",
    "obtener_comentarios_documento": "get_doc_comments",
    "buscar_documentos_por_autor": "find_docs_by_author",
    "buscar_documentos_por_fecha": "find_docs_by_date_range",
    "crear_documento": "create_doc",
    "insertar_texto_docs": "insert_text_in_doc",
    "cambiar_titulo_doc": "change_doc_title",
    "reemplazar_texto_docs": "replace_doc_text",
    "eliminar_texto_por_contenido": "delete_doc_text_by_content",
    "insertar_tabla_docs": "insert_table_in_doc",
    "llenar_tabla_docs": "fill_table_in_doc",
    "obtener_contenido_slides": "get_presentation_content",
    "obtener_slide_por_nombre": "find_presentation_by_name",
    "obtener_lista_slides": "list_presentations",
    "obtener_info_slide": "get_presentation_info",
    "obtener_comentarios_slide": "get_presentation_comments",
    "obtener_ids_slides": "get_presentation_slide_ids",
    "crear_slide_drive": "create_presentation",
    "crear_slide": "create_presentation",
    "insertar_texto_slides": "insert_text_in_presentation",
    "reemplazar_texto_slide": "replace_text_in_presentation",
    "cambiar_titulo_slide": "change_presentation_title",
    "agregar_diapositiva_slide": "add_slide",
    "duplicar_diapositiva_slide": "duplicate_slide",
    "crear_figura_slide": "create_shape",
    "crear_tabla_slide": "create_table",
    "compartir_slide": "share_presentation",
}


class WikipediaArgs(BaseModel):
    query: str = Field(
        description="Término, nombre de persona, lugar o concepto a buscar en Wikipedia"
    )


static_bigtools: List[BigTool] = [
    BigTool(
        name="tavily",
        description=(
            "Search the internet for real-time or unknown information. Use for: current news, weather, "
            "prices, sports scores, stock data, recent events, people, companies, executives (CEO, CTO, "
            "founders), organizations, products, or any fact the AI is not certain about. "
            "Triggers on: 'investiga', 'busca', 'quién es', 'quién dirige', 'CEO de', 'CTO de', "
            "'fundador de', 'información sobre', 'qué dice internet', 'look up', 'find out', "
            "'who is the CEO', 'who runs', 'research', 'investigate', 'find information about'."
        ),
        tool=tavily_tool,
    ),
    BigTool(
        name="wikipedia",
        description="Busca información enciclopédica, definiciones y conceptos",
        tool=wikipedia_tool,
        args_schema=WikipediaArgs,
    ),
    BigTool(
        name="suma",
        description="Suma dos números",
        tool=suma_tool,
        args_schema=SumaArgs,
    ),
    BigTool(
        name="concat_2",
        description="Concatena dos palabras o textos",
        tool=concat2_tool,
        args_schema=Concat2Args,
    ),
    BigTool(
        name="concat_3",
        description="Concatena tres palabras o textos",
        tool=concat3_tool,
        args_schema=Concat3Args,
    ),
    BigTool(
        name="join_words",
        description="Une varias palabras con un separador",
        tool=join_tool,
        args_schema=JoinArgs,
    ),
    BigTool(
        name="repeat_word",
        description="Repite una palabra varias veces",
        tool=repeat_tool,
        args_schema=RepeatArgs,
    ),
]

_MODULE_CACHE: Dict[str, Optional[Callable]] = {}


def _get_cached_loader(module_path: str, func_name: str) -> Optional[Callable]:
    """Load a dynamic module safely (singleton per module)."""
    cache_key = f"{module_path}.{func_name}"
    if cache_key in _MODULE_CACHE:
        return _MODULE_CACHE[cache_key]
    try:
        mod = importlib.import_module(module_path)
        loader_func = getattr(mod, func_name)
        _MODULE_CACHE[cache_key] = loader_func
        return loader_func
    except (ImportError, ModuleNotFoundError):
        logger.debug(f"[BigtoolsLoader] Module not found: {module_path}. Skipped silently.")
        _MODULE_CACHE[cache_key] = None
        return None
    except AttributeError:
        logger.warning(f"[BigtoolsLoader] Missing function '{func_name}' in {module_path}. Skipped.")
        _MODULE_CACHE[cache_key] = None
        return None
    except Exception as e:
        logger.exception(f"[BigtoolsLoader] Unexpected error importing {module_path}: {e}")
        _MODULE_CACHE[cache_key] = None
        return None


def _normalize_provider(name: str) -> str:
    n = re.sub(r"[\s_\-]", "", name.lower())
    if n.startswith("google") or n in ("gmail", "drive"):
        return "google"
    return n


def get_all_bigtools(
    user_id: str,
    user_email: str,
    db: Optional[AsyncIOMotorDatabase] = None,
    active_accounts: Optional[Dict[str, str]] = None,
    allowed_providers: Optional[Set[str]] = None,
    conversation_id: Optional[str] = None,
) -> List[BigTool]:
    """
    Central tool instantiation engine.
    Uses dynamic dependency injection (Reflection) to support multi-account,
    isolating failures so one broken integration doesn't crash the agent.
    """
    all_tools: List[BigTool] = static_bigtools.copy()
    email_safe = user_email.lower().strip()
    safe_active_accounts = active_accounts or {}
    normalized_allowed = (
        {_normalize_provider(p) for p in allowed_providers}
        if allowed_providers is not None
        else None
    )

    def load_integration(loader_func: Callable, name: str) -> List[BigTool]:
        if not loader_func:
            return []
        try:
            sig = inspect.signature(loader_func)
            kwargs = {}
            if "user_id" in sig.parameters:
                kwargs["user_id"] = user_id
            if "db" in sig.parameters:
                kwargs["db"] = db
            if "active_accounts" in sig.parameters:
                kwargs["active_accounts"] = safe_active_accounts
            if "conversation_id" in sig.parameters:
                kwargs["conversation_id"] = conversation_id
            tools_list = loader_func(user_email=email_safe, **kwargs)
            return tools_list if isinstance(tools_list, list) else []
        except AttributeError as ae:
            logger.warning(f"[BigtoolsLoader] Integration '{name}' attribute error: {str(ae)}. Skipping.")
            return []
        except Exception as e:
            logger.exception(f"[BigtoolsLoader] Structural failure building tools for '{name}' ({email_safe}): {str(e)}")
            return []

    _saas_integrations = [
        ("app.agent.shared.tools.providers.gmail_bigtools",       "get_gmail_bigtools",       "Gmail"),
        ("app.agent.shared.tools.providers.drive_bigtools",        "get_drive_bigtools",       "Drive"),
        ("app.agent.shared.tools.providers.docs_bigtools",         "get_docs_bigtools",        "Google Docs"),
        ("app.agent.shared.tools.providers.sheets_bigtools",       "get_sheets_bigtools",      "Google Sheets"),
        ("app.agent.shared.tools.providers.slides_bigtools",       "get_slides_bigtools",      "Google Slides"),
        ("app.agent.shared.tools.providers.dropBox_bigtools",      "get_dropbox_bigtools",     "Dropbox"),
        ("app.tools.bigtools.onedrive_bigtools",     "get_onedrive_bigtools",    "OneDrive"),
        ("app.agent.shared.tools.providers.clickup_bigtools",      "get_clickup_bigtools",     "ClickUp"),
        ("app.agent.shared.tools.providers.asana_bigtools",        "get_asana_bigtools",       "Asana"),
        ("app.tools.bigtools.trello_bigtools",       "get_trello_bigtools",      "Trello"),
        ("app.tools.bigtools.monday_bigtools",       "get_monday_bigtools",      "Monday"),
        ("app.tools.bigtools.jira_bigtools",         "get_jira_bigtools",        "Jira"),
        ("app.tools.bigtools.instagram_bigtools",    "get_instagram_bigtools",   "Instagram"),
        ("app.agent.shared.tools.providers.facebook_bigtools",     "get_facebook_bigtools",    "Facebook"),
        ("app.tools.bigtools.tiktok_bigtools",       "get_tiktok_bigtools",      "TikTok"),
        ("app.tools.bigtools.twitter_bigtools",      "get_twitter_bigtools",     "X (Twitter)"),
        ("app.tools.bigtools.threads_bigtools",      "get_threads_bigtools",     "Threads"),
        ("app.tools.bigtools.linkedin_bigtools",     "get_linkedin_bigtools",    "LinkedIn"),
        ("app.tools.bigtools.onlyfans_bigtools",     "get_onlyfans_bigtools",    "OnlyFans"),
        ("app.tools.bigtools.kick_bigtools",         "get_kick_bigtools",        "Kick"),
        ("app.tools.bigtools.whatsapp_bigtools",     "get_whatsapp_bigtools",    "WhatsApp Business"),
        ("app.tools.bigtools.slack_bigtools",        "get_slack_bigtools",       "Slack"),
        ("app.tools.bigtools.discord_bigtools",      "get_discord_bigtools",     "Discord"),
        ("app.tools.bigtools.teams_bigtools",        "get_teams_bigtools",       "Microsoft Teams"),
        ("app.tools.bigtools.telegram_bigtools",     "get_telegram_bigtools",    "Telegram"),
        ("app.tools.bigtools.outlook_bigtools",      "get_outlook_bigtools",     "Outlook"),
        ("app.agent.shared.tools.providers.hubspot_bigtools",      "get_hubspot_bigtools",     "HubSpot"),
        ("app.tools.bigtools.salesforce_bigtools",   "get_salesforce_bigtools",  "Salesforce"),
        ("app.tools.bigtools.brevo_bigtools",        "get_brevo_bigtools",       "Brevo"),
        ("app.tools.bigtools.mailchimp_bigtools",    "get_mailchimp_bigtools",   "Mailchimp"),
        ("app.tools.bigtools.notion_bigtools",       "get_notion_bigtools",      "Notion"),
        ("app.tools.bigtools.ubereats_bigtools",     "get_ubereats_bigtools",    "Uber Eats"),
        ("app.tools.bigtools.pedidosya_bigtools",    "get_pedidosya_bigtools",   "Pedidos Ya"),
    ]
    for module_path, func_name, integration_name in _saas_integrations:
        if (
            normalized_allowed is not None
            and _normalize_provider(integration_name) not in normalized_allowed
        ):
            continue
        loader_func = _get_cached_loader(module_path, func_name)
        if loader_func:
            all_tools.extend(load_integration(loader_func, integration_name))

    _core_integrations = [
        ("app.agent.shared.tools.providers.memory_search_bigtools",        "get_memory_search_bigtools",       "Memory Search"),
        ("app.agent.shared.tools.providers.conversation_context_bigtools", "get_conversation_context_bigtools", "Conversation Context"),
        ("app.agent.shared.tools.providers.scheduleProcessTool_bigtools",  "get_schedule_bigtools",            "Schedule Process"),
        ("app.agent.shared.tools.providers.procesos_bigtools",             "get_process_bigtools",             "Process Management"),
        ("app.tools.bigtools.ai_analysis_bigtools",          "get_ai_analysis_bigtools",         "AI Analysis"),
        ("app.tools.bigtools.file_tool_bigtools",            "get_file_bigtools",                "File Tool"),
        ("app.agent.shared.tools.providers.scheduler_bigtools",            "get_scheduler_bigtools",           "Scheduler"),
        ("app.agent.shared.tools.providers.workflow_bigtools",             "get_workflow_bigtools",            "Workflows"),
        ("app.agent.shared.tools.providers.ai_bigtools",                   "get_ai_bigtools",                  "AI Processing"),
    ]
    for module_path, func_name, integration_name in _core_integrations:
        loader_func = _get_cached_loader(module_path, func_name)
        if loader_func:
            all_tools.extend(load_integration(loader_func, integration_name))

    try:
        from app.tools.global_memory_tool import MemoryUserPreferencesToolProvider

        provider_sig = inspect.signature(MemoryUserPreferencesToolProvider.__init__)
        provider_kwargs = {}
        if "db" in provider_sig.parameters:
            provider_kwargs["db"] = db
        if "user_id" in provider_sig.parameters:
            provider_kwargs["user_id"] = user_id
        if "active_accounts" in provider_sig.parameters:
            provider_kwargs["active_accounts"] = safe_active_accounts
        prefs_provider = MemoryUserPreferencesToolProvider(user_email=email_safe, **provider_kwargs)
        memory_pref_tools = [
            BigTool(
                name="memory_users_preferences_save",
                description="HERRAMIENTA PARA **GUARDAR O ESTABLECER** nuevas preferencias del usuario.\n✓ USA ESTA HERRAMIENTA CUANDO el usuario QUIERA:\n  - Guardar una preferencia nueva: 'mi idioma favorito es inglés'\n  - Establecer una configuración: 'prefiero respuestas cortas'\n  - Cambiar un ajuste: 'configura mi tono a formal'\n  - Expresar un gusto: 'me gusta el color azul'\n  - Guardar información personal: 'mi nombre es Juan'\n\n✗ NO USAR PARA:\n  - Consultar preferencias existentes\n  - Preguntar qué preferencias tiene el usuario\n  - Ver configuraciones guardadas\n\nPalabras clave: guardar, establecer, configurar, cambiar, actualizar, me gusta, prefiero, mi favorito es",
                args_schema=SavePreferenceInput,
                tool=prefs_provider.get_tool_save_preference(),
            ),
            BigTool(
                name="memory_users_preferences_get",
                description="HERRAMIENTA PARA **CONSULTAR O LEER** las preferencias guardadas del usuario.\n✓ USA ESTA HERRAMIENTA CUANDO el usuario QUIERA:\n  - Ver sus preferencias: 'muéstrame mis preferencias'\n  - Consultar configuraciones: 'qué preferencias tengo?'\n  - Preguntar por ajustes específicos: 'qué idioma tengo configurado?'\n  - Solicitar información guardada: 'dime mis preferencias'\n  - Revisar gustos previos: 'cómo tengo configurado el tono?'\n\n✗ NO USAR PARA:\n  - Guardar nuevas preferencias\n  - Establecer configuraciones\n  - Cambiar preferencias existentes\n\nPalabras clave: consultar, ver, mostrar, obtener, qué preferencias, dime mis, cómo tengo, enséñame, listar",
                tool=prefs_provider.get_tool_get_preferences(),
            ),
        ]
        all_tools.extend(memory_pref_tools)
    except Exception as e:
        logger.exception(f"[BigtoolsLoader] Failed to init memory preference tools for {email_safe}: {str(e)}")

    logger.debug(f"[BigtoolsLoader] Total tools loaded for {email_safe}: {len(all_tools)}")
    return all_tools


def get_tool_names(
    user_email: Optional[str] = None,
    db: Optional[AsyncIOMotorDatabase] = None,
    active_accounts: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Lightweight — returns only tool names (useful for validation)."""
    if not user_email:
        return [bt.name for bt in static_bigtools]
    bigtools = get_all_bigtools(user_email, db=db, active_accounts=active_accounts)
    return [bt.name for bt in bigtools]


bigtools = static_bigtools


def bigtool_to_lc(bt) -> Any:
    """Convert a BigTool dataclass into a LangChain BaseTool (StructuredTool)."""
    from langchain_core.tools import BaseTool, StructuredTool

    if not bt:
        return None
    tool_obj = getattr(bt, "tool", None)
    args_schema = getattr(bt, "args_schema", None)

    try:
        if isinstance(tool_obj, BaseTool):
            return tool_obj
    except Exception:
        pass

    try:
        if inspect.iscoroutinefunction(tool_obj):
            return StructuredTool.from_function(
                coroutine=tool_obj,
                name=getattr(bt, "name", "unknown"),
                description=getattr(bt, "description", ""),
                args_schema=args_schema,
            )
        if callable(tool_obj):
            async def _wrap(*args, **kwargs):
                return tool_obj(*args, **kwargs)

            return StructuredTool.from_function(
                coroutine=_wrap,
                name=getattr(bt, "name", "unknown"),
                description=getattr(bt, "description", ""),
                args_schema=args_schema,
            )
    except Exception as exc:
        logger.warning(f"[BigtoolsLoader] Failed to convert BigTool {getattr(bt, 'name', None)}: {exc}")
    return None
