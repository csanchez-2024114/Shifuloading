"""Genera doc/base_de_datos.drawio: colecciones de Mongo que usa el agente y como se relacionan. Uso: python doc/make_base_de_datos_drawio.py ."""
import sys
from html import escape
from pathlib import Path

CARD_W, CARD_H, GAP = 290, 104, 22
# grupo: (titulo, color de fondo, borde, x, y, [(id, coleccion, campos)])
GROUPS = [
    ("g_cuenta", "Cuenta del usuario", "#dae8fc", "#6c8ebf", 40, 330, [
        ("users", "users", "_id · email · plan · email_notices"),
        ("prefs", "user_preferences  ○", "user_id · idioma, zona horaria, tono"),
        ("accounts", "user_connected_accounts", "user_id · provider · account_id · tokens cifrados · status"),
        ("secrets", "user_secrets  ○", "user_id · API keys cifradas"),
    ]),
    ("g_conv", "Conversación", "#d5e8d4", "#82b366", 1420, 330, [
        ("context", "chat_context", "user_id · conversation_id (dueño de la conversación)"),
        ("messages", "chat_messages", "user_id · conversation_id · role · content · ui_actions · resources · quality · usage"),
        ("checkpoints", "shifu_checkpoints (+ _writes)", "thread_id = conversation_id · estado del grafo por turno"),
        ("msgindex", "user_message_index", "user_id · conversation_id · text + embedding (buscar en mensajes viejos)"),
    ]),
    ("g_files", "Archivos adjuntos", "#fff2cc", "#d6b656", 1880, 330, [
        ("files", "user_files", "_id = file_id · user_id · name · kind · storage · key (los bytes van al disco o a Cloudinary)"),
        ("extractions", "document_extractions", "file_id · user_id · conversation_id · texto extraído (caché)"),
        ("chunks", "document_chunks  ○", "file_id · conversation_id · user_id · texto + embedding (documentos grandes)"),
    ]),
    ("g_mem", "Memoria y avisos", "#e1d5e7", "#9673a6", 960, 330, [
        ("facts", "user_semantic_memory", "user_id · key · value · status · source_conversation (un hecho por documento)"),
        ("diary", "user_daily_diary", "user_id · conversation_id · activities · pending (due_date, done_at)"),
        ("decisions", "user_decision_memory  ○", "user_id · decisión + embedding"),
        ("goals", "user_active_goals  ○", "user_id · metas (solo lectura)"),
        ("notices", "user_notifications", "user_id · type · read · told_at · emailed_at"),
        ("mails", "notice_emails  ○", "user_id · tope de correos de avisos por día"),
    ]),
    ("g_wf", "Workflows y acciones", "#f8cecc", "#b85450", 500, 330, [
        ("workflows", "workflows", "_id · user_id · status · steps[function_id, config, account_id] · webhook_token · email_trigger"),
        ("tasks", "scheduled_tasks", "workflow_id · cron · next_run_at (programador)"),
        ("runs", "workflow_runs", "_id = run_id · workflow_id · user_id · trigger · resultado por paso"),
        ("wfstate", "workflow_state", "workflow_id · last_run_at"),
        ("wfstats", "workflow_analytics", "workflow_id · run_id · user_id · status · duration_ms"),
        ("actions", "action_log", "user_id · conversation_id · fn = function_id · args (escrituras del modo act)"),
    ]),
    ("g_auth", "Acceso y perfil", "#d0e0e3", "#45818e", 2340, 330, [
        ("authm", "user_auth_methods", "user_id · provider · provider_user_id (correo, Google...)"),
        ("sessions", "user_sessions", "user_id · refresh_token_hash · device · expires_at · revoked_at"),
        ("profiles", "user_profiles", "user_id · display_name · avatar_url"),
        ("onboarding", "user_onboarding", "user_id · current_step · completed"),
        ("streaks", "login_streaks", "user_id · login_date"),
    ]),
    ("g_log", "Registro y medición", "#eeeeee", "#999999", 1880, 800, [
        ("audit", "audit_events", "user_id · action · resource · outcome · ip"),
        ("outcomes", "intent_outcomes", "user_id · conversation_id · workflow_id · run_id · intent_type · success"),
    ]),
]
GLOBAL = ("g_global", "Datos globales (sin usuario): comportamiento y catálogos", "#f5f5f5", "#666666", 40, 40, [
    ("catalog", "catalog_apps", "apps de la plataforma y cómo se conectan"),
    ("functions", "functions  ○", "function_id · app · version · status · descripción + embedding"),
    ("fapps", "function_apps  ○", "app · AuthSpec (cómo se autentica cada app)"),
    ("uicat", "ui_actions_catalog", "id · source · label · plans · confirm"),
    ("identity", "agent_identity", "quién es el agente"),
    ("personality", "agent_personality", "voz, reglas, memory_policy, quality_control (SHIFU_AGENT_ID elige el documento)"),
])
# Por donde sale y entra cada linea: asi corren por los pasillos entre columnas y no por encima de las tarjetas.
MODES = {
    "L": "exitX=0;exitY=0.5;entryX=0;entryY=0.5;",      # misma columna, por el carril izquierdo
    "R": "exitX=1;exitY=0.5;entryX=0;entryY=0.5;",      # a la columna de la derecha
    "Lx": "exitX=0;exitY=0.5;entryX=1;entryY=0.5;",     # a la columna de la izquierda
    "U": "exitX=0.5;exitY=0;entryX=0.5;entryY=1;",      # hacia los datos globales
    "BUS": "exitX=0.5;exitY=0;entryX=0.5;entryY=0;",    # de users a un grupo entero, por la franja de arriba
    "RU": "exitX=1;exitY=0.5;entryX=0.85;entryY=1;",
    "LU": "exitX=0;exitY=0.75;entryX=0.15;entryY=1;",
}
# (origen, destino, etiqueta, punteada = se enlaza por nombre o es indirecta, modo)
EDGES = [
    ("users", "g_wf", "user_id", 0, "BUS"), ("users", "g_mem", "user_id", 0, "BUS"), ("users", "g_conv", "user_id", 0, "BUS"), ("users", "g_files", "user_id", 0, "BUS"), ("users", "g_auth", "user_id", 0, "BUS"),
    ("users", "prefs", "user_id", 0, "L"), ("users", "accounts", "user_id", 0, "L"), ("users", "secrets", "user_id", 0, "L"),
    ("context", "messages", "conversation_id", 0, "L"), ("context", "checkpoints", "thread_id", 0, "L"),
    ("context", "diary", "conversation_id", 0, "Lx"), ("context", "facts", "source_conversation", 1, "Lx"),
    ("messages", "files", "resources.file_id", 0, "R"), ("files", "extractions", "file_id", 0, "L"), ("extractions", "chunks", "file_id", 0, "L"),
    ("workflows", "tasks", "workflow_id", 0, "L"), ("workflows", "runs", "workflow_id", 0, "L"), ("workflows", "wfstate", "workflow_id", 0, "L"), ("runs", "wfstats", "run_id", 0, "L"), ("context", "msgindex", "conversation_id", 0, "L"),
    ("runs", "notices", "run_failed / run_completed", 1, "R"), ("notices", "mails", "correo de avisos", 1, "L"),
    ("workflows", "functions", "steps.function_id", 0, "U"), ("workflows", "accounts", "steps.account_id", 0, "Lx"),
    ("functions", "fapps", "app", 0, "R"), ("accounts", "catalog", "provider", 1, "LU"),
]

cells = []


def card(cid, parent, name, fields, x, y, w, stroke):
    label = escape(f"<b>{name}</b><br><font style=\"font-size:10px\">{fields}</font>", quote=True)
    cells.append(f'<mxCell id="{cid}" value="{label}" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor={stroke};align=left;spacingLeft=8;spacingRight=6;verticalAlign=middle;" vertex="1" parent="{parent}">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{CARD_H}" as="geometry"/></mxCell>')


def box(gid, title, fill, stroke, x, y, w, h):
    cells.append(f'<mxCell id="{gid}" value="{escape(title, quote=True)}" style="swimlane;startSize=30;html=1;fillColor={fill};strokeColor={stroke};fontStyle=1;" vertex="1" parent="1">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


gid, title, fill, stroke, x, y, items = GLOBAL
gw = 417
box(gid, title, fill, stroke, x, y, 20 + len(items) * (gw + 28) - 8, 30 + CARD_H + 32)
for i, (cid, name, fields) in enumerate(items):
    card(cid, gid, name, fields, 20 + i * (gw + 28), 46, gw, stroke)
for gid, title, fill, stroke, x, y, items in GROUPS:
    box(gid, title, fill, stroke, x, y, CARD_W + 80, 30 + 16 + len(items) * (CARD_H + GAP))
    for i, (cid, name, fields) in enumerate(items):
        card(cid, gid, name, fields, 40, 46 + i * (CARD_H + GAP), CARD_W, stroke)
for i, (a, b, label, dashed, mode) in enumerate(EDGES):
    cells.append(f'<mxCell id="e{i}" value="{escape(label, quote=True)}" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=ERmany;startArrow=ERone;fontSize=10;labelBackgroundColor=#ffffff;{MODES[mode]}'
                 f'{"dashed=1;" if dashed else ""}" edge="1" source="{a}" target="{b}" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>')
legend = escape("<b>Cómo leerlo</b><br>Casi todo cuelga de <b>users</b> por <b>user_id</b> y de la conversación por <b>conversation_id</b>.<br>"
                "Mongo no tiene llaves foráneas: estas relaciones las mantiene el código.<br>Línea continua = se enlaza por id. Punteada = por nombre o indirecta. No se dibujan todas: document_chunks y action_log también llevan conversation_id, y action_log.fn apunta a functions.<br>"
                "○ = el código la usa, pero en este Mongo todavía no tiene documentos (no existe hasta el primer uso).<br><b>Solo nombradas en el código, sin colección en este Mongo:</b> oauth_vault, password_resets, workspace_members, referrals, message_feedback, user_pending_tasks, user_memories, user_global_memory, agent_session_state, app_tools_catalog, processes, scheduled_processes y unas 20 del backend original que aquí nadie usa (rewards, posts, boards, workspaces, stripe_events...).<br>Contado contra el Mongo local el 2026-10-11: 29 colecciones, tras borrar 8 que nadie leía (6 vacías del diseño anterior, más agent_goals y agent_system_model).", quote=True)
cells.append(f'<mxCell id="legend" value="{legend}" style="rounded=0;whiteSpace=wrap;html=1;fillColor=#fffde7;strokeColor=#bbbbbb;align=left;spacingLeft=10;verticalAlign=middle;fontSize=11;" vertex="1" parent="1">'
             f'<mxGeometry x="960" y="1160" width="1750" height="170" as="geometry"/></mxCell>')

xml = ('<mxfile host="app.diagrams.net"><diagram id="db" name="Base de datos"><mxGraphModel dx="1600" dy="1100" grid="1" gridSize="10" page="0"><root>'
       '<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>")
out = Path(sys.argv[1]) / "doc" / "base_de_datos.drawio"
out.write_text(xml, encoding="utf-8")
import xml.etree.ElementTree as ET  # noqa: E402
root = ET.fromstring(xml)
ids = {c.get("id") for c in root.iter("mxCell")}
missing = [(c.get("source"), c.get("target")) for c in root.iter("mxCell") if c.get("edge") and not {c.get("source"), c.get("target")} <= ids]
print(out, "| celdas:", len(ids), "| relaciones:", len(EDGES), "| extremos sin tarjeta:", missing)
print(xml[xml.index("<mxGraphModel"):xml.index("</diagram>")] if "--print" in sys.argv else "")
