"""
Script para crear índices DB necesarios en entornos donde no se ejecute el arranque de la app.
Ejecutar desde el entorno virtual del proyecto:

python scripts/create_indexes.py

Este script usa PyMongo (sincrónico). Asegúrate de tener instalado `pymongo`.
"""
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import OperationFailure
from config import Config
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def create_index_safe(collection, keys, name, **kwargs):
    """Crea un índice ignorando si ya existe. Reporta si hay conflicto de datos."""
    try:
        collection.create_index(keys, name=name, **kwargs)
        logger.info("  ✓ Índice '%s' asegurado", name)
    except OperationFailure as e:
        if "already exists" in str(e) or "IndexKeySpecsConflict" in str(e):
            logger.info("  - Índice '%s' ya existía, sin cambios", name)
        elif "duplicate key" in str(e).lower():
            logger.error(
                "  ✗ Índice '%s' NO creado: existen documentos duplicados en la colección. "
                "Limpia los duplicados antes de aplicar el índice único.",
                name,
            )
        else:
            logger.error("  ✗ Error en índice '%s': %s", name, e)


def main():
    uri = Config.MONGO_URI
    db_name = Config.MONGO_DB_NAME
    client = MongoClient(uri)
    db = client[db_name]

    try:
        logger.info("=== Creando índices en '%s' ===", db_name)

        # --- agente_v2: agente_v2_chat_context ---
        col = db["agente_v2_chat_context"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("conversation_id", ASCENDING)],
            name="idx_agente_v2_chat_context_unique",
            unique=True,
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("updated_at", ASCENDING)],
            name="idx_agente_v2_chat_context_by_updated",
        )

        # --- agente_v2: user_daily_diary ---
        col = db["user_daily_diary"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("date", ASCENDING)],
            name="idx_user_daily_diary_by_date",
        )

        # --- agente_v2: user_global_memory ---
        col = db["user_global_memory"]
        create_index_safe(
            col,
            [("user_id", ASCENDING)],
            name="idx_user_global_memory_unique",
            unique=True,
        )

        # --- agente_v2: user_global_memory_chunks ---
        col = db["user_global_memory_chunks"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("chunk_index", ASCENDING)],
            name="idx_user_global_memory_chunks_unique",
            unique=True,
        )

        # --- agente_v2: user_semantic_memory ---
        col = db["user_semantic_memory"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("key", ASCENDING)],
            name="idx_user_semantic_memory_unique",
            unique=True,
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("mention_count", ASCENDING), ("last_seen_at", ASCENDING)],
            name="idx_user_semantic_memory_ranking",
        )

        # --- agente_v2: user_discovery_session ---
        col = db["user_discovery_session"]
        create_index_safe(
            col,
            [("user_id", ASCENDING)],
            name="idx_user_discovery_session_unique",
            unique=True,
        )

        # --- agente_v2: workflow_sessions ---
        col = db["workflow_sessions"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("status", ASCENDING)],
            name="idx_workflow_sessions_by_status",
        )

        # --- agente_v2: workflows ---
        col = db["workflows"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("conversation_id", ASCENDING)],
            name="idx_workflows_unique",
            unique=True,
            sparse=True,
        )

        # --- langgraph_pending_states ---
        col = db["langgraph_pending_states"]
        create_index_safe(col, [("expires_at", ASCENDING)],
                          name="idx_langgraph_pending_states_expires_at",
                          expireAfterSeconds=0)
        create_index_safe(col, [("resume_token", ASCENDING)],
                          name="idx_langgraph_pending_states_resume_token",
                          unique=True)

        # --- user_connected_accounts ---
        # Índice único: un documento por (usuario, proveedor, cuenta).
        # Permite multicuenta: misma app con distintos account_id → documentos separados.
        # Previene duplicados por race conditions.
        col = db["user_connected_accounts"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("provider", ASCENDING), ("account_id", ASCENDING)],
            name="idx_user_connected_accounts_unique",
            unique=True,
        )
        # Índice de búsqueda: todas las cuentas de un usuario
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("provider", ASCENDING)],
            name="idx_user_connected_accounts_by_provider",
        )

        # --- agente_v2: agente_v2_working_memory (24h TTL) ---
        col = db["agente_v2_working_memory"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("conversation_id", ASCENDING)],
            name="idx_agente_v2_working_memory_unique",
            unique=True,
        )
        create_index_safe(
            col,
            [("expires_at", ASCENDING)],
            name="idx_agente_v2_working_memory_ttl",
            expireAfterSeconds=0,
        )

        # --- agente_v2: user_active_goals ---
        col = db["user_active_goals"]
        create_index_safe(
            col,
            [("goal_id", ASCENDING)],
            name="idx_user_active_goals_goal_id",
            unique=True,
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("status", ASCENDING)],
            name="idx_user_active_goals_by_status",
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("priority", ASCENDING), ("created_at", ASCENDING)],
            name="idx_user_active_goals_ranking",
        )

        # --- agente_v2: user_pending_tasks ---
        col = db["user_pending_tasks"]
        create_index_safe(
            col,
            [("task_id", ASCENDING)],
            name="idx_user_pending_tasks_task_id",
            unique=True,
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("status", ASCENDING)],
            name="idx_user_pending_tasks_by_status",
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("priority", ASCENDING), ("created_at", ASCENDING)],
            name="idx_user_pending_tasks_ranking",
        )

        # --- agente_v2: memory_retrieval_events (observability trace) ---
        col = db["memory_retrieval_events"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("turn_at", ASCENDING)],
            name="idx_memory_retrieval_events_by_turn",
        )
        create_index_safe(
            col,
            [("turn_at", ASCENDING)],
            name="idx_memory_retrieval_events_ttl",
            expireAfterSeconds=30 * 24 * 3600,  # auto-delete after 30 days
        )

        # --- audit_events: security audit log ---
        col = db["audit_events"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("timestamp", -1)],
            name="idx_audit_events_by_user_ts",
        )
        create_index_safe(
            col,
            [("action", ASCENDING), ("timestamp", -1)],
            name="idx_audit_events_by_action",
        )
        # Auto-delete audit events after 365 days (compliance window)
        create_index_safe(
            col,
            [("timestamp", ASCENDING)],
            name="idx_audit_events_ttl",
            expireAfterSeconds=365 * 24 * 3600,
        )

        # --- intent_outcomes: user+timestamp for action-history queries ---
        col = db["intent_outcomes"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("timestamp", -1)],
            name="idx_intent_outcomes_by_user_ts",
        )

        # --- user_semantic_memory: user+status for memory correction queries ---
        col = db["user_semantic_memory"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("status", ASCENDING)],
            name="idx_user_semantic_memory_by_status",
        )

        # --- workflows: webhook_token unique (sparse — only present on webhook-type workflows) ---
        col = db["workflows"]
        create_index_safe(
            col,
            [("webhook_token", ASCENDING)],
            name="idx_workflows_webhook_token",
            unique=True,
            sparse=True,
        )

        # --- webhook_events: audit log with 90-day TTL ---
        col = db["webhook_events"]
        create_index_safe(
            col,
            [("workflow_id", ASCENDING), ("received_at", ASCENDING)],
            name="idx_webhook_events_by_workflow",
        )
        create_index_safe(
            col,
            [("received_at", ASCENDING)],
            name="idx_webhook_events_ttl",
            expireAfterSeconds=90 * 24 * 3600,
        )

        # --- tool_outcome_log: per-call success/failure for circuit breaker + success rates ---
        col = db["tool_outcome_log"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("action", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_tool_outcome_user_action_ts",
        )
        create_index_safe(
            col,
            [("action", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_tool_outcome_action_ts",
        )
        create_index_safe(
            col,
            [("ttl", ASCENDING)],
            name="idx_tool_outcome_ttl",
            expireAfterSeconds=0,  # TTL field stores exact expiry datetime (30d from creation)
        )

        # --- agent_learning_memory: per-user synthesized failure/success patterns ---
        col = db["agent_learning_memory"]
        create_index_safe(
            col,
            [("user_id", ASCENDING)],
            name="idx_agent_learning_memory_user",
            unique=True,
        )
        create_index_safe(
            col,
            [("last_synthesized_at", DESCENDING)],
            name="idx_agent_learning_memory_last_synth",
        )

        # --- user_world_state: live snapshots of user's external environment ---
        col = db["user_world_state"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("category", ASCENDING), ("key", ASCENDING)],
            name="idx_user_world_state_unique",
            unique=True,
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("last_synced", DESCENDING)],
            name="idx_user_world_state_by_synced",
        )
        create_index_safe(
            col,
            [("ttl", ASCENDING)],
            name="idx_user_world_state_ttl",
            expireAfterSeconds=0,  # TTL field stores exact expiry datetime (24h)
        )

        # --- agent_bus_messages: inter-agent message queue ---
        col = db["agent_bus_messages"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("conversation_id", ASCENDING), ("status", ASCENDING)],
            name="idx_agent_bus_pending",
        )
        create_index_safe(
            col,
            [("expires_at", ASCENDING)],
            name="idx_agent_bus_ttl",
            expireAfterSeconds=0,
        )

        # --- node_fault_log: fault isolation audit trail ---
        col = db["node_fault_log"]
        create_index_safe(
            col,
            [("node", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_node_fault_log_by_node",
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_node_fault_log_by_user",
        )
        create_index_safe(
            col,
            [("timestamp", ASCENDING)],
            name="idx_node_fault_log_ttl",
            expireAfterSeconds=30 * 24 * 3600,  # auto-delete after 30 days
        )

        # --- Claudio evaluation framework ---
        col = db["evaluation_cases"]
        create_index_safe(col, [("test_id", ASCENDING)], name="idx_eval_cases_test_id", unique=True)
        create_index_safe(col, [("category", ASCENDING)], name="idx_eval_cases_category")
        create_index_safe(col, [("severity", ASCENDING)], name="idx_eval_cases_severity")

        col = db["evaluation_runs"]
        create_index_safe(col, [("run_id", ASCENDING)], name="idx_eval_runs_run_id", unique=True)
        create_index_safe(col, [("timestamp", DESCENDING)], name="idx_eval_runs_timestamp")
        create_index_safe(col, [("status", ASCENDING)], name="idx_eval_runs_status")

        col = db["evaluation_results"]
        create_index_safe(col, [("run_id", ASCENDING)], name="idx_eval_results_run_id")
        create_index_safe(col, [("test_id", ASCENDING)], name="idx_eval_results_test_id")
        create_index_safe(col, [("passed", ASCENDING)], name="idx_eval_results_passed")

        # --- user_auth_methods ---
        col = db["user_auth_methods"]
        create_index_safe(
            col,
            [("user_id", ASCENDING), ("provider", ASCENDING)],
            name="idx_user_auth_methods_unique",
            unique=True,
        )
        create_index_safe(
            col,
            [("provider_user_id", ASCENDING)],
            name="idx_user_auth_methods_provider_user_id",
        )

        # --- user_sessions ---
        col = db["user_sessions"]
        create_index_safe(
            col,
            [("refresh_token_hash", ASCENDING)],
            name="idx_user_sessions_token",
            unique=True,
        )
        create_index_safe(
            col,
            [("user_id", ASCENDING)],
            name="idx_user_sessions_user_id",
        )
        create_index_safe(
            col,
            [("expires_at", ASCENDING)],
            name="idx_user_sessions_ttl",
            expireAfterSeconds=0,
        )

        # --- user_onboarding --- unique per user
        col = db["user_onboarding"]
        create_index_safe(col, [("user_id", ASCENDING)], name="idx_user_onboarding_user_id", unique=True)

        # --- user_profiles --- unique per user
        col = db["user_profiles"]
        create_index_safe(col, [("user_id", ASCENDING)], name="idx_user_profiles_user_id", unique=True)

        # --- user_goals --- unique per user
        col = db["user_goals"]
        create_index_safe(col, [("user_id", ASCENDING)], name="idx_user_goals_user_id", unique=True)

        # --- user_use_cases --- unique per user
        col = db["user_use_cases"]
        create_index_safe(col, [("user_id", ASCENDING)], name="idx_user_use_cases_user_id", unique=True)

        # --- workspaces --- by owner
        col = db["workspaces"]
        create_index_safe(col, [("owner_id", ASCENDING)], name="idx_workspaces_owner_id")

        logger.info("=== Listo ===")

    finally:
        client.close()


if __name__ == '__main__':
    main()
