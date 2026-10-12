# AI Conversations Models

Modelos para la gestión de conversaciones con IA en el sistema HYPERSHIFU.

## 📊 Estructura

```
app/models/conversations/
├── __init__.py                    # Exporta los modelos
├── conversation_model.py          # Modelos de conversación y mensajes
└── README.md                      # Este archivo
```

## 🗂️ Colecciones de MongoDB

### 1. **conversations** → `ConversationModel`

Almacena el **contenedor/metadatos** de las conversaciones con IA.

Es lo que aparece en la **barra lateral** del historial de chats. Cada documento representa una conversación completa pero solo guarda información de metadatos.

**Campos:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `_id` | ObjectId | ID único generado por MongoDB |
| `user_id` | ObjectId | Foreign Key - ID del usuario propietario |
| `title` | str | Título de la conversación (generado por IA) |
| `created_at` | datetime | Fecha de creación |
| `updated_at` | datetime | Se actualiza con cada mensaje nuevo (para ordenar) |
| `message_count` | int | Número total de mensajes |
| `last_message_preview` | str | Vista previa del último mensaje |
| `is_pinned` | bool | Si está fijada en la barra lateral |
| `is_archived` | bool | Si está archivada |
| `description` | str | (Opcional) Descripción más larga |
| `tags` | List[str] | (Opcional) Etiquetas de categorización |
| `model_used` | str | (Opcional) Modelo de IA usado |
| `temperature` | float | (Opcional) Temperatura utilizada |

**Ejemplo:**
```json
{
  "_id": "507f1f77bcf86cd799439011",
  "user_id": "507f1f77bcf86cd799439012",
  "title": "Receta de galletas de chocolate",
  "created_at": "2026-02-01T14:30:00",
  "updated_at": "2026-02-02T10:30:00",
  "message_count": 8,
  "last_message_preview": "Agrega chocolate derretido...",
  "is_pinned": false,
  "is_archived": false,
  "tags": ["recetas", "postres"],
  "model_used": "gpt-4",
  "temperature": 0.7
}
```

---

### 2. **messages** → `MessageModel`

Almacena los **mensajes individuales** dentro de una conversación.

Cada documento representa un "globo de texto" en la conversación. Conecta con la conversación mediante `conversation_id`.

**Campos:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `_id` | ObjectId | ID único |
| `conversation_id` | ObjectId | Foreign Key - ID de la conversación a la que pertenece |
| `role` | str | Quién envió el mensaje: `"user"` o `"assistant"` |
| `content` | str | Contenido/texto del mensaje |
| `created_at` | datetime | Timestamp exacto del mensaje |
| `tokens_used` | int | (Opcional) Tokens consumidos |
| `metadata` | dict | (Opcional) Metadatos adicionales |

**Ejemplo:**
```json
{
  "_id": "507f1f77bcf86cd799439021",
  "conversation_id": "507f1f77bcf86cd799439011",
  "role": "user",
  "content": "¿Cuál es la mejor forma de hacer galletas?",
  "created_at": "2026-02-01T14:30:15",
  "tokens_used": 12
}
```

```json
{
  "_id": "507f1f77bcf86cd799439022",
  "conversation_id": "507f1f77bcf86cd799439011",
  "role": "assistant",
  "content": "Las mejores galletas se hacen con mantequilla a temperatura ambiente...",
  "created_at": "2026-02-01T14:30:45",
  "tokens_used": 87
}
```

---

## 🔗 Relación entre Colecciones

```
Usuario (collection: usuarios)
    │
    └─→ Conversación (collection: conversations)
            │
            └─→ Mensajes (collection: messages)
```

**Flujo:**
1. El usuario crea una nueva conversación → Se crea documento en `conversations`
2. El usuario envía un mensaje → Se crea documento en `messages` con `conversation_id`
3. El `updated_at` de la conversación se actualiza
4. La barra lateral ordena por `updated_at` DESC (más reciente primero)

---

## 💻 Ejemplos de Uso

### Importar modelos

```python
from app.models.conversations import ConversationModel, MessageModel
```

### Crear una conversación

```python
from app.models.conversations.conversation_model import ConversationModel
from bson import ObjectId

conversation_data = {
    "user_id": ObjectId("507f1f77bcf86cd799439012"),
    "title": "Cómo aprender Python",
    "is_pinned": False,
    "tags": ["programacion", "python"],
    "model_used": "gpt-4"
}

conversation = ConversationModel(**conversation_data)
print(conversation.model_dump_json())
```

### Crear un mensaje

```python
from app.models.conversations import MessageModel
from bson import ObjectId

message_data = {
    "conversation_id": ObjectId("507f1f77bcf86cd799439011"),
    "role": "user",
    "content": "¿Cuál es la diferencia entre listas y tuplas?"
}

message = MessageModel(**message_data)
print(message.json())
```

### Insertar en MongoDB

```python
from pymongo import MongoClient
from app.models.conversations import ConversationModel, MessageModel

client = MongoClient("mongodb://...")
db = client["shifu_production"]

# Crear conversación
conv_doc = conversation.dict()
conv_id = db.conversations.insert_one(conv_doc).inserted_id

# Crear mensaje
msg_doc = message.dict()
msg_doc["conversation_id"] = conv_id
db.messages.insert_one(msg_doc)

# Actualizar updated_at de la conversación
db.conversations.update_one(
    {"_id": conv_id},
    {
        "$set": {"updated_at": datetime.utcnow()},
        "$inc": {"message_count": 1}
    }
)
```

---

## 🛠️ Operaciones Comunes

### Obtener conversaciones ordenadas por reciente

```python
db.conversations.find(
    {"user_id": ObjectId(user_id)},
    sort=[("updated_at", -1)]  # Más reciente primero
).limit(20)
```

### Obtener todos los mensajes de una conversación

```python
db.messages.find(
    {"conversation_id": ObjectId(conversation_id)},
    sort=[("created_at", 1)]  # Más antiguo primero
)
```

### Contar mensajes de usuario vs asistente

```python
user_msgs = db.messages.count_documents({
    "conversation_id": ObjectId(conversation_id),
    "role": "user"
})

assistant_msgs = db.messages.count_documents({
    "conversation_id": ObjectId(conversation_id),
    "role": "assistant"
})
```

### Buscar conversaciones por tag

```python
db.conversations.find({
    "user_id": ObjectId(user_id),
    "tags": "python"
})
```

---

## 📋 Índices Recomendados

Para optimizar las consultas más comunes:

```python
# En conversations
db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
db.conversations.create_index([("user_id", 1), ("is_archived", 1)])

# En messages
db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
db.messages.create_index([("conversation_id", 1), ("role", 1)])
```

---

## ✨ Características

✅ **Separación de responsabilidades**: Metadatos en `conversations`, contenido en `messages`  
✅ **Escalabilidad**: Permite crecer sin limite de mensajes por conversación  
✅ **Eficiencia**: Solo carga metadatos para la barra lateral  
✅ **Flexibilidad**: Campos opcionales para extensibilidad  
✅ **Validación**: Pydantic valida la estructura

---

## 🔐 Relación con Usuario

El campo `user_id` en `conversations` es una **Foreign Key** que referencia a:
```
db.usuarios.find_one({"_id": ObjectId(conversation.user_id)})
```

Esto permite:
- Obtener todas las conversaciones de un usuario
- Validar que el usuario propietario acceda solo a sus conversaciones
- Borrar todas las conversaciones cuando se elimina un usuario
