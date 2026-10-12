"""
Diagrama de relación entre modelos de conversaciones con IA.

Este archivo documenta cómo se relacionan las colecciones de conversaciones
y mensajes con los usuarios.
"""

# ============================================================
# ESTRUCTURA DE DATOS - DIAGRAMA ER
# ============================================================

"""
┌─────────────────────────────────────────────────────────────┐
│ USUARIOS (collection: usuarios)                             │
│                                                             │
│ - _id: ObjectId (Primary Key)                              │
│ - correo: string (unique)                                  │
│ - nombre: string                                           │
│ - integrations: {...}                                      │
│ - chats: [...]                                             │
│ - preferences: {...}                                       │
└─────────────────────────────────────────────────────────────┘
           │
           │ (1-N) Propiedad
           ▼
┌─────────────────────────────────────────────────────────────┐
│ CONVERSATIONS (collection: conversations)                   │
│                                                             │
│ - _id: ObjectId (Primary Key)                              │
│ - user_id: ObjectId (Foreign Key → usuarios._id) 👈        │
│ - title: string                                            │
│ - created_at: datetime                                     │
│ - updated_at: datetime (ÍNDICE DESC para sidebar)          │
│ - message_count: int                                       │
│ - last_message_preview: string                             │
│ - is_pinned: boolean                                       │
│ - is_archived: boolean                                     │
│ - tags: [string]                                           │
│ - model_used: string (ej: "gpt-4")                         │
│ - temperature: float                                       │
└─────────────────────────────────────────────────────────────┘
           │
           │ (1-N) Contiene
           ▼
┌─────────────────────────────────────────────────────────────┐
│ MESSAGES (collection: messages)                             │
│                                                             │
│ - _id: ObjectId (Primary Key)                              │
│ - conversation_id: ObjectId (Foreign Key) 👈               │
│ - role: string ("user" | "assistant")                      │
│ - content: string (el mensaje)                             │
│ - created_at: datetime (timestamp exacto)                  │
│ - tokens_used: int (opcional)                              │
│ - metadata: {} (opcional)                                  │
└─────────────────────────────────────────────────────────────┘
"""

# ============================================================
# FLUJO DE OPERACIONES
# ============================================================

"""
1. USUARIO COMIENZA UN CHAT
   └─→ Crear documento en conversations
       └─→ user_id, title (generado por IA), created_at, updated_at

2. USUARIO ENVÍA MENSAJE
   └─→ Crear documento en messages
       ├─→ conversation_id, role="user", content
       └─→ Actualizar conversación
           ├─→ updated_at = ahora
           ├─→ message_count += 1
           └─→ last_message_preview = preview del mensaje

3. IA RESPONDE
   └─→ Crear documento en messages
       ├─→ conversation_id, role="assistant", content
       └─→ Actualizar conversación (mismos campos)

4. MOSTRAR SIDEBAR (barra lateral)
   └─→ db.conversations.find(
         {"user_id": user_id, "is_archived": false},
         sort=[("updated_at", -1)],
         limit=20
       )

5. ABRIR UNA CONVERSACIÓN
   └─→ db.messages.find(
         {"conversation_id": conv_id},
         sort=[("created_at", 1)]
       )
"""

# ============================================================
# INDICES RECOMENDADOS
# ============================================================

"""
Conversations:
  1. {user_id: 1, updated_at: -1}    ← Para obtener sidebar ordenado
  2. {user_id: 1, is_archived: 1}    ← Para filtrar archivadas
  3. {user_id: 1, is_pinned: -1}     ← Para mostrar fijadas primero

Messages:
  1. {conversation_id: 1, created_at: 1}   ← Para obtener historial ordenado
  2. {conversation_id: 1, role: 1}         ← Para filtrar por rol
"""

# ============================================================
# DISTINCIÓN IMPORTANTE: MessageModel
# ============================================================

"""
⚠️  EXISTEN DOS TIPOS DE MessageModel EN EL SISTEMA:

1️⃣  MessageModel EN usuario_model.py
    └─ Forma parte del documento Usuario
    └─ Guardado en la estructura: usuarios.chats[].messages
    └─ Para guardar chats cortos en el perfil del usuario
    └─ No tiene conversation_id (forma parte de un array anidado)

2️⃣  MessageModel EN conversations/conversation_model.py
    └─ Colección independiente: messages
    └─ Tiene conversation_id (referencia a conversación)
    └─ Para conversaciones completas con historial largo
    └─ Escalable a miles de mensajes por conversación

CUÁNDO USAR CADA UNA:
- Usa opción 1️⃣  para chats rápidos dentro del usuario
- Usa opción 2️⃣  para historial completo y barra lateral
"""

# ============================================================
# EJEMPLOS DE QUERIES (PyMongo)
# ============================================================

"""
# Obtener conversaciones activas ordenadas (para sidebar)
db.conversations.find(
    {"user_id": ObjectId(user_id), "is_archived": False},
    sort=[("updated_at", -1)],
    limit=20
)

# Obtener una conversación específica
db.conversations.find_one({"_id": ObjectId(conversation_id)})

# Obtener todos los mensajes de una conversación
db.messages.find(
    {"conversation_id": ObjectId(conversation_id)},
    sort=[("created_at", 1)]
)

# Contar mensajes de un usuario en una conversación
db.messages.count_documents({
    "conversation_id": ObjectId(conversation_id),
    "role": "user"
})

# Actualizar última hora de acceso
db.conversations.update_one(
    {"_id": ObjectId(conversation_id)},
    {
        "$set": {"updated_at": datetime.utcnow()},
        "$inc": {"message_count": 1},
        "$set": {"last_message_preview": "Preview del mensaje..."}
    }
)

# Archivar una conversación
db.conversations.update_one(
    {"_id": ObjectId(conversation_id)},
    {"$set": {"is_archived": True}}
)

# Fijar una conversación
db.conversations.update_one(
    {"_id": ObjectId(conversation_id)},
    {"$set": {"is_pinned": True}}
)

# Eliminar una conversación (soft delete)
db.conversations.update_one(
    {"_id": ObjectId(conversation_id)},
    {"$set": {"is_archived": True}}
)

# Eliminar todos los mensajes de una conversación (hard delete)
db.messages.delete_many(
    {"conversation_id": ObjectId(conversation_id)}
)

# Buscar conversaciones por tag
db.conversations.find(
    {"user_id": ObjectId(user_id), "tags": "python"},
    sort=[("updated_at", -1)]
)
"""

# ============================================================
# ARCHIVOS RELACIONADOS
# ============================================================

"""
app/models/conversations/
├── __init__.py                    # Exporta ConversationModel y MessageModel
├── conversation_model.py          # Definición de los modelos
├── examples.py                    # Ejemplos prácticos de uso
└── README.md                      # Documentación completa

app/models/
├── __init__.py                    # Exporta todos los modelos (actualizado)
├── proceso_model.py               # Procesos del agente
├── usuario_model.py               # Usuarios e integraciones
└── conversations/                 # 👈 Carpeta nueva
"""

# ============================================================
# IMPORTAR Y USAR
# ============================================================

"""
from app.models.conversations import ConversationModel, MessageModel

# Crear conversación
conv = ConversationModel(
    user_id=ObjectId("..."),
    title="Mi conversación",
    model_used="gpt-4"
)

# Crear mensaje
msg = MessageModel(
    conversation_id=conv_id,
    role="user",
    content="Hola, ¿cómo estás?"
)

# Insertar en MongoDB
db.conversations.insert_one(conv.dict())
db.messages.insert_one(msg.dict())
"""
