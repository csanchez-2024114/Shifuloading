# 🎯 Diagrama Visual - Sistema de User Memories

## 📊 Flujo Completo de Ejecución

```
┌─────────────────────────────────────────────────────────────────┐
│                    USUARIO ENVÍA MENSAJE                        │
│                     "Prefiero español"                           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│    AGENTSERVICE.ejecutar_o_crear_proceso()                      │
│         o _answer_without_tools()                               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ↓                   ↓
              ┌─────────────┐    ┌──────────────┐
              │ FASE 1      │    │ FASE 1.2     │
              │ Validar     │    │ Obtener/     │
              │ Integraciones   │ Crear Memories
              └─────────────┘    └──────────────┘
                                      │
                                      ↓
                        ┌─────────────────────────────┐
                        │ ¿Usuario tiene memorias?    │
                        └──────────┬──────────────────┘
                                   │
                   ┌───────────────┴───────────────┐
                   │                               │
                   ↓ NO                            ↓ SÍ
          ┌──────────────────┐          ┌──────────────────┐
          │ Crear documento  │          │ Obtener documento│
          │ memorias vacío   │          │ existente        │
          └──────────────────┘          └──────────────────┘
                   │                               │
                   └───────────────┬───────────────┘
                                   │
                                   ↓
                    ┌──────────────────────────────┐
                    │ FASE 2                       │
                    │ Formatear memorias para LLM  │
                    └──────────────┬───────────────┘
                                   │
                                   ↓
                        ┌──────────────────────────┐
                        │ Agrupar por categorías   │
                        │ Crear string formateado  │
                        └──────────────┬───────────┘
                                      │
                                      ↓
                    ┌──────────────────────────────┐
                    │ FASE 3                       │
                    │ Agregar memorias al Prompt   │
                    │                              │
                    │ System Prompt INCLUYE:       │
                    │ 🌐 Idioma: español ✅        │
                    │ 🎭 Tono: profesional ✔️      │
                    │ 🔧 Apps: Gmail, Drive ✅    │
                    │ + Instrucciones para LLM     │
                    └──────────────┬───────────────┘
                                   │
                                   ↓
                    ┌──────────────────────────────┐
                    │ FASE 4                       │
                    │ Invocar LLM                  │
                    │ (ChatOpenAI)                 │
                    │                              │
                    │ LLM RECIBE:                  │
                    │ - Preferencias del usuario   │
                    │ - Historial de chat          │
                    │ - Mensaje actual             │
                    └──────────────┬───────────────┘
                                   │
                                   ↓
                    ┌──────────────────────────────┐
                    │ LLM ADAPTA RESPUESTA         │
                    │ basándose en memorias        │
                    │                              │
                    │ Responde en ESPAÑOL          │
                    │ Con TONO PROFESIONAL         │
                    │ Menciona APPS disponibles    │
                    └──────────────┬───────────────┘
                                   │
                                   ↓
                    ┌──────────────────────────────┐
                    │ FASE 5                       │
                    │ Guardar respuesta en BD      │
                    │ (conversations.messages)     │
                    └──────────────┬───────────────┘
                                   │
                                   ↓
                    ┌──────────────────────────────┐
                    │ FASE 6                       │
                    │ Detectar nuevas memorias     │
                    │                              │
                    │ Analizar:                    │
                    │ - user_input                 │
                    │ - llm_response               │
                    │ Buscar preferencias nuevas   │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ↓ SÍ (detectadas)             ↓ NO
            ┌──────────────────┐      ┌─────────────────┐
            │ Crear/Actualizar │      │ Sin cambios     │
            │ memorias         │      │ Fin             │
            └──────────────────┘      └─────────────────┘
                    │
                    ↓
            ┌──────────────────────┐
            │ Si es NUEVA:         │
            │ - Crear MemoryItem   │
            │ - confidence=1.0     │
            │ - update_count=1     │
            │                      │
            │ Si EXISTE:           │
            │ - update_count++     │
            │ - confidence+=0.02   │
            │ - updated_at now     │
            └──────────────┬───────┘
                          │
                          ↓
            ┌──────────────────────────┐
            │ Guardar en MongoDB       │
            │ user_memories            │
            │                          │
            │ _id: ObjectId            │
            │ correo_usuario: email    │
            │ memories: [              │
            │   {...},                 │
            │   {...}                  │
            │ ]                        │
            │ updated_at: now          │
            └──────────────┬───────────┘
                          │
                          ↓
            ┌──────────────────────────┐
            │ 🎉 RESPUESTA AL USUARIO  │
            │ + Memorias Guardadas     │
            │ + Preferencias Recordadas│
            └──────────────────────────┘
```

---

## 🔁 Ciclo de Vida de una Memoria

```
┌─────────────────────────────────┐
│  DETECTADA                      │
│  (Conversa 1)                   │
│                                 │
│  idioma_preferido: español      │
│  confidence: 1.0                │
│  update_count: 1                │
└────────────┬────────────────────┘
             │
             ↓
┌─────────────────────────────────┐
│  CONFIRMADA                     │
│  (Conversa 2)                   │
│                                 │
│  confidence: 1.02 (aumentó)     │
│  update_count: 2                │
└────────────┬────────────────────┘
             │
             ↓
┌─────────────────────────────────┐
│  REFORZADA                      │
│  (Varias conversas)             │
│                                 │
│  confidence: 0.98 → 1.0         │
│  update_count: 5, 10, 20...     │
│  Emoji: ✅ (muy confiable)       │
└────────────┬────────────────────┘
             │
         ┌───┴────┬──────────┐
         │        │          │
         ↓        ↓          ↓
     ┌────┐  ┌──────┐  ┌────────┐
     │USA │  │REVIEW│  │ENABLED │
     │    │  │      │  │ FOREVER│
     └────┘  └──────┘  └────────┘
```

---

## 📋 Estado de Memoria según Confianza

```
┌─────────────┬─────────┬─────────────────────────┐
│ Confianza   │ Emoji   │ Significado             │
├─────────────┼─────────┼─────────────────────────┤
│ >= 0.95     │ ✅      │ MUY CONFIABLE           │
│  0.85-0.94  │ ✔️      │ CONFIABLE               │
│  0.70-0.84  │ ⚠️      │ MODERADA (revisar)      │
│  < 0.70     │ ❓      │ DUDOSA (confirmar)      │
└─────────────┴─────────┴─────────────────────────┘
```

---

## 🎭 Ejemplo: Conversa Completa

### **Conversación 1**
```
Usuario: "Prefiero que hables español y profesional"

FLOW:
1. Obtener/crear memorias ← Crea documento nuevo
2. Formatear memorias ← String vacío (sin memorias yet)
3. Agregar a prompt ← No hay mucho contexto
4. Invocar LLM ← Responde genéricamente
5. Detectar memorias ← DETECTA: idioma_preferido, tono
6. Guardar nuevas memorias ← INSERT en MongoDB

Resultado: 2 memorias guardadas
- idioma_preferido: "español" (conf: 1.0, count: 1)
- tono_comunicacion: "profesional" (conf: 1.0, count: 1)
```

### **Conversación 2**
```
Usuario: "¿Cuál es tu nombre?"

FLOW:
1. Obtener memorias ← OBTIENE del BD (2 memorias)
2. Formatear memorias ← 
   🌐 Idioma: español ✅
   🎭 Tono: profesional ✅
3. Agregar a prompt ← LLM RECIBE estas preferencias
4. Invocar LLM ← RESPONDE EN ESPAÑOL Y PROFESIONAL ✅
5. Detectar memorias ← Confirma idioma y tono
6. Actualizar memorias ← update_count: 2, confidence: 1.02

Resultado: Memorias confirmadas + LLM pide responder en español
```

### **Conversación 3+**
```
Usuario: "Trabaja con Gmail y Drive"

FLOW:
1. Obtener memorias ← OBTIENE (ahora con apps)
2. Formatear memorias ← 
   🌐 Idioma: español ✅
   🎭 Tono: profesional ✅
   🔧 Apps: Gmail, Drive ✅
3. Incluir en prompt ← LLM SABE las apps del usuario
4. Invocar agente + tools ← Usa Gmail y Drive
5. Detectar memorias ← AÑADE apps_frecuentes
6. Guardar ← INSERT nueva memoria o UPDATE si existe

Resultado: 3 memorias, todas con alta confianza
```

---

## 🔐 Garantías del Sistema

✅ **Privacidad** - Memorias almacenadas solo para ese usuario
✅ **Persistencia** - Guardadas en MongoDB, no se pierden
✅ **Escalabilidad** - Fácil agregar nuevas categorías/tipos
✅ **Auditabilidad** - Se registra cuándo/dónde se detectó
✅ **Flexibilidad** - Usuario puede revisar/editar memorias
✅ **Eficiencia** - Se usan solo las memorias relevantes

---

## 🚀 Ejemplo de JSON en MongoDB

```json
{
  "_id": ObjectId("507f1f77bcf86cd799439011"),
  "correo_usuario": "juan@empresa.com",
  "user_id": ObjectId("607f1f77bcf86cd799439012"),
  
  "memories": [
    {
      "key": "idioma_preferido",
      "value": "español",
      "category": "language",
      "confidence": 0.98,
      "source": "detected_pattern",
      "created_at": "2026-02-01T10:00:00Z",
      "updated_at": "2026-02-06T15:00:00Z",
      "update_count": 8,
      "metadata": {"variants": ["es", "español"]}
    },
    {
      "key": "tono_comunicacion",
      "value": "profesional_informal",
      "category": "tone",
      "confidence": 0.85,
      "source": "pattern_detected_from_interactions",
      "created_at": "2026-02-02T08:30:00Z",
      "updated_at": "2026-02-06T14:00:00Z",
      "update_count": 5
    },
    {
      "key": "apps_frecuentes",
      "value": ["Gmail", "Google Drive", "Slack"],
      "category": "apps",
      "confidence": 0.95,
      "source": "usage_tracking",
      "created_at": "2026-02-01T10:15:00Z",
      "updated_at": "2026-02-06T15:30:00Z",
      "update_count": 15
    }
  ],
  
  "created_at": "2026-02-01T08:00:00Z",
  "updated_at": "2026-02-06T15:30:00Z",
  "total_memories": 3,
  "average_confidence": 0.93,
  "is_active": true
}
```

---

## 💡 Casos de Uso

### **Caso 1: Usuario Multilingüe**
```
Conv 1: "Responde en inglés"
→ Detecta: idioma_preferido: english

Conv 2: "Ahora en español"
→ Detecta cambio, actualiza
→ Memoria evoluciona: último idioma es el preferido
```

### **Caso 2: Usuario con Múltiples Integraciones**
```
Conv 1: "Necesito Gmail"
→ Detecta: apps_frecuentes=[Gmail]

Conv 2: "Ahora Drive también"
→ Actualiza: apps_frecuentes=[Gmail, Drive]

Conv 3: "Slack también"
→ Actualiza: apps_frecuentes=[Gmail, Drive, Slack]
```

### **Caso 3: Usuario que Define Explícitamente**
```
Conv 1: "Soy Juan, ing. de software, trabajo en Tech Inc"
→ Detecta múltiples memorias:
   - personal_name: Juan
   - profession: Ingeniero de Software
   - company: Tech Inc
```

---

## 🎓 Diagrama de Clases

```
┌────────────────────────────────┐
│   UserMemoriesModel            │
├────────────────────────────────┤
│ - correo_usuario: str          │
│ - user_id: ObjectId            │
│ - memories: List[Memory]       │
│ - total_memories: int          │
│ - average_confidence: float    │
│ - is_active: bool              │
└────────────────────────────────┘
           │
           │ contains
           ↓
┌────────────────────────────────┐
│   MemoryItemModel              │
├────────────────────────────────┤
│ - key: str                     │
│ - value: Any                   │
│ - category: str                │
│ - confidence: float (0-1)      │
│ - update_count: int            │
│ - created_at: datetime         │
│ - updated_at: datetime         │
└────────────────────────────────┘

┌────────────────────────────────┐
│   UserMemoriesService          │
├────────────────────────────────┤
│ + get_or_create_memories()     │
│ + format_memories_for_llm()    │
│ + detect_and_update_memories() │
│ + _save_memories_to_db()       │
│ + get_memory_by_key()          │
│ + reset_memories()             │
└────────────────────────────────┘
           │
           │ uses
           ↓
┌────────────────────────────────┐
│   AgentService                 │
├────────────────────────────────┤
│ + _answer_without_tools()      │
│ + ejecutar_o_crear_proceso()   │
│ + _needs_tools()               │
│ + _detect_required_apps()      │
└────────────────────────────────┘
```

---

¿Necesitas ajustar algo del diagrama o la documentación?
