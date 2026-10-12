# User Memories Model - Documentación

## 📋 Estructura General

El modelo `UserMemoriesModel` está diseñado para almacenar y gestionar las preferencias y características detectadas del usuario.

---

## 🏗️ Componentes Principales

### 1. **MemoryItemModel** - Cada preferencia individual
```python
{
    "key": "idioma_preferido",           # Identificador único
    "value": "español",                 # Valor almacenado
    "category": "language",             # Categoría
    "confidence": 0.95,                 # Confianza (0.0 - 1.0)
    "source": "conversation_detected",  # De dónde se detectó
    "detected_from_message": "texto",   # Mensaje original
    "created_at": "2026-02-06T...",     # Cuándo se detectó
    "updated_at": "2026-02-06T...",     # Última actualización
    "update_count": 3,                  # Veces confirmada
    "metadata": {...}                   # Info adicional
}
```

### 2. **UserMemoriesModel** - Perfil completo del usuario
```python
{
    "_id": ObjectId,                    # Auto-generado por MongoDB
    "user_id": ObjectId,                # FK a colección 'usuarios'
    "user_email": "user@example.com",
    "memories": [
        {...},  # MemoryItemModel 1
        {...},  # MemoryItemModel 2
        ...
    ],
    "created_at": "2026-02-01T...",
    "updated_at": "2026-02-06T...",
    "total_memories": 5,
    "average_confidence": 0.92,
    "is_active": True
}
```

---

## 🏷️ Categorías de Memorias

El campo `category` define el tipo de preferencia:

| Categoría | Descripción | Ejemplos |
|-----------|-------------|----------|
| `language` | Preferencias idiomáticas | idioma_preferido, dialecto, variantes |
| `tone` | Tono/estilo de comunicación | formal, informal, técnico, casual |
| `apps` | Aplicaciones/integraciones | apps_frecuentes, apps_favoritas |
| `schedule` | Horarios y tiempo | horario_preferido, zona_horaria, disponibilidad |
| `personal` | Info personal recordada | nombre_jefe, empresa, rol, colegas |
| `interests` | Temas/áreas de interés | temas_favoritos, proyectos, especialidades |
| `communication` | Estilo de comunicación | formal/informal, detalles vs resumen |
| `other` | Otras preferencias | categoría personalizada |

---

## 📊 Ejemplo Completo

```python
{
    "_id": ObjectId("507f1f77bcf86cd799439011"),
    "user_id": ObjectId("607f1f77bcf86cd799439012"),
    "user_email": "juan@empresa.com",
    
    "memories": [
        # Memoria 1: Idioma preferido
        {
            "key": "idioma_preferido",
            "value": "español",
            "category": "language",
            "confidence": 0.98,
            "source": "detected_pattern",
            "detected_from_message": "Prefiero que hables siempre en español",
            "created_at": "2026-02-01T10:00:00",
            "updated_at": "2026-02-06T15:00:00",
            "update_count": 8,
            "metadata": {"variants": ["es", "español", "castellano"]}
        },
        
        # Memoria 2: Tono preferido
        {
            "key": "tono_comunicacion",
            "value": "profesional_informal",
            "category": "tone",
            "confidence": 0.85,
            "source": "pattern_detected_from_interactions",
            "detected_from_message": "Prefiero un tono relajado pero profesional",
            "created_at": "2026-02-02T08:30:00",
            "updated_at": "2026-02-06T14:00:00",
            "update_count": 5
        },
        
        # Memoria 3: Apps frecuentes
        {
            "key": "apps_frecuentes",
            "value": ["Gmail", "Google Drive", "Slack", "Notion"],
            "category": "apps",
            "confidence": 0.95,
            "source": "usage_tracking",
            "created_at": "2026-02-01T10:15:00",
            "updated_at": "2026-02-06T15:30:00",
            "update_count": 15,
            "metadata": {
                "usage_frequency": {"Gmail": 0.95, "Drive": 0.87, "Slack": 0.80, "Notion": 0.70}
            }
        },
        
        # Memoria 4: Horario preferido
        {
            "key": "zona_horaria",
            "value": "America/Mexico_City",
            "category": "schedule",
            "confidence": 0.92,
            "source": "detected_from_timestamps",
            "created_at": "2026-02-03T09:00:00",
            "updated_at": "2026-02-06T13:45:00",
            "update_count": 10
        },
        
        # Memoria 5: Información personal
        {
            "key": "empresa",
            "value": "HyperShifu AI",
            "category": "personal",
            "confidence": 0.99,
            "source": "conversation_explicit",
            "detected_from_message": "Trabajo en HyperShifu AI como Project Manager",
            "created_at": "2026-02-04T11:00:00",
            "updated_at": "2026-02-06T12:00:00",
            "update_count": 2
        },
        
        # Memoria 6: Temas de interés
        {
            "key": "temas_interes",
            "value": ["productividad", "automatización", "integraciones", "data science"],
            "category": "interests",
            "confidence": 0.88,
            "source": "pattern_detected",
            "created_at": "2026-02-05T10:00:00",
            "updated_at": "2026-02-06T15:00:00",
            "update_count": 6
        }
    ],
    
    "created_at": "2026-02-01T08:00:00",
    "updated_at": "2026-02-06T15:30:00",
    "last_memory_detected_at": "2026-02-06T15:30:00",
    "total_memories": 6,
    "average_confidence": 0.93,
    "is_active": True
}
```

---

## 🎯 Casos de Uso

### 1. **Detección Automática**
El LLM detecta automáticamente preferencias:
```
Usuario: "Prefiero que me respondas siempre en español"
→ Se detecta y crea/actualiza memoria "idioma_preferido"
```

### 2. **Formato para Prompt del LLM**
Las memorias se formatean y se inyectan en el prompt:
```
PREFERENCIAS DEL USUARIO:
- Idioma: Español
- Tono: Profesional pero informal
- Apps favoritas: Gmail, Google Drive, Slack
- Zona horaria: México (GMT-6)
- Empresa: HyperShifu AI
- Intereses: Automatización, productividad, integraciones
```

### 3. **Actualización Incremental**
Cada vez que se detecta la misma preferencia:
- Se incrementa `update_count`
- Se actualiza `updated_at`
- Se recalcula `average_confidence`
- Se puede actualizar el `confidence` si hay evidencia adicional

### 4. **Recuperación de Contexto**
Antes de responder, el agente:
1. Carga las memories del usuario
2. Formatea un resumen
3. Lo incluye como "hint" en el system prompt
4. El LLM ajusta su respuesta en base a eso

---

## 🔄 Ciclo de Vida de una Memoria

1. **Detección**: Se analiza input del usuario → Se detecta preferencia
2. **Creación**: Se crea `MemoryItemModel` con `confidence` inicial
3. **Confirmación**: Si se confirma esta preferencia → Se incrementa `update_count`
4. **Actualización**: Valor/metadata puede cambiar → Se actualiza `updated_at` 
5. **Uso**: Se formatea y se pasa al LLM como contexto
6. **Revisión/Borrado** (futuro): Usuario puede revisar/eliminar memorias incorrectas

---

## 📝 Próximos Pasos

Después de que valides este modelo, necesitaremos:

1. **Servicio de Gestión** (`UserMemoriesService`):
   - `add_memory()`: Agregar nueva memoria
   - `update_memory()`: Actualizar memoria existente
   - `get_memories()`: Obtener todas las memorias
   - `get_formatted_summary()`: Formatear para LLM
   - `detect_and_add()`: Detectar automáticamente

2. **Integración en `AgentService`**:
   - Detectar memorias después de cada mensaje
   - Incluir memorias en prompts del LLM
   - Actualizar confianza de memorias existentes

3. **Rutas API** (opcional):
   - GET `/api/user/memories` - Obtener memorias
   - POST `/api/user/memories` - Crear manual
   - PUT `/api/user/memories/{id}` - Actualizar
   - DELETE `/api/user/memories/{id}` - Eliminar

---

¿Te parece bien esta estructura? ¿Algo que cambiar o agregar?
