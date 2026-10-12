# ⚡ Quick Reference - User Memories

## 🎯 Lo Esencial en 1 Minuto

### **Qué es**
Sistema que el LLM RECUERDA las preferencias del usuario automáticamente y las usa para personalizar respuestas.

### **Cómo funciona**
1. Usuario envía mensaje
2. Sistema obtiene preferencias recordadas
3. Las agrega al prompt del LLM
4. LLM responde considerando esas preferencias
5. Se detectan nuevas preferencias
6. Se guardan para futuras conversaciones

### **Resultado**
El LLM mejora con cada interacción. Sabe idioma preferido, tono, apps usadas, etc.

---

## 📂 Ubicación de Archivos

```
app/
├── models/
│   ├── user_memories_model.py      ← Modelos Pydantic
│   ├── __init__.py                 ← Exports
│   └── USER_MEMORIES_REFERENCE.md  ← Docs del modelo
├── agents/
│   ├── agent_service.py            ← Integración (MODIFICADO)
│   ├── user_memories_service.py    ← Servicio (NUEVO)
│   └── USER_MEMORIES_INTEGRATION.md ← Docs integración
└── ... otra estructura
```

---

## 🔧 Uso Rápido del Servicio

### **Importar**
```python
from app.agents.user_memories_service import UserMemoriesService
```

### **Instanciar**
```python
service = UserMemoriesService("usuario@example.com")
```

### **Obtener/Crear**
```python
memory_doc = service.get_or_create_memories()
# Retorna: document de mongoDB o None si error
```

### **Formatear para LLM**
```python
formatted = service.format_memories_for_llm(memory_doc)
# Retorna: string con formato bonito para el prompt
```

### **Detectar y Actualizar**
```python
updated = service.detect_and_update_memories(
    user_input="texto del usuario",
    llm_response="respuesta del LLM",
    memory_doc=memory_doc
)
# Retorna: True si hubo cambios, False si no
```

### **Otros**
```python
# Obtener una memoria específica
mem = service.get_memory_by_key(memory_doc, "idioma_preferido")

# Verificar si tiene memorias
has = service.has_memory(memory_doc)

# Borrar todo
deleted = service.reset_memories(memory_doc)
```

---

## 📊 Categorías de Memorias

| Valor | Descripción | Ejemplos |
|-------|-------------|----------|
| `language` | Idioma preferido | español, english, francés |
| `tone` | Tono de comunicación | formal, informal, técnico |
| `apps` | Apps que usa | Gmail, Drive, Slack |
| `schedule` | Horarios/zona horaria | UTC-6, 9am-5pm |
| `personal` | Info personal | Juan, ingeniero, empresa |
| `interests` | Temas de interés | API, ML, productividad |
| `communication` | Estilo de escribir | resumen vs detallado |
| `other` | Otros | custom |

---

## 🧠 Estructura de una Memoria

```python
{
    "key": "idioma_preferido",          # ID único
    "value": "español",                 # El valor
    "category": "language",             # Categoría
    "confidence": 0.95,                 # 0.0-1.0: confianza
    "source": "detected_pattern",       # Origen
    "detected_from_message": "...",     # Texto original
    "created_at": "2026-02-06T...",     # Cuándo
    "updated_at": "2026-02-06T...",     # Última actualización
    "update_count": 5,                  # Veces confirmada
    "metadata": {...}                   # Campos adicionales
}
```

---

## 📈 Confianza de Memoria

```
Confianza += 0.02 cada vez que se confirma

Ejemplo:
1a vez: 1.0
2a vez: 1.02 (capped a 1.0)
3a vez: 1.02
5a vez: 1.02

Más confirmaciones = más confianza
```

---

## 🔄 Flujo en AgentService

### **En `_answer_without_tools()`:**
```
1. Obtener/crear memories
2. Formatear: formatted_memories = service.format_memories_for_llm(memory_doc)
3. Incluir en system prompt: f"...{formatted_memories}..."
4. Invocar LLM
5. Detectar: service.detect_and_update_memories(user_input, output, memory_doc)
6. Responder
```

### **En `ejecutar_o_crear_proceso()`:**
```
Fase 1.2: Obtener/crear memories
Fase 4: Incluir formatted_memories en el prompt enriquecido
Fase 5: Detectar y actualizar después de responder
```

---

## 💾 MongoDB

### **Colección**
```
db.user_memories
```

### **Índices Recomendados**
```javascript
db.user_memories.createIndex({ "correo_usuario": 1 })
db.user_memories.createIndex({ "user_id": 1 })
```

### **Consulta Típica**
```javascript
db.user_memories.findOne({ "correo_usuario": "user@example.com" })
```

---

## 🎯 Ejemplos de Uso

### **Ejemplo 1: Respuesta Simple**
```python
# User: "Hola, ¿qué tal?"

# Backend
service = UserMemoriesService("user@example.com")
memory_doc = service.get_or_create_memories()
formatted = service.format_memories_for_llm(memory_doc)

# Si memory_doc tiene:
# - idioma_preferido: español
# - tono: profesional
# 
# formatted = 
# "🌐 Idioma: español ✅
#  🎭 Tono: profesional ✔️
#  ..."
#
# System prompt ahora incluye estas preferencias
# LLM responde en ESPAÑOL Y PROFESIONAL automáticamente
```

### **Ejemplo 2: Detectar Nueva Preferencia**
```python
user_input = "Prefiero que hables en inglés"
llm_response = "Of course! I'll speak in English from now on."
memory_doc = {...}

updated = service.detect_and_update_memories(
    user_input, llm_response, memory_doc
)
# updated = True
# Nueva memoria: idioma_preferido = english
```

### **Ejemplo 3: Acceso Directo**
```python
service = UserMemoriesService("user@example.com")
memory_doc = service.get_or_create_memories()

# Obtener un valor específico
idioma = service.get_memory_by_key(memory_doc, "idioma_preferido")
print(idioma['value'])  # "español"
```

---

## ⚠️ Cosas Importantes

1. **Email es la clave**
   ```python
   # Siempre usar correo_usuario para obtener/crear
   service = UserMemoriesService(correo_usuario)
   ```

2. **Formateo antes de incluir en prompt**
   ```python
   # Siempre formatear, no pasar el doc directamente
   formatted = service.format_memories_for_llm(memory_doc)
   ```

3. **Detectar después de responder**
   ```python
   # Siempre llamar detect_and_update después de obtener respuesta
   service.detect_and_update_memories(..., memory_doc)
   ```

4. **Manejo de errores**
   ```python
   try:
       service.detect_and_update_memories(...)
   except Exception as e:
       print(f"⚠️ Error: {e}")
       # Continuar sin error - las memorias son opcionales
   ```

---

## 🚨 Troubleshooting

### **Problema: No se detectan memorias**
```
Checklist:
□ ¿memory_doc es None?  → Verificar conexión MongoDB
□ ¿_extract_preferences_from_text() vacío? → Mejorar lógica de detección
□ ¿user_input vacío? → Verificar input del usuario
□ ¿Excepción silenciosa? → Agregar logs
```

### **Problema: Memoria no se actualiza**
```
Checklist:
□ ¿Se está llamando detect_and_update_memories()? → Sí/No
□ ¿memory_doc es válido? → Verificar estructura
□ ¿Errores en console? → Ver logs
□ ¿update_count no incrementa? → Verificar lógica de actualización
```

### **Problema: LLM no considera memorias**
```
Checklist:
□ ¿formatted_memories está vacío? → Verificar format_memories_for_llm()
□ ¿Se incluye en el prompt? → Verificar que sí esté en el string
□ ¿LLM recibe el prompt actualizado? → Verificar invoke()
□ ¿System prompt tiene las memorias? → Audit del prompt antes de invocar
```

---

## 📞 Métodos del Service Rápidos

```python
service = UserMemoriesService(correo_usuario)

# CRUD
service.get_or_create_memories()                    → memory_doc
service._save_memories_to_db(memory_doc)            → bool

# Formateo
service.format_memories_for_llm(memory_doc)         → str

# Detección
service.detect_and_update_memories(u, r, m)        → bool

# Querys
service.get_memory_by_key(memory_doc, key)          → memory o None
service.has_memory(memory_doc)                      → bool

# Destructivo
service.reset_memories(memory_doc)                  → bool
```

---

## 🎓 Campos del MemoryItemModel

```python
MemoryItemModel(
    key="",                         # str - identificador
    value="",                        # Any - valor
    category="",                     # str - categoría
    confidence=1.0,                  # float 0-1
    source=None,                     # str opcional
    detected_from_message=None,      # str opcional
    created_at=datetime.utcnow(),    # datetime
    updated_at=datetime.utcnow(),    # datetime
    update_count=1,                  # int
    metadata=None                    # dict opcional
)
```

---

## 🔗 Links Documentación

- [Modelo completo](app/models/USER_MEMORIES_REFERENCE.md)
- [Integración en AgentService](app/agents/USER_MEMORIES_INTEGRATION.md)
- [Diagrama visual](SYSTEM_MEMORIES_DIAGRAM.md)
- [Resumen completo](SYSTEM_MEMORIES_SUMMARY.md)

---

**Última actualización:** 6 de febrero de 2026
**Versión:** 1.0
