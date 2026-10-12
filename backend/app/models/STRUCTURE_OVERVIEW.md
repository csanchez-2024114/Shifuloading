"""
ESTRUCTURA FINAL - Modelos MongoDB

Resumen visual de toda la estructura de modelos creada para MongoDB.
"""

# ===========================================================================
# CARPETA: app/models/
# ===========================================================================

"""
app/models/
│
├── __init__.py
│   └─ Exporta todos los modelos (con manejo de errores si Pydantic falta)
│
├── README.md
│   └─ Documentación general (actualizado con referencias a conversaciones)
│
├── proceso_model.py
│   ├─ ProcessModel       (collection: procesos)
│   ├─ ProcessTempModel   (collection: procesos_temp)
│   └─ StepModel          (pasos dentro de un proceso)
│
├── usuario_model.py
│   ├─ UserModel          (collection: usuarios)
│   ├─ IntegrationModel   (integraciones en usuario)
│   ├─ ChatModel          (chats en usuario)
│   └─ MessageModel       (mensajes en usuario.chats)
│
└── conversations/        ✨ NUEVA CARPETA
    │
    ├── __init__.py
    │   └─ Exporta ConversationModel y MessageModel
    │
    ├── conversation_model.py
    │   ├─ ConversationModel   (collection: conversations) ← NUEVO
    │   └─ MessageModel        (collection: messages) ← NUEVO
    │
    ├── examples.py
    │   └─ 6 ejemplos prácticos de uso
    │
    ├── README.md
    │   └─ Documentación completa con ejemplos
    │
    ├── SCHEMA_DOCUMENTATION.md
    │   └─ Diagramas ER, queries de MongoDB, índices
    │
    └── RESUMEN.md
        └─ Resumen de todo lo creado
"""

# ===========================================================================
# COLECCIONES MONGODB
# ===========================================================================

"""
ANTES (sin conversaciones):
├── usuarios              (documentos del usuario)
├── procesos              (procesos del agente)
└── procesos_temp         (procesos temporales)

DESPUÉS (con conversaciones):
├── usuarios              (documentos del usuario)
├── procesos              (procesos del agente)
├── procesos_temp         (procesos temporales)
├── conversations         ✨ NUEVA - Metadatos de conversaciones con IA
└── messages              ✨ NUEVA - Mensajes individuales de IA
"""

# ===========================================================================
# MODELOS Y CAMPOS
# ===========================================================================

"""
1. USUARIO (collection: usuarios)
   ├─ _id: ObjectId
   ├─ correo: str (unique)
   ├─ nombre: str
   ├─ integrations: {google, notion, slack...}
   ├─ chats: [ChatModel]  ← Chats cortos anidados
   ├─ preferences: dict
   ├─ plan: str
   └─ created_at: datetime

2. CONVERSACIÓN (collection: conversations) ✨ NUEVO
   ├─ _id: ObjectId
   ├─ user_id: ObjectId ──→ reference a usuarios._id
   ├─ title: str (generado por IA)
   ├─ created_at: datetime
   ├─ updated_at: datetime ← Se actualiza con cada mensaje
   ├─ message_count: int
   ├─ last_message_preview: str
   ├─ is_pinned: bool
   ├─ is_archived: bool
   ├─ tags: [str]
   ├─ model_used: str
   ├─ temperature: float
   └─ description: str (opcional)

3. MENSAJE (collection: messages) ✨ NUEVO
   ├─ _id: ObjectId
   ├─ conversation_id: ObjectId ──→ reference a conversations._id
   ├─ role: str ("user" | "assistant")
   ├─ content: str
   ├─ created_at: datetime
   ├─ tokens_used: int (opcional)
   └─ metadata: dict (opcional)

4. PROCESO (collection: procesos)
   ├─ _id: ObjectId
   ├─ nombre_proceso: str
   ├─ correo_usuario: str
   ├─ user_input: str
   ├─ steps: [StepModel]
   ├─ output: str
   ├─ created_at: datetime
   ├─ confirmed_at: datetime
   └─ ...

5. PROCESO TEMP (collection: procesos_temp)
   ├─ Similar a procesos pero con:
   ├─ status: "PENDING_CONFIRMATION" | "CONFIRMED"
   ├─ expires_at: datetime
   └─ procesos_id: ObjectId (si fue confirmado)
"""

# ===========================================================================
# FLUJO DE CONVERSACIÓN
# ===========================================================================

"""
PASO 1: Usuario abre un chat nuevo
└─→ POST /api/conversations
    └─→ Crear documento en conversations
        ├─ user_id, title (generado por IA)
        ├─ created_at, updated_at = ahora
        ├─ message_count = 0
        └─ is_archived = False

PASO 2: Usuario envía primer mensaje
└─→ POST /api/conversations/{conversation_id}/messages
    └─→ Crear documento en messages
        ├─ conversation_id, role="user"
        ├─ content, created_at = ahora
        └─→ Actualizar conversations
            ├─ updated_at = ahora
            ├─ message_count = 1
            └─ last_message_preview = content[:50]

PASO 3: IA procesa y responde
└─→ POST /api/conversations/{conversation_id}/messages
    └─→ Crear documento en messages
        ├─ conversation_id, role="assistant"
        ├─ content (respuesta IA), created_at = ahora
        └─→ Actualizar conversations
            ├─ updated_at = ahora
            ├─ message_count = 2
            └─ last_message_preview = content[:50]

PASO 4: Usuario abre sidebar
└─→ GET /api/conversations
    └─→ db.conversations.find(
            {user_id, is_archived: false},
            sort=[("updated_at", -1)],  ← Más reciente primero
            limit: 20
        )

PASO 5: Usuario abre conversación
└─→ GET /api/conversations/{conversation_id}/messages
    └─→ db.messages.find(
            {conversation_id},
            sort=[("created_at", 1)]  ← Más antiguo primero
        )
"""

# ===========================================================================
# DIFERENCIA: Dos TIPOS DE MessageModel
# ===========================================================================

"""
⚠️ IMPORTANTE: No confundir

TIPO 1: MessageModel EN usuario_model.py
├─ Ubicación: documentos anidados en usuarios.chats[].messages
├─ Estructura:
│  ├─ role: "user" | "assistant"
│  ├─ content: str
│  └─ timestamp: datetime
├─ Uso: Chats cortos guardados en el perfil del usuario
└─ Escalabilidad: Limitada (no recomendado para cientos de mensajes)

TIPO 2: MessageModel EN conversations/conversation_model.py ✨ NUEVO
├─ Ubicación: colección independiente "messages"
├─ Estructura:
│  ├─ conversation_id: ObjectId (Foreign Key)
│  ├─ role: "user" | "assistant"
│  ├─ content: str
│  └─ created_at: datetime
├─ Uso: Conversaciones completas con historial largo
└─ Escalabilidad: Ilimitada (recomendado para historial)

CUÁNDO USAR CADA UNA:
├─ Tipo 1: Para guardar chats dentro del documento del usuario
├─ Tipo 2: Para conversaciones independientes con historial completo
└─ Preferencia: Usa Tipo 2 para la barra lateral y historial
"""

# ===========================================================================
# ARCHIVOS CREADOS
# ===========================================================================

"""
✅ app/models/conversations/__init__.py
✅ app/models/conversations/conversation_model.py
✅ app/models/conversations/examples.py
✅ app/models/conversations/README.md
✅ app/models/conversations/SCHEMA_DOCUMENTATION.md
✅ app/models/conversations/RESUMEN.md
✅ app/models/__init__.py (actualizado)
✅ app/models/README.md (actualizado)
"""

# ===========================================================================
# CÓMO USAR
# ===========================================================================

"""
1. IMPORTAR MODELOS:
   from app.models.conversations import ConversationModel, MessageModel

2. CREAR INSTANCIAS:
   conv = ConversationModel(
       user_id=ObjectId("..."),
       title="Mi conversación",
       model_used="gpt-4"
   )
   
   msg = MessageModel(
       conversation_id=conv_id,
       role="user",
       content="Hola"
   )

3. VALIDAR ANTES DE INSERTAR:
   # Pydantic valida automáticamente
   # Si hay error, levanta ValidationError
   
4. CONVERTIR A DICT PARA MONGO:
   db.conversations.insert_one(conv.dict())
   db.messages.insert_one(msg.dict())

5. SERIALIZAR A JSON:
   print(conv.json(indent=2))
   print(msg.json())
"""

# ===========================================================================
# ÍNDICES RECOMENDADOS
# ===========================================================================

"""
Para optimizar las búsquedas frecuentes:

CONVERSATIONS:
  1. db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
     └─ Para obtener sidebar ordenado por actualización

  2. db.conversations.create_index([("user_id", 1), ("is_archived", 1)])
     └─ Para filtrar conversaciones archivadas

  3. db.conversations.create_index([("user_id", 1), ("is_pinned", -1)])
     └─ Para mostrar fijadas primero

MESSAGES:
  1. db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
     └─ Para obtener historial en orden

  2. db.messages.create_index([("conversation_id", 1), ("role", 1)])
     └─ Para filtrar por usuario/asistente
"""

# ===========================================================================
# RESUMEN FINAL
# ===========================================================================

"""
✨ NUEVO SISTEMA DE CONVERSACIONES ✨

Modelos creados:
├─ ConversationModel      ← Metadatos de conversaciones
└─ MessageModel           ← Mensajes individuales (IA)

Características:
├─ Separación clara de responsabilidades
├─ Escalable a miles de mensajes
├─ Eficiente (sidebar carga solo metadatos)
├─ Completamente documentado
├─ Validado con Pydantic
└─ Compatible con MongoDB

Documentación:
├─ README.md              ← Guía general
├─ SCHEMA_DOCUMENTATION.md ← Diagramas y queries
├─ examples.py            ← Ejemplos ejecutables
└─ RESUMEN.md             ← Este documento

Estado: LISTO PARA USAR ✅
"""
