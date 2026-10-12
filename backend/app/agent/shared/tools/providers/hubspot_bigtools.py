from typing import List, Optional, Type, Any
from dataclasses import dataclass
from pydantic import BaseModel, Field

@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None

def get_hubspot_bigtools(user_email: str) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de HubSpot para un usuario específico.
    
    Args:
        user_email: Email del usuario para autenticación en HubSpot
        
    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    from app.tools.connectors.hubspotTool import HubspotToolProvider
    provider = HubspotToolProvider(user_email)
    return [BigTool(name='obtener_informacion_cuenta_hubspot', description='Devuelve información general de la cuenta HubSpot autenticada, incluyendo ID de portal, zona horaria, tipo de cuenta, moneda, y más.', tool=provider.get_tool_account_information()), BigTool(name='listar_usuarios_portal_hubspot', description='Lista los usuarios del portal HubSpot. Devuelve su ID, nombre, correo, rol, y estado (activo o no).', tool=provider.get_tool_portal_users()), BigTool(name='listar_roles_portal_hubspot', description='Lista los roles disponibles en el portal de HubSpot. Devuelve su ID, nombre, descripción y permisos asociados.', tool=provider.get_tool_roles()), BigTool(name='listar_equipos_portal_hubspot', description='Lista los equipos (teams) del portal de HubSpot. Devuelve su ID, nombre, correo del manager, cantidad de miembros y estado.', tool=provider.get_tool_teams()), BigTool(name='listar_contactos_hubspot', description='Lista todos los contactos registrados en HubSpot. Devuelve su ID, nombre, correo, teléfono y fecha de creación.', tool=provider.get_tool_listar_contactos()), BigTool(name='buscar_contacto_por_id_hubspot', description='Obtiene los detalles de un contacto de HubSpot usando su ID. Devuelve su nombre, correo, teléfono y empresa asociada.', tool=provider.get_tool_buscar_contacto_por_id()), BigTool(name='listar_propiedades_contactos_hubspot', description='Lista todas las propiedades configuradas para los contactos, incluyendo su nombre, etiqueta visible, tipo y descripción.', tool=provider.get_tool_listar_propiedades_contactos()), BigTool(name='listar_companias_hubspot', description='Lista todas las compañías registradas en HubSpot. Incluye nombre, sitio web, industria, ciudad, país y etapa del ciclo de vida.', tool=provider.get_tool_listar_companias()), BigTool(name='buscar_compania_por_id_hubspot', description='Obtiene los detalles de una compañía específica usando su ID. Devuelve nombre, sitio web, teléfono, dirección, país e industria.', tool=provider.get_tool_buscar_compania_por_id()), BigTool(name='listar_propiedades_companias_hubspot', description='Lista un subconjunto (máx. 25) de las propiedades configuradas para las compañías en HubSpot, incluyendo su nombre, etiqueta visible, tipo y descripción.', tool=provider.get_tool_listar_propiedades_companias()), BigTool(name='listar_deals_hubspot', description='Lista todos los negocios (deals) registrados en HubSpot, incluyendo su nombre, monto, etapa del pipeline y fecha de cierre.', tool=provider.get_tool_listar_deals()), BigTool(name='buscar_deal_por_id_hubspot', description='Obtiene los detalles de un negocio específico usando su ID. Devuelve nombre, monto, etapa, pipeline y fechas relevantes.', tool=provider.get_tool_buscar_deal_por_id()), BigTool(name='listar_propiedades_deals_hubspot', description='Lista un subconjunto (máx. 25) de las propiedades configuradas para los negocios (deals) en HubSpot, incluyendo su nombre, etiqueta visible, tipo y descripción.', tool=provider.get_tool_listar_propiedades_deals()), BigTool(name='listar_tickets_hubspot', description='Lista todos los tickets registrados en HubSpot Service Hub. Devuelve su ID, asunto, estado, prioridad, pipeline y fecha de creación.', tool=provider.get_tool_listar_tickets()), BigTool(name='buscar_ticket_por_id_hubspot', description='Obtiene los detalles de un ticket específico usando su ID. Devuelve el asunto, contenido, estado, prioridad y pipeline.', tool=provider.get_tool_buscar_ticket_por_id()), BigTool(name='listar_propiedades_tickets_hubspot', description='Lista un subconjunto (máx. 25) de las propiedades configuradas para los tickets en HubSpot, incluyendo su nombre, etiqueta visible, tipo y descripción.', tool=provider.get_tool_listar_propiedades_tickets()), BigTool(name='listar_productos_hubspot', description='Lista los productos registrados en HubSpot, incluyendo nombre, precio, descripción y SKU.', tool=provider.get_tool_listar_productos()), BigTool(name='buscar_producto_por_id_hubspot', description='Obtiene la información detallada de un producto en HubSpot usando su ID.', tool=provider.get_tool_buscar_producto_por_id()), BigTool(name='listar_items_linea_hubspot', description='Lista los ítems de línea (productos asociados a negocios) registrados en HubSpot.', tool=provider.get_tool_listar_items_linea()), BigTool(name='listar_cotizaciones_hubspot', description='Lista las cotizaciones (quotes) creadas en HubSpot, incluyendo su título, estado y monto.', tool=provider.get_tool_listar_cotizaciones()), BigTool(name='buscar_asociaciones_hubspot', description='Devuelve los objetos relacionados en HubSpot. Ejemplo: contactos ↔ deals, deals ↔ companies, tickets ↔ contacts. Requiere especificar los tipos: from_type, from_id y to_type.', tool=provider.get_tool_buscar_asociaciones()), BigTool(name='listar_tipos_asociaciones_hubspot', description='Lista todos los tipos de asociaciones configuradas entre objetos del CRM, como contactos, empresas, deals, tickets o productos.', tool=provider.get_tool_listar_tipos_asociaciones()), BigTool(name='listar_asociaciones_hubspot', description='Lista todos los objetos relacionados (asociaciones) a un registro del CRM, como contactos, compañías, deals, etc.', tool=provider.get_tool_listar_asociaciones()), BigTool(name='listar_pipelines_hubspot', description='Lista los pipelines configurados para un tipo de objeto del CRM (por ejemplo: deals o tickets). Devuelve su ID, nombre y estado activo.', tool=provider.get_tool_listar_pipelines()), BigTool(name='listar_etapas_pipeline_hubspot', description='Muestra las etapas de un pipeline específico dentro del CRM de HubSpot. Incluye ID, nombre y metadatos de cada etapa.', tool=provider.get_tool_listar_etapas_pipeline()), BigTool(name='detalles_pipeline_hubspot', description='Devuelve información completa de un pipeline específico, incluyendo etapas, metadatos y orden.', tool=provider.get_tool_detalles_pipeline()), BigTool(name='listar_owners_hubspot', description='Lista todos los dueños o responsables activos del CRM en HubSpot, con su ID, nombre y correo.', tool=provider.get_tool_listar_owners()), BigTool(name='resumen_general_crm_hubspot', description='Devuelve un resumen general del CRM, incluyendo los tipos de objetos y el número de propiedades disponibles.', tool=provider.get_tool_resumen_crm()), BigTool(name='listar_emails_hubspot', description='Lista todos los correos electrónicos registrados en el CRM de HubSpot, incluyendo asunto, remitente y estado.', tool=provider.get_tool_listar_emails()), BigTool(name='listar_llamadas_hubspot', description='Lista todas las llamadas registradas en el CRM de HubSpot, incluyendo título, duración y estado.', tool=provider.get_tool_listar_llamadas()), BigTool(name='listar_reuniones_hubspot', description='Lista todas las reuniones registradas en HubSpot con su hora de inicio, fin y resultado.', tool=provider.get_tool_listar_reuniones()), BigTool(name='listar_notas_hubspot', description='Lista todas las notas registradas en el CRM de HubSpot con título, contenido y fechas de creación.', tool=provider.get_tool_listar_notas()), BigTool(name='historial_actividades_hubspot', description='Muestra el historial completo de actividades (emails, llamadas, reuniones, notas) relacionadas con un registro del CRM.', tool=provider.get_tool_historial_actividades()), BigTool(name='listar_grupos_propiedades_hubspot', description='Devuelve los grupos de propiedades disponibles para un objeto (contacto, compañía, deal, etc.)', tool=provider.get_tool_listar_grupos_propiedades()), BigTool(name='listar_dashboards_hubspot', description='Lista todos los dashboards e informes configurados en el portal de HubSpot.', tool=provider.get_tool_listar_dashboards()), BigTool(name='crear_contacto_hubspot', description='Crea un nuevo contacto en HubSpot con los campos email, nombre, apellido, teléfono, empresa y estado del lead.', tool=provider.get_tool_crear_contacto()), BigTool(name='crear_compania_hubspot', description='Crea una nueva compañía en HubSpot con nombre, dominio, teléfono, ciudad, país e industria.', tool=provider.get_tool_crear_compania()), BigTool(name='crear_deal_hubspot', description='Crea un nuevo Deal (negocio) en HubSpot con nombre, monto, etapa, pipeline y contactos asociados.', tool=provider.get_tool_crear_deal()), BigTool(name='crear_ticket_hubspot', description='Crea un nuevo Ticket de soporte en HubSpot con asunto, contenido y contacto asociado.', tool=provider.get_tool_crear_ticket()), BigTool(name='crear_producto_hubspot', description='Crea un nuevo Producto en HubSpot con nombre, precio, SKU, descripción y moneda.', tool=provider.get_tool_crear_producto()), BigTool(name='crear_nota_hubspot', description='Crea una nueva Nota en HubSpot, opcionalmente asociada a un contacto, deal o ticket.', tool=provider.get_tool_crear_nota()), BigTool(name='crear_tarea_hubspot', description='Crea una tarea en HubSpot con título, fecha límite, notas y contacto asociado.', tool=provider.get_tool_crear_tarea()), BigTool(name='crear_llamada_hubspot', description='Registra una llamada en HubSpot con título, estado, duración y notas.', tool=provider.get_tool_crear_llamada()), BigTool(name='actualizar_contacto_hubspot', description='Actualiza los campos de un contacto existente en HubSpot. Envía el ID y un diccionario con las propiedades.', tool=provider.get_tool_actualizar_contacto()), BigTool(name='actualizar_compania_hubspot', description='Actualiza los datos de una compañía existente en HubSpot. Envía el ID y las propiedades a modificar.', tool=provider.get_tool_actualizar_compania()), BigTool(name='actualizar_deal_hubspot', description='Actualiza los datos de un Deal existente (por ejemplo nombre, monto o etapa).', tool=provider.get_tool_actualizar_deal()), BigTool(name='actualizar_ticket_hubspot', description='Actualiza un ticket de soporte en HubSpot. Envía el ID y las propiedades a modificar.', tool=provider.get_tool_actualizar_ticket()), BigTool(name='actualizar_producto_hubspot', description='Actualiza un producto en HubSpot con nuevas propiedades como nombre, precio o descripción.', tool=provider.get_tool_actualizar_producto()), BigTool(name='actualizar_nota_hubspot', description='Actualiza el cuerpo o contenido de una nota existente en HubSpot.', tool=provider.get_tool_actualizar_nota()), BigTool(name='asociar_objetos_hubspot', description='Asocia dos objetos del CRM, como contacto→compañía o deal→ticket.', tool=provider.get_tool_asociar_objetos()), BigTool(name='actualizar_propietario_hubspot', description='Cambia el propietario (usuario asignado) de un contacto, compañía o deal.', tool=provider.get_tool_actualizar_propietario()), BigTool(name='actualizar_etapa_pipeline_hubspot', description="Actualiza la etapa del pipeline de un Deal o Ticket (por ejemplo, mover de 'appointment scheduled' a 'closed won').", tool=provider.get_tool_actualizar_etapa_pipeline())]

def get_hubspot_tools_by_category(user_email: str, category: str='all') -> List[BigTool]:
    """
    Obtiene herramientas de HubSpot filtradas por categoría.
    
    Categories: "account", "contacts", "companies", "deals", "tickets", 
                "products", "associations", "pipelines", "activities", 
                "create", "update", "all"
    """
    all_tools = get_hubspot_bigtools(user_email)
    if category == 'all':
        return all_tools
    category_mapping = {'account': ['informacion_cuenta', 'usuarios_portal', 'roles_portal', 'equipos_portal'], 'contacts': ['contactos', 'contacto_por_id', 'propiedades_contactos'], 'companies': ['companias', 'compania_por_id', 'propiedades_companias'], 'deals': ['deals', 'deal_por_id', 'propiedades_deals'], 'tickets': ['tickets', 'ticket_por_id', 'propiedades_tickets'], 'products': ['productos', 'producto_por_id', 'items_linea', 'cotizaciones'], 'associations': ['asociaciones', 'tipos_asociaciones'], 'pipelines': ['pipelines', 'etapas_pipeline', 'detalles_pipeline'], 'owners': ['owners', 'propietario'], 'activities': ['emails', 'llamadas', 'reuniones', 'notas', 'historial_actividades'], 'crm': ['resumen_general_crm', 'dashboards', 'grupos_propiedades'], 'create': ['crear_', 'crear_contacto', 'crear_compania', 'crear_deal', 'crear_ticket'], 'update': ['actualizar_', 'asociar_', 'actualizar_propietario', 'actualizar_etapa']}
    if category not in category_mapping:
        return all_tools
    keywords = category_mapping[category]
    filtered_tools = []
    for tool in all_tools:
        if any((keyword in tool.name.lower() for keyword in keywords)):
            filtered_tools.append(tool)
    return filtered_tools

def get_crm_management_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas específicas para gestión de CRM.
    """
    categories = ['contacts', 'companies', 'deals', 'tickets', 'products']
    all_tools = []
    for category in categories:
        all_tools.extend(get_hubspot_tools_by_category(user_email, category))
    return all_tools

def get_activity_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas para gestión de actividades (emails, llamadas, reuniones, notas).
    """
    return get_hubspot_tools_by_category(user_email, 'activities')

def get_creation_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas para creación de registros en HubSpot.
    """
    return get_hubspot_tools_by_category(user_email, 'create')

def get_update_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas para actualización de registros en HubSpot.
    """
    return get_hubspot_tools_by_category(user_email, 'update')

def get_all_hubspot_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene todas las herramientas de HubSpot.
    """
    return get_hubspot_bigtools(user_email)
