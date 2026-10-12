# Phase 13 — MCP & External Systems

**Estado:** ❌ No implementada (ni en v1 ni en v2)

---

## Qué hace

Shifu se conecta con sistemas externos via el protocolo MCP (Model Context Protocol), agentes externos, fuentes de conocimiento de terceros, y coordina acciones entre múltiples sistemas heterogéneos.

---

## Objetivos

| Objetivo | Estado | Descripción | Verificación en debug |
|----------|--------|-------------|----------------------|
| MCP Integration | ❌ | Shifu actúa como cliente MCP — se conecta a servidores MCP externos | Shifu puede usar herramientas de cualquier servidor MCP registrado |
| External Agents | ❌ | Delegar subtareas a agentes especializados (ej. agente de búsqueda, agente de código) | Logs muestran llamadas a agentes externos y sus respuestas |
| External Knowledge Sources | ❌ | Conectar con bases de conocimiento externas (RAG sobre docs del usuario, wikis, etc.) | Shifu cita fuentes externas en sus respuestas |
| External Services | ❌ | APIs externas sin OAuth (webhooks, REST APIs públicas, servicios internos) | Shifu puede consultar cualquier API configurada |
| Cross-System Coordination | ❌ | Orquestar acciones que cruzan múltiples sistemas en una sola operación | "Busqué en Notion, actualicé en Airtable, y te notifiqué en Slack" |

---

## Qué es MCP

MCP (Model Context Protocol) es un estándar abierto de Anthropic que permite a los LLMs conectarse con herramientas externas de forma estandarizada. En lugar de implementar una integración custom por cada servicio, un servidor MCP expone un conjunto de `tools` que el agente puede invocar.

**Ventaja sobre integraciones manuales:** cualquier sistema que implemente el protocolo MCP (hay cientos de servidores open source) está disponible para Shifu sin código adicional.

---

## Implementación propuesta

### Servidor MCP local (para empezar)

```python
# Shifu como cliente MCP
from mcp import ClientSession, StdioServerParameters

async def connect_mcp_server(server_name: str, command: str, args: list):
    server = StdioServerParameters(command=command, args=args)
    async with ClientSession(server) as session:
        tools = await session.list_tools()
        # tools disponibles para bind al LLM
```

### Integración en el graph

```
tool_context_loader → mcp_tools_loader → chat (con tools de MCP bound)
```

**Nuevo nodo: `mcp_tools_loader`**
- Lee la lista de servidores MCP configurados para el usuario/plataforma
- Se conecta a cada servidor y obtiene la lista de tools
- Agrega las tools al state para que `chat_node` las incluya en el LLM

### Configuración de servidores MCP

```json
{
  "mcp_servers": [
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/user-files"]
    },
    {
      "name": "google-drive",
      "command": "python",
      "args": ["-m", "mcp_google_drive"]
    }
  ]
}
```

---

## Casos de uso reales en debug

1. **Servidor MCP de archivos:** "analiza el CSV que subí" → Shifu lee el archivo via MCP
2. **Servidor MCP de búsqueda:** "busca en mi documentación sobre X" → RAG sobre docs del usuario
3. **Agente externo:** "genera el código de este workflow" → delega a agente de código especializado
4. **API interna:** "consulta el estado del servidor de producción" → llama a API interna via MCP

---

## Cómo verificarlo en la interfaz de debug

1. Configurar un servidor MCP simple (ej. filesystem)
2. Pedir: "lista los archivos que tengo disponibles"
3. Shifu debe invocar la tool del servidor MCP y listar los archivos
4. Logs: `[mcp_tools_loader] servers=1 tools=5` y `[tool_executor] tool=mcp:filesystem:list_directory`

---

## Dependencias

- Requiere Phase 11 ❌ (Tool Execution — el mecanismo de invocar tools es el mismo)
- No requiere DB nueva — la configuración de servidores MCP puede estar en MongoDB o en .env

---

## Prioridad sugerida

Baja en el corto plazo. Implementar después de que Phase 11 esté sólido. MCP se vuelve muy valioso cuando la plataforma quiere crecer rápido en integraciones sin implementar cada una manualmente.
