# 🔗 Guía: Vinculación Bidireccional en Entity-Aware Memories

## 🎯 Problema Resuelto

### ❌ Problema Original

Cuando preguntabas **"¿Quién está en la empresa?"**, el sistema:

1. Buscaba en `entity_registry["company_hyper_reality"]`
2. Solo encontraba `memory_ids` de memorias de la empresa
3. **NO encontraba a Carlos Mendoza** (CEO) porque:
   - Carlos vive en `entity_registry["person_carlos_mendoza"]`
   - Su relación "ceo_of" apunta DESDE Carlos HACIA la empresa
   - No había referencia inversa

**Resultado:** El LLM no podía responder "Carlos es el CEO" sin escanear TODAS las memorias O(n).

---

### ✅ Solución: Vinculación Bidireccional

Ahora, cuando se guarda una memoria con `relations`, el sistema actualiza **AMBAS entidades**:

1. **Entidad principal (Carlos)** → Agrega relación "outgoing" hacia la empresa
2. **Entidad relacionada (Empresa)** → Agrega relación "incoming" desde Carlos

**Resultado:** Lookup O(1) para preguntas como "¿Quién está en la empresa?"

---

## 📊 Estructura del Entity Registry Mejorado

### Antes (Sin Vinculación)

```json
{
  "entity_registry": {
    "company_hyper_reality": {
      "entity_type": "company",
      "entity_name": "Hyper Reality",
      "memory_ids": ["mem_abc123"]
      // ❌ No hay referencia a Carlos
    },
    "person_carlos_mendoza": {
      "entity_type": "person",
      "entity_name": "Carlos Mendoza",
      "memory_ids": ["mem_def456"]
      // Su relación vive en la memoria, no en el registry
    }
  }
}
```

### Ahora (Con Vinculación Bidireccional)

```json
{
  "entity_registry": {
    "company_hyper_reality": {
      "entity_type": "company",
      "entity_name": "Hyper Reality",
      "memory_ids": ["mem_abc123"],
      
      // ✅ NUEVO: Referencias inversas
      "related_entities": [
        {
          "entity_id": "person_carlos_mendoza",
          "entity_name": "Carlos Mendoza",
          "entity_type": "person",
          "relation_type": "has_ceo",  // Invertido de "ceo_of"
          "direction": "incoming",     // La relación viene HACIA la empresa
          "memory_id": "mem_def456"
        },
        {
          "entity_id": "user_main",
          "entity_name": "Alan",
          "entity_type": "user",
          "relation_type": "employs",  // Invertido de "works_at"
          "direction": "incoming",
          "memory_id": "mem_ghi789"
        }
      ]
    },
    
    "person_carlos_mendoza": {
      "entity_type": "person",
      "entity_name": "Carlos Mendoza",
      "memory_ids": ["mem_def456"],
      
      "related_entities": [
        {
          "entity_id": "company_hyper_reality",
          "entity_name": "Hyper Reality",
          "entity_type": "company",
          "relation_type": "ceo_of",   // Original
          "direction": "outgoing",      // La relación sale DESDE Carlos
          "memory_id": "mem_def456"
        }
      ]
    },
    
    "user_main": {
      "entity_type": "user",
      "entity_name": "Alan",
      "memory_ids": ["mem_ghi789"],
      
      "related_entities": [
        {
          "entity_id": "company_hyper_reality",
          "entity_name": "Hyper Reality",
          "entity_type": "company",
          "relation_type": "works_at",
          "direction": "outgoing",
          "memory_id": "mem_ghi789"
        }
      ]
    }
  }
}
```

---

## 🚀 Cómo Funciona

### 1. Guardado de Memoria con Relación

```python
# Usuario dice: "Carlos Mendoza es nuestro CEO en Hyper Reality"

# LLM genera memoria para Carlos:
{
  "memory_id": "mem_def456",
  "key": "ceo_name",
  "value": "Carlos Mendoza",
  "subject": {
    "entity_id": "person_carlos_mendoza",
    "entity_type": "person",
    "entity_name": "Carlos Mendoza"
  },
  "relations": [
    {
      "related_key": "company_name",  # Apunta a la empresa
      "relation_type": "ceo_of"
    }
  ]
}
```

### 2. Actualización Automática del Entity Registry

El método `_update_entity_registry()` hace:

**A) Actualiza entidad principal (Carlos):**
```python
entity_registry["person_carlos_mendoza"]["related_entities"].append({
  "entity_id": "company_hyper_reality",
  "entity_name": "Hyper Reality",
  "entity_type": "company",
  "relation_type": "ceo_of",
  "direction": "outgoing",  # Sale DESDE Carlos
  "memory_id": "mem_def456"
})
```

**B) Actualiza entidad relacionada (Empresa):**
```python
entity_registry["company_hyper_reality"]["related_entities"].append({
  "entity_id": "person_carlos_mendoza",
  "entity_name": "Carlos Mendoza",
  "entity_type": "person",
  "relation_type": "has_ceo",  # Invertido de "ceo_of"
  "direction": "incoming",     # Viene HACIA la empresa
  "memory_id": "mem_def456"
})
```

---

## 💡 Casos de Uso

### Caso 1: "¿Quién está en la empresa?"

```python
from app.agents.user_memories_service import UserMemoriesService

service = UserMemoriesService("user@example.com")
memory_doc = service.get_or_create_memories()

# Obtener todas las personas relacionadas con la empresa
people = service.get_related_entities(
    memory_doc,
    entity_id="company_hyper_reality",
    direction="incoming"  # Solo relaciones que apuntan HACIA la empresa
)

for person in people:
    print(f"{person['entity_name']} - {person['relation_type']}")
# Output:
# Carlos Mendoza - has_ceo
# Alan - employs
```

**Complejidad:** O(1) (lookup directo en entity_registry)

---

### Caso 2: "¿En qué empresas trabaja Carlos?"

```python
companies = service.get_related_entities(
    memory_doc,
    entity_id="person_carlos_mendoza",
    direction="outgoing",
    relation_type="ceo_of"
)

for company in companies:
    print(f"{company['entity_name']}")
# Output:
# Hyper Reality
```

---

### Caso 3: "Dame todas las relaciones de la empresa"

```python
# Sin filtros → obtiene incoming + outgoing
all_relations = service.get_related_entities(
    memory_doc,
    entity_id="company_hyper_reality"
)

for rel in all_relations:
    direction_symbol = "←" if rel['direction'] == "incoming" else "→"
    print(f"{direction_symbol} {rel['entity_name']} ({rel['relation_type']})")
# Output:
# ← Carlos Mendoza (has_ceo)
# ← Alan (employs)
# → Proyecto Alpha (owns_project)
```

---

## 🔄 Inversión de Tipos de Relación

El sistema invierte automáticamente los tipos de relación:

| Original (Outgoing) | Invertido (Incoming) |
|---------------------|---------------------|
| `ceo_of` | `has_ceo` |
| `works_at` | `employs` |
| `founded_by` | `founder_of` |
| `owns` | `owned_by` |
| `member_of` | `has_member` |
| `manages` | `managed_by` |

**Heurísticas:**
- Si termina en `_of` → Invierte a `has_{base}`
- Si empieza con `has_` → Invierte a `{base}_of`
- Relaciones simétricas (ej: `works_with`) → Se mantienen iguales

Puedes personalizar el mapeo en `_invert_relation_type()`.

---

## 📝 API Completa

### `get_related_entities()`

```python
def get_related_entities(
    self,
    memory_doc: Dict[str, Any],
    entity_id: str,
    relation_type: Optional[str] = None,
    direction: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Obtiene entidades relacionadas con una entidad específica.
    
    Args:
        memory_doc: Documento de memorias
        entity_id: ID de la entidad base
        relation_type: Filtrar por tipo (ej: "has_ceo", "employs")
        direction: Filtrar por dirección ("incoming", "outgoing", None=ambas)
    
    Returns:
        Lista de entidades relacionadas
    """
```

**Ejemplos:**

```python
# Todas las relaciones
all = service.get_related_entities(doc, "company_hyper_reality")

# Solo personas que trabajan EN la empresa (incoming)
employees = service.get_related_entities(
    doc, 
    "company_hyper_reality",
    direction="incoming"
)

# Solo CEOs de la empresa
ceos = service.get_related_entities(
    doc,
    "company_hyper_reality",
    relation_type="has_ceo",
    direction="incoming"
)

# Empresas PARA las que trabaja una persona (outgoing)
companies = service.get_related_entities(
    doc,
    "person_carlos_mendoza",
    direction="outgoing"
)
```

---

## 🔍 Formato para el LLM

Cuando el LLM consulta memorias, ahora ve:

```
🧠 MEMORIA Y CONTEXTO DEL USUARIO:
================================================================================

┌─ Hyper Reality (company)
│
│  🔗 ENTIDADES RELACIONADAS:
│     ← Carlos Mendoza (has_ceo)
│     ← Alan (employs)
│
│  ✓ company_name: Hyper Reality
│     → Hyper Reality es la empresa donde trabaja el usuario.
│     🔗 Relaciones: has_ceo(ceo_name)
│     (confianza: 0.95)
│
└─────────────────────────────────────────

┌─ Carlos Mendoza (person)
│
│  🔗 ENTIDADES RELACIONADAS:
│     → Hyper Reality (ceo_of)
│
│  ✓ ceo_name: Carlos Mendoza
│     → Carlos Mendoza es el CEO de Hyper Reality.
│     🔗 Relaciones: ceo_of(company_name)
│     (confianza: 0.95)
│
└─────────────────────────────────────────
```

**Ventajas:**
- El LLM ve directamente quién está relacionado con la empresa
- No necesita escanear todas las memorias
- Puede responder preguntas de contexto inmediatamente

---

## ✅ Validación

### Test de Vinculación Bidireccional

```bash
python test_entity_aware_memories.py
```

El **Test 4** valida:
- ✅ Cada entidad tiene `related_entities`
- ✅ Relaciones outgoing tienen su inversa incoming
- ✅ No hay relaciones huérfanas

El **Test 7** valida:
- ✅ Caso de uso "¿Quién está en la empresa?"
- ✅ Comparación O(1) vs O(n)
- ✅ Ambos métodos retornan el mismo resultado

---

## 🎯 Beneficios

### Performance

| Operación | Antes (Sin Vinculación) | Ahora (Con Vinculación) |
|-----------|------------------------|------------------------|
| "¿Quién es el CEO?" | O(n) - Escanear todas las memorias | O(1) - Lookup directo |
| "¿En qué empresa trabaja X?" | O(n) | O(1) |
| "Lista todo el equipo" | O(n) | O(1) |

### Usabilidad

- ✅ Queries más rápidas
- ✅ Menos latencia en respuestas del LLM
- ✅ Soporte nativo para preguntas de contexto
- ✅ No necesita RAG/embeddings para relaciones simples

### Escalabilidad

- Si tienes 1000 memorias:
  - **Antes:** Escanear 1000 memorias para encontrar el CEO
  - **Ahora:** 1 lookup en `entity_registry`

---

## 🔧 Troubleshooting

### Problema: "No se encontraron entidades relacionadas"

**Posibles causas:**
1. La memoria no tiene `relations` definidas
2. El `related_key` no coincide con ninguna memoria existente
3. La relación no se procesó correctamente

**Solución:**
```python
# Verificar que la memoria tiene relations
memory = service.get_memory_by_id(doc, "mem_abc123")
print(memory.get("relations"))

# Verificar entity_registry
print(doc["entity_registry"])
```

### Problema: "Relaciones unidireccionales detectadas"

**Causa:** La entidad relacionada no existe aún en el registry cuando se crea la relación.

**Solución:** El sistema debería crear la entidad automáticamente. Si no lo hace, revisa `_update_entity_registry()`.

---

## 📚 Lecturas Relacionadas

- [ENTITY_AWARE_MEMORIES_GUIDE.md](./ENTITY_AWARE_MEMORIES_GUIDE.md) - Guía completa del sistema
- [ENTITY_AWARE_IMPLEMENTATION.md](./ENTITY_AWARE_IMPLEMENTATION.md) - Detalles de implementación
- [test_entity_aware_memories.py](./test_entity_aware_memories.py) - Suite de tests

---

**Versión:** 2.1.0 (Vinculación Bidireccional)  
**Fecha:** 2026-02-07  
**Autor:** Hyper Shifu AI Team
