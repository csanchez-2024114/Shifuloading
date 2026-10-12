# Integración LangGraph + JIRA - Guía de Implementación

## Archivo: `app/agents/tools/jira_tool.py`

### Características Implementadas

- **4 Tools completos**: Crear tickets, listar proyectos, obtener issue, buscar con JQL
- **Inyección de Sesión Segura**: El `user_id` se obtiene automáticamente de `flask.session` (transparente para la IA)
- **Validación robusta**: Pydantic schemas limpios sin exponer IDs internos
- **Manejo de errores profesional**: Mensajes útiles para el agente
- **Logging detallado**: Todos los pasos están logueados
- **Type hints completos**: Código totalmente tipado
- **Documentación inline**: Docstrings en todas las funciones

### Uso Básico en LangGraph

**Nota Crítica:** Como los tools usan `flask.session`, el agente debe ser invocado dentro de un contexto de solicitud HTTP (una ruta de Flask).

```python
from app.agents.tools.jira_tool import jira_tools
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

# 1. Crear agente con tools de JIRA
llm = ChatOpenAI(model="gpt-4")
agent = create_react_agent(llm, jira_tools)

# 2. Invocar el agente (Dentro de una ruta/request)
result = agent.invoke({
    "input": "Crea un ticket en el proyecto DEV sobre un bug en el login",
    # El user_id NO se pasa al tool, lo toma de la sesión activa
    "chat_history": []
})

# El agente automáticamente:
# - Detecta que necesita crear un ticket
# - Llama a create_jira_ticket_tool (SIN parámetro user_id)
# - El tool inyecta el ID desde la sesión
# - Ejecuta JiraService y retorna el resultado

Integración con Sistema Existente
Opción A: Agregar a lista de tools existente
# En tu archivo de agente principal
from app.agents.tools.jira_tool import jira_tools
# from app.agents.tools.gmail_tool import gmail_tools

all_tools = [
    *jira_tools,
    # *gmail_tools,
    # ... otros tools
]

agent = create_react_agent(llm, all_tools)

Opción B: Tools dinámicos por usuario
from app.agents.tools.jira_tool import get_jira_tools_for_agent

def get_tools_for_user(user_id: str):
    """Obtiene tools basados en las integraciones del usuario"""
    tools = []
    
    # Verificar qué integraciones tiene el usuario en DB
    user = db.usuarios.find_one({"_id": user_id})
    integrations = user.get("integrations", {})
    
    if "jira" in integrations:
        # Ya no requiere user_id explícito, pero se mantiene compatible
        tools.extend(get_jira_tools_for_agent())
    
    if "gmail" in integrations:
        tools.extend(get_gmail_tools_for_agent(user_id))
    
    return tools

# Uso
tools = get_tools_for_user("507f...")
agent = create_react_agent(llm, tools)

Ejemplos de Conversaciones
Ejemplo 1: Crear ticket básico
Usuario: "Crea un ticket en DEV sobre el bug del login"
Agente: [llama a create_jira_ticket_tool]
Response: "Ticket DEV-42 creado exitosamente. Puedes verlo en: https://..."

Ejemplo 2: Crear ticket con contexto complejo
Usuario: "Tenemos un problema crítico: cuando el usuario intenta hacer login 
          con Google OAuth, el botón no responde. Solo pasa en Chrome. 
          Crea un bug de alta prioridad en el proyecto BUGS"

Agente: [analiza el contexto y llama a create_jira_ticket_tool con]
{
  "project_key": "BUGS",
  "summary": "Botón de login con Google OAuth no responde en Chrome",
  "description": "Problema crítico: el botón de OAuth de Google no responde al hacer clic. Solo ocurre en navegador Chrome.",
  "issue_type": "Bug",
  "priority": "High"
}
# NOTA: El agente NO inventa ni envía user_id.

Response: "Bug BUGS-123 creado con prioridad High"

Ejemplo 3: Búsqueda inteligente (JQL)
Usuario: "Muéstrame todos los bugs abiertos que me asignaron esta semana"
Agente: [llama a search_jira_issues_tool con JQL]
JQL: "assignee = currentUser() AND type = Bug AND status = Open AND created >= -7d"
Response: "Encontré 3 bugs: BUGS-45, BUGS-67, BUGS-89"
🔍 Debugging
Para probar las funciones individualmente, debes simular un contexto de Flask, ya que ahora dependen de session.

Ver logs de los tools:
import logging
logging.getLogger('app.agents.tools.jira_tool').setLevel(logging.DEBUG)

Probar tools individualmente (Script de prueba):
from flask import Flask, session
from app.agents.tools.jira_tool import create_jira_ticket_function

# Configurar mini-app para testing
app = Flask(__name__)
app.secret_key = 'test_key'

# Envolver en contexto de solicitud
with app.test_request_context():
    # 1. Simular Login
    session['user_id'] = "507f1f77bcf86cd799439011" # ID Real de Mongo
    
    # 2. Ejecutar función (Sin user_id como argumento)
    result = create_jira_ticket_function(
        project_key="DEV",
        summary="Test ticket desde debug",
        description="Probando inyección de sesión"
    )
    print(result)

    Manejo de Errores Comunes
Error 1: Usuario sin sesión (Authentication required)
Si se ejecuta fuera de una request web:
# El tool retorna:
{
    "success": False,
    "error": "auth_error",
    "message": "Authentication required: No hay usuario en sesión."
}

Error 2: Usuario sin JIRA conectado
# El tool retorna:
{
    "success": False,
    "error": "auth_required",
    "message": "Necesitas conectar tu cuenta de JIRA en Configuración."
}

# El agente debe responder:
"Para crear tickets en JIRA, primero necesitas conectar tu cuenta. 
 Ve a Configuración → Integraciones → JIRA"

 Error 3: Proyecto no existe
 # El tool retorna:
{
    "success": False,
    "error": "api_error",
    "message": "El proyecto 'XYZ' no existe o no tienes permisos..."
}

mejores practicas
No pedir el ID al usuario: El sistema lo maneja internamente.

Usa get_jira_projects_tool cuando no estés seguro del project_key.

Proporciona contexto al agente: El summary y description deben ser claros.

Validar conexión: El tool valida automáticamente si hay token, pero el agente debe saber explicar si falta la conexión.

Dependencias Requeridas
pip install langchain langchain-openai pydantic flask

Archivos Relacionados
app/services/jira_service.py - Lógica de negocio

app/routes/auth_jira.py - OAuth endpoints

Esta documentación asume que el OAuth ya está configurado

