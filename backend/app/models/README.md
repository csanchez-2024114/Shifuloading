# Modelos de MongoDB

Esta carpeta contiene los modelos de datos que representan las estructuras almacenadas en MongoDB para el backend de HYPERSHIFU AI.

## 📁 Estructura

```
app/models/
├── __init__.py                    # Exporta todos los modelos
├── proceso_model.py               # Modelos para procesos del agente
├── usuario_model.py               # Modelos para usuarios e integraciones
├── README.md                       # Este archivo
└── conversations/                 # Carpeta para modelos de conversaciones con IA
    ├── __init__.py
    ├── conversation_model.py      # ConversationModel y MessageModel
    └── README.md                  # Documentación de conversaciones
```

## 📊 Colecciones de MongoDB

### 1. **usuarios** → `UserModel`

Almacena información de los usuarios del sistema.

**Campos principales:**
- `correo`: Email del usuario (identificador único)
- `nombre`: Nombre del usuario
- `integrations`: Diccionario de integraciones con servicios externos (Google, Notion, Slack, etc.)
- `chats`: Historial de conversaciones con el agente
- `preferences`: Preferencias guardadas por el usuario
- `plan`: Plan de suscripción (free, pro, enterprise)

**Modelos relacionados:**
- `IntegrationModel`: Representa una integración con un servicio externo
- `ChatModel`: Representa una conversación
- `MessageModel`: Representa un mensaje individual

**Ubicación:** `app/models/usuario_model.py`

---

### 2. **procesos** → `ProcessModel`

Almacena procesos del agente que han sido confirmados y guardados permanentemente.

**Campos principales:**
- `nombre` / `nombre_proceso`: Nombre del proceso
- `correo_usuario`: Email del propietario
- `user_input`: Prompt original del usuario
- `steps`: Lista de pasos ejecutados (cada uno con herramienta, input y resultado)
- `output`: Resultado final del proceso
- `total_steps`: Número total de pasos
- `created_at`: Fecha de creación
- `confirmed_at`: Fecha de confirmación

**Modelos relacionados:**
- `StepModel`: Representa un paso individual del proceso

**Ubicación:** `app/models/proceso_model.py`

---

### 3. **procesos_temp** → `ProcessTempModel`

Almacena procesos temporales que esperan confirmación del usuario.

**Campos principales:**
- Similar a `ProcessModel` pero con campos adicionales:
- `status`: Estado del proceso (PENDING_CONFIRMATION, CONFIRMED)
- `expires_at`: Fecha de expiración (típicamente 1 hora)
- `procesos_id`: ID del proceso en la colección definitiva si fue confirmado

**Ubicación:** `app/models/proceso_model.py`

---

## 🔧 Uso de los Modelos

### Importar modelos

```python
from app.models import ProcessModel, UserModel, IntegrationModel
from app.models import ProcessTempModel, StepModel, ChatModel, MessageModel
```

### Ejemplo: Validar un proceso

```python
from app.models import ProcessModel, StepModel

proceso_data = {
    "nombre": "create_doc",
    "nombre_proceso": "create_doc",
    "correo_usuario": "user@example.com",
    "user_input": "Crea un documento en Google Docs",
    "steps": [
        {
            "step_number": 1,
            "tool": "google_docs",
            "tool_input": {"title": "Mi Documento"},
            "observation": "Documento creado exitosamente"
        }
    ],
    "total_steps": 1,
    "output": "Proceso completado"
}

# Validar con Pydantic
proceso = ProcessModel(**proceso_data)
print(proceso.json())
```

### Ejemplo: Validar un usuario

```python
from app.models import UserModel

usuario_data = {
    "correo": "usuario@example.com",
    "nombre": "Juan Pérez",
    "integrations": {
        "google": {
            "access_token": "ya29.xxx",
            "refresh_token": "1//xxx",
            "google_id": "123456789"
        }
    },
    "plan": "pro"
}

usuario = UserModel(**usuario_data)
print(usuario.correo)  # usuario@example.com
```

---

## � Conversaciones con IA

Existe una **carpeta separada** para los modelos de conversaciones con IA:

### 4. **conversations** → `ConversationModel`

Almacena metadatos de conversaciones con IA (lo que aparece en la barra lateral).

**Campos principales:**
- `user_id`: ID del usuario propietario
- `title`: Título de la conversación (generado por IA)
- `created_at`: Fecha de creación
- `updated_at`: Se actualiza con cada mensaje (para ordenar en sidebar)
- `message_count`: Número de mensajes en la conversación
- `is_pinned`: Si está fijada
- `is_archived`: Si está archivada

**Ubicación:** `app/models/conversations/conversation_model.py`

---

### 5. **messages** → `MessageModel` (AI Conversations)

Almacena mensajes individuales dentro de conversaciones con IA.

**Campos principales:**
- `conversation_id`: Foreign Key a la conversación
- `role`: "user" o "assistant"
- `content`: Texto del mensaje
- `created_at`: Timestamp del mensaje
- `tokens_used`: (Opcional) Tokens consumidos

**Ubicación:** `app/models/conversations/conversation_model.py`

**Nota:** Este `MessageModel` es diferente del `MessageModel` en `usuario_model.py` que pertenece al modelo de `ChatModel` del usuario.

Ver documentación completa en: [app/models/conversations/README.md](conversations/README.md)

---

## 📚 Tecnologías

- **Pydantic**: Validación de datos y serialización
- **PyMongo**: Interacción con MongoDB
- **BSON**: Manejo de ObjectId y tipos de datos de MongoDB

---

## 🔄 Relación con el Código Existente

Los modelos documentan y validan las estructuras que ya se están usando en:

- `app/agents/mongo_process_manager.py` - Gestión de procesos
- `app/routes/userRoutes.py` - Gestión de usuarios
- `app/services/*.py` - Servicios de integración

---

## ✅ Ventajas de Usar Estos Modelos

1. **Documentación clara** de las estructuras de datos
2. **Validación automática** con Pydantic
3. **Type hints** para mejor autocompletado en IDEs
4. **Consistencia** en toda la aplicación
5. **Facilita migraciones** y cambios en el esquema

---

## 🚀 Próximos Pasos

Para integrar estos modelos en el código existente:

1. Importar los modelos en los archivos que interactúan con MongoDB
2. Validar datos antes de insertar en la base de datos
3. Usar los modelos para type hints en funciones
4. Documentar APIs con los esquemas de Pydantic

---

## 📝 Notas

- Los modelos son **descriptivos**, no imponen restricciones en MongoDB (que es schema-less)
- Se pueden usar para **validación opcional** donde sea necesario
- Mantienen compatibilidad con el código existente
