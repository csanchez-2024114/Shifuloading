# Plantilla para crear herramientas (modo bigtool)

Cada herramienta de una app se define con el decorador `@tool_spec` ([src/assistant/tool_spec.py](../src/assistant/tool_spec.py)). La ficha genera dos textos:

- **Lo que ve el modelo** cuando la herramienta está cargada: corto (`summary` + cuándo usarla + requisitos).
- **Lo que se indexa** para `retrieve_tools`: completo (app, recurso, acción, cuándo sí/no, parámetros, requisitos, etiquetas y ejemplos). De este texto depende que la búsqueda semántica elija bien.

Ejemplo completo y funcionando: [src/assistant/apps/crm_demo.py](../src/assistant/apps/crm_demo.py).

## Plantilla para copiar

```python
from assistant.tool_spec import AutoResolve, tool_spec


@tool_spec(
    app="myapp",                       # short app id; the tool name MUST start with "myapp_"
    resource="invoice",                # what it acts on (singular noun)
    action="create",                   # verb: create | get | list | update | delete | send | find_by_<x> ...
    summary="Create a new invoice for a customer in MyApp.",
    when_to_use="The user wants to issue/bill/charge a customer in MyApp.",
    when_not_to_use="To charge in OtherApp use otherapp_create_charge; to see invoices use myapp_list_invoices.",
    tags=["invoice", "billing", "charge", "factura"],
    examples=[                         # 5–10 real user requests, English AND Spanish
        "create an invoice for ACME for 500 USD",
        "factura 3 horas de consultoría a Ana",
        "bill customer 42 for the October subscription",
    ],
    requires={"customer_id": ["myapp_find_customer_by_email", "myapp_list_customers"]},  # optional
    auto={"customer_id": AutoResolve(source="myapp_find_customer_by_email",              # optional
                                     args={"email": "customer_email"}, field="id")},
    effect="write",                    # read | write
)
def myapp_create_invoice(amount: float, concept: str, customer_id: str = "", customer_email: str = "") -> dict:
    """Create an invoice.

    Args:
        amount: Total amount in the account currency.
        concept: What is being billed.
        customer_id: MyApp customer id. Get it with myapp_find_customer_by_email or myapp_list_customers.
        customer_email: Customer email; used to resolve customer_id automatically when it is missing.
    """
    ...
```

Después agrega la lista de herramientas de la app a `build_registry` en [bigtool_agent.py](../src/assistant/bigtool_agent.py), como `crm_tools()`.

## Reglas

**Idioma:** todo lo programado va en inglés: nombres de herramientas y parámetros, `summary`, `when_to_use`, `when_not_to_use`, `tags`, docstrings y mensajes. La única excepción son `examples` (y opcionalmente algunas `tags`), que llevan frases en inglés **y** español, porque son ejemplos de cómo escriben los usuarios.

**Nombres:** `app_resource_action` en snake_case (`crm_create_order`, `jira_list_issues`). El prefijo de app es obligatorio: con 30 apps habrá muchas `create_*` parecidas, y el prefijo evita choques.

**`summary`:** una frase con verbo y objeto que diga qué hace, en qué app y qué devuelve.

**`when_to_use` / `when_not_to_use`:** escribe la intención del usuario, no la API. En `when_not_to_use` nombra la herramienta parecida que debe usarse en su lugar, incluida la de otra app. Esto es lo que más ayuda a distinguir funciones casi iguales.

**`examples`:** de 5 a 10 peticiones reales y variadas, con sinónimos, en inglés y español, mencionando la app cuando sea natural. Es la técnica con mejor evidencia para mejorar la búsqueda. No pongas llamadas de API ni JSON: empeoran la búsqueda.

**`tags`:** de 3 a 6 palabras clave (sinónimos y términos de negocio).

**Docstring:** un bloque `Args:` con una línea por parámetro. Se usa para describir los parámetros, tanto al modelo como al índice.

**`effect`:** `read` si solo consulta y `write` si crea, modifica, borra o envía. Hoy es informativo; servirá para pedir aprobación humana en las de escritura.

## Pre-funciones: cuando un dato se obtiene antes

Muchas funciones necesitan un dato que se consigue con otra función, a veces por más de un camino. Por ejemplo, `customer_id` se obtiene por email **o** listando clientes.

### 1. `requires`: el agente llama la pre-función (recomendado siempre)

```python
requires={"customer_id": ["crm_find_customer_by_email", "crm_list_customers"]}
```

- Cuando `retrieve_tools` encuentra esta herramienta, **agrega automáticamente sus pre-funciones** al alcance del agente (hasta 2 niveles), aunque la búsqueda no las haya traído.
- La descripción que ve el modelo dice: *"Requires customer_id: get it first with crm_find_customer_by_email or crm_list_customers"*.
- El agente elige el camino según lo que tenga: email, nombre, etc.
- Si la función se llama sin el dato, no se ejecuta: devuelve un error que indica con qué funciones obtenerlo.
- El parámetro requerido debe tener valor por defecto vacío (`customer_id: str = ""`).

### 2. `auto`: encadenado automático (opcional, cuando el camino es fijo)

```python
auto={"customer_id": AutoResolve(source="crm_find_customer_by_email",
                                 args={"email": "customer_email"},  # source_param: this_tool_param
                                 field="id")}                       # key of the source result
```

- Si falta `customer_id` pero viene `customer_email`, el sistema ejecuta `crm_find_customer_by_email(email=customer_email)` y usa `resultado["id"]`. Es una sola llamada del modelo en vez de dos.
- Si la pre-función no encuentra nada, devuelve un error con la alternativa (*"Try crm_list_customers…"*) para que el agente siga por el otro camino.
- La pre-función debe devolver un `dict` con ese campo.

## Validación al arrancar

Si algo está mal, el servidor no arranca y lista todos los problemas. Valida:
- el prefijo de app en el nombre;
- los campos obligatorios vacíos;
- que haya al menos 2 `examples`;
- que `effect` sea `read` o `write`;
- que cada pre-función de `requires` y cada `source` de `auto` existan en el registro;
- que los parámetros de `auto` existan en ambas funciones.

## Checklist rápido

- [ ] Nombre `app_resource_action` en inglés
- [ ] `summary` con verbo + objeto + app
- [ ] `when_to_use` en términos del usuario, y `when_not_to_use` que nombre la herramienta alternativa
- [ ] 5–10 `examples` en inglés y español, variados
- [ ] Docstring con `Args:` para cada parámetro
- [ ] `requires` para cada dato que se obtiene con otra función, con sus alternativas
- [ ] `auto` solo si el camino es siempre el mismo
- [ ] `effect` correcto
- [ ] Sin efectos reales mientras el modo bigtool no tenga aprobación humana
