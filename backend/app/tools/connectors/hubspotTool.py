"""
HubSpot Tool para LangGraph / LangChain
Migración a Bóveda Segura, Resiliencia y Anti-Hallucination.
- Inyección masiva de esquemas Pydantic para prevenir alucinaciones del LLM.
- Delega la lectura y refresco seguro a app.services.hubspot.
- Implementa timeouts (15s) en todas las llamadas de red.
- Erradica los silent failures usando ToolException en lugar de dicts.
- Estandariza respuestas exitosas a json.dumps.
"""
import json
import logging
import requests
from typing import Callable, Any, Dict, List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, ToolException
from config import Config
import app.integrations.providers.hubspot as HubspotConnection
from app.core.db_utils import canonicalize_email
load_dotenv()
logger = logging.getLogger('tools.hubspot')
_REQUEST_TIMEOUT = 15

class EmptyOrQueryInput(BaseModel):
    query: str = Field(default='', description='Parámetro opcional de búsqueda. Dejar vacío por defecto.')

class LimitInput(BaseModel):
    limit: int = Field(default=50, description='Cantidad máxima de resultados a retornar. Rango seguro: 10 a 100.')

class ContactIdInput(BaseModel):
    contact_id: str = Field(..., description='ID numérico único del contacto en HubSpot.')

class CompanyIdInput(BaseModel):
    company_id: str = Field(..., description='ID numérico único de la compañía en HubSpot.')

class DealIdInput(BaseModel):
    deal_id: str = Field(..., description='ID numérico único del negocio (Deal) en HubSpot.')

class TicketIdInput(BaseModel):
    ticket_id: str = Field(..., description='ID numérico único del ticket de soporte en HubSpot.')

class ProductIdInput(BaseModel):
    product_id: str = Field(..., description='ID numérico único del producto en HubSpot.')

class GetAssociationsInput(BaseModel):
    from_type: str = Field(..., description="Tipo de objeto origen (ej. 'contacts', 'companies', 'deals').")
    from_id: str = Field(..., description='ID del objeto origen.')
    to_type: str = Field(..., description="Tipo de objeto destino (ej. 'deals', 'tickets').")

class GetPipelinesInput(BaseModel):
    object_type: str = Field(default='deals', description="Tipo de objeto del pipeline. Valores comunes: 'deals' o 'tickets'.")

class GetPipelineStagesInput(BaseModel):
    object_type: str = Field(..., description="Tipo de objeto (ej. 'deals' o 'tickets').")
    pipeline_id: str = Field(..., description='ID del pipeline a consultar.')

class TimelineInput(BaseModel):
    object_type: str = Field(..., description="Tipo de objeto (ej. 'contacts', 'companies').")
    object_id: str = Field(..., description='ID único del objeto para extraer su línea de tiempo.')

class PropertyGroupsInput(BaseModel):
    object_type: str = Field(..., description="Tipo de objeto (ej. 'contacts', 'deals').")

class CreateContactInput(BaseModel):
    email: str = Field(..., alias='correo', description='Correo electrónico del contacto.')
    firstname: str = Field(..., alias='nombre', description='Nombre del contacto.')
    lastname: str = Field(..., alias='apellido', description='Apellido del contacto.')
    phone: str = Field(default='', alias='telefono', description='Teléfono del contacto.')
    company: str = Field(default='', alias='empresa', description='Nombre de la empresa.')
    website: str = Field(default='', alias='sitio_web', description='Sitio web de la empresa.')
    lead_status: str = Field(default='NEW', alias='estado_lead', description='Estado del lead (ej. NEW, OPEN, IN_PROGRESS).')

class CreateCompanyInput(BaseModel):
    name: str = Field(..., alias='nombre', description='Nombre oficial de la compañía.')
    domain: str = Field(..., alias='dominio', description='Dominio web de la compañía (ej. empresa.com).')
    phone: str = Field(default='', alias='telefono', description='Teléfono corporativo.')
    city: str = Field(default='', alias='ciudad', description='Ciudad.')
    country: str = Field(default='', alias='pais', description='País.')
    industry: str = Field(default='', alias='industria', description='Industria de la compañía.')

class CreateDealInput(BaseModel):
    dealname: str = Field(..., alias='nombre', description='Nombre descriptivo del negocio/deal.')
    amount: float = Field(..., alias='monto', description='Monto o valor económico del negocio.')
    dealstage: str = Field(..., alias='etapa', description='ID de la etapa del pipeline donde se creará.')
    pipeline: str = Field(default='default', alias='pipeline', description='ID del pipeline.')
    close_date: str = Field(default='', alias='fecha_cierre', description='Fecha de cierre esperada en formato Unix timestamp (milisegundos) o ISO-8601.')
    associated_contact_ids: Optional[List[str]] = Field(default=None, alias='contactos_asociados', description='Lista de IDs de contactos a asociar.')

class CreateTicketInput(BaseModel):
    subject: str = Field(..., alias='asunto', description='Asunto o título del ticket de soporte.')
    content: str = Field(..., alias='contenido', description='Descripción detallada del problema.')
    pipeline: str = Field(default='default', alias='pipeline', description='ID del pipeline de soporte.')
    ticket_status: str = Field(default='OPEN', alias='estado_ticket', description='Etapa del ticket (ej. OPEN, IN_PROGRESS).')
    associated_contact_id: Optional[str] = Field(default=None, alias='contacto_asociado', description='ID del contacto asociado.')

class CreateProductInput(BaseModel):
    name: str = Field(..., alias='nombre', description='Nombre del producto.')
    price: float = Field(..., alias='precio', description='Precio base del producto.')
    sku: str = Field(default='', alias='codigo', description='SKU o código único de inventario.')
    description: str = Field(default='', alias='descripcion', description='Descripción del producto.')
    currency: str = Field(default='USD', alias='moneda', description='Moneda (ej. USD, EUR, COP, ARS).')

class CreateNoteInput(BaseModel):
    note_body: str = Field(..., alias='cuerpo', description='Cuerpo del texto de la nota.')
    associated_object_type: Optional[str] = Field(default=None, alias='tipo_objeto_asociado', description="Tipo de objeto a asociar (ej. 'contacts').")
    associated_object_id: Optional[str] = Field(default=None, alias='id_objeto_asociado', description='ID del objeto a asociar.')

class UpdateContactInput(BaseModel):
    contact_id: str = Field(..., alias='id_contacto', description='ID del contacto a modificar.')
    properties: Dict[str, Any] = Field(..., alias='propiedades', description='Diccionario clave-valor con las propiedades a actualizar.')

class UpdateCompanyInput(BaseModel):
    company_id: str = Field(..., alias='id_compania', description='ID de la compañía a modificar.')
    properties: Dict[str, Any] = Field(..., alias='propiedades', description='Diccionario clave-valor con las propiedades a actualizar.')

class UpdateDealInput(BaseModel):
    deal_id: str = Field(..., alias='id_deal', description='ID del deal a modificar.')
    properties: Dict[str, Any] = Field(..., alias='propiedades', description='Diccionario clave-valor con las propiedades a actualizar.')

class UpdateTicketInput(BaseModel):
    ticket_id: str = Field(..., alias='id_ticket', description='ID del ticket a modificar.')
    properties: Dict[str, Any] = Field(..., alias='propiedades', description='Diccionario clave-valor con las propiedades a actualizar.')

class UpdateProductInput(BaseModel):
    product_id: str = Field(..., alias='id_producto', description='ID del producto a modificar.')
    properties: Dict[str, Any] = Field(..., alias='propiedades', description='Diccionario clave-valor con las propiedades a actualizar.')

class UpdateNoteInput(BaseModel):
    note_id: str = Field(..., alias='id_nota', description='ID de la nota a actualizar.')
    new_body: str = Field(..., alias='nuevo_cuerpo', description='Nuevo texto de la nota.')

class AssociateObjectsInput(BaseModel):
    from_object: str = Field(..., alias='objeto_origen', description="Tipo de objeto origen (ej. 'contacts').")
    from_id: str = Field(..., alias='id_origen', description='ID origen.')
    to_object: str = Field(..., alias='objeto_destino', description="Tipo de objeto destino (ej. 'deals').")
    to_id: str = Field(..., alias='id_destino', description='ID destino.')
    association_type_id: int = Field(default=1, alias='tipo_asociacion_id', description='ID del tipo de asociación de HubSpot.')

class CreateTaskInput(BaseModel):
    title: str = Field(..., alias='titulo', description='Título de la tarea.')
    due_date: str = Field(..., alias='fecha_entrega', description='Fecha de entrega en formato Unix Timestamp en milisegundos.')
    owner_id: str = Field(default='', alias='id_dueno', description='ID del usuario asignado (owner).')
    notes: str = Field(default='', alias='notas', description='Notas o instrucciones adicionales.')
    associated_contact_id: Optional[str] = Field(default=None, alias='contacto_asociado', description='ID del contacto a asociar.')

class CreateCallInput(BaseModel):
    call_title: str = Field(..., alias='titulo_llamada', description='Asunto o título de la llamada.')
    call_status: str = Field(default='COMPLETED', alias='estado_llamada', description='Estado de la llamada (ej. COMPLETED, BUSY, MISSED).')
    duration_seconds: int = Field(default=60, alias='duracion_segundos', description='Duración en segundos.')
    notes: str = Field(default='', alias='notas', description='Minuta de la llamada.')
    associated_contact_id: Optional[str] = Field(default=None, alias='contacto_asociado', description='ID del contacto asociado.')

class UpdateOwnerInput(BaseModel):
    object_type: str = Field(..., alias='tipo_objeto', description="Tipo de objeto (ej. 'contacts').")
    object_id: str = Field(..., alias='id_objeto', description='ID del objeto.')
    new_owner_id: str = Field(..., alias='nuevo_dueno_id', description='ID del nuevo dueño/usuario de HubSpot.')

class UpdatePipelineStageInput(BaseModel):
    object_type: str = Field(..., alias='tipo_objeto', description="Tipo de objeto ('deals' o 'tickets').")
    object_id: str = Field(..., alias='id_objeto', description='ID del objeto.')
    new_stage: str = Field(..., alias='nueva_etapa', description='ID de la nueva etapa del pipeline.')

class HubspotToolProvider:

    def __init__(self, user_email: str | None=None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or '')
        self.user_email = canonical
        self.baseUrl = 'https://api.hubapi.com'
        self.client_id = Config.HUBSPOT_CLIENT_ID
        self.Secret = Config.HUBSPOT_CLIENT_SECRET
        self.url = Config.FRONTEND_REDIRECT_URL

    def get_valid_token(self) -> str:
        """
        Obtiene un token válido apoyándose en el servicio seguro de HubSpot.
        Si el token expiró (401), delega el refresco al método refreshToken_Hubspot.
        """
        creds = HubspotConnection.Get_Credenciales_Hubspot(self.user_email)
        if not creds or not creds.get('token'):
            raise ToolException('HubSpot no está conectado. Por favor, conecta tu cuenta en la configuración.')
        token = creds['token']
        try:
            test = requests.get(f'{self.baseUrl}/account-info/v3/details', headers={'Authorization': f'Bearer {token}'}, timeout=_REQUEST_TIMEOUT)
            if test.status_code == 401:
                logger.info(f"[HubspotTool] Token expirado para '{self.user_email}', solicitando refresco seguro...")
                new_creds = HubspotConnection.refreshToken_Hubspot(self.user_email)
                if new_creds and new_creds.get('token'):
                    logger.info(f"[HubspotTool] Token refrescado y encriptado en bóveda para '{self.user_email}'.")
                    return new_creds['token']
                else:
                    raise ToolException('No se pudo refrescar el token de HubSpot. Requiere re-autenticación.')
        except requests.exceptions.RequestException as e:
            logger.warning(f'[HubspotTool] Error de red al probar token: {e}')
        return token

    def _make_tool(self, name: str, func: Callable, description: str, args_schema: Any=None) -> StructuredTool:
        """Helper Enterprise para instanciar herramientas de forma segura con validación Pydantic estricta."""
        kwargs = {'name': name, 'func': func, 'description': description, 'handle_tool_error': True}
        if args_schema:
            kwargs['args_schema'] = args_schema
        return StructuredTool.from_function(**kwargs)

    def get_account_information(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/account-info/v3/details', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            res = {'portalId': data.get('portalId'), 'accountType': data.get('accountType'), 'timezone': data.get('timeZone'), 'currency': data.get('companyCurrency'), 'dataHostingLocation': data.get('dataHostingLocation'), 'uiDomain': data.get('uiDomain'), 'utcOffset': data.get('utcOffset')}
            return json.dumps(res, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f'[HubspotTool] Error en get_account_information: {e}')
            raise ToolException(f'Error interno: {str(e)}')

    def get_portal_users(self, limit: int=50) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/settings/v3/users?limit={limit}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            users = [{'id': u.get('id'), 'email': u.get('email') or (u.get('user') or {}).get('email'), 'firstName': u.get('firstName') or (u.get('user') or {}).get('firstName'), 'lastName': u.get('lastName') or (u.get('user') or {}).get('lastName'), 'active': u.get('active'), 'roleId': u.get('roleId'), 'superAdmin': u.get('superAdmin', False)} for u in data.get('results', [])]
            return json.dumps({'total_users': len(users), 'users': users}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_roles(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/settings/v3/users/roles', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            roles = [{'id': r.get('id'), 'name': r.get('name'), 'description': r.get('description'), 'permission_sets': [p.get('name') for p in r.get('permissionSets', [])] if r.get('permissionSets') else []} for r in data.get('results', [])]
            return json.dumps({'total_roles': len(roles), 'roles': roles}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_teams(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/settings/v3/users/teams', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            teams = [{'id': t.get('id'), 'name': t.get('name'), 'active': t.get('active', True), 'manager_email': (t.get('manager') or {}).get('email') if t.get('manager') else None, 'member_count': len(t.get('members', [])) if t.get('members') else 0} for t in data.get('results', [])]
            return json.dumps({'total_teams': len(teams), 'teams': teams}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_contacts_hubspot(self, limit: int=50) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/contacts?limit={limit}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            contacts = [{'id': c.get('id'), 'firstname': c.get('properties', {}).get('firstname'), 'lastname': c.get('properties', {}).get('lastname'), 'email': c.get('properties', {}).get('email'), 'phone': c.get('properties', {}).get('phone'), 'company': c.get('properties', {}).get('company')} for c in data.get('results', [])]
            return json.dumps({'total_contacts': len(contacts), 'contacts': contacts}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_one_contact_hubspot(self, contact_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/contacts/{contact_id}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            props = data.get('properties', {})
            res = {'id': data.get('id'), 'firstname': props.get('firstname'), 'lastname': props.get('lastname'), 'email': props.get('email'), 'phone': props.get('phone')}
            return json.dumps(res, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_contact_properties(self, limit: int=20) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/properties/contacts', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            properties = [{'name': p.get('name'), 'label': p.get('label'), 'type': p.get('type')} for p in data.get('results', [])[:limit]]
            return json.dumps({'total_properties': len(properties), 'properties': properties}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_companies(self, limit: int=50) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/companies?limit={limit}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            companies = [{'id': c.get('id'), 'name': c.get('properties', {}).get('name'), 'website': c.get('properties', {}).get('website'), 'industry': c.get('properties', {}).get('industry')} for c in data.get('results', [])]
            return json.dumps({'total_companies': len(companies), 'companies': companies}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_one_company(self, company_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/companies/{company_id}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            props = data.get('properties', {})
            res = {'id': data.get('id'), 'name': props.get('name'), 'website': props.get('website')}
            return json.dumps(res, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_company_properties(self, limit: int=25) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/properties/companies', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            properties = [{'name': p.get('name'), 'label': p.get('label')} for p in data.get('results', [])[:limit]]
            return json.dumps({'total_properties': len(properties), 'properties': properties}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_deals(self, limit: int=50) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/deals?limit={limit}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            deals = [{'id': d.get('id'), 'dealname': d.get('properties', {}).get('dealname'), 'amount': d.get('properties', {}).get('amount'), 'dealstage': d.get('properties', {}).get('dealstage')} for d in data.get('results', [])]
            return json.dumps({'total_deals': len(deals), 'deals': deals}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_one_deal(self, deal_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/deals/{deal_id}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            props = data.get('properties', {})
            res = {'id': data.get('id'), 'dealname': props.get('dealname'), 'amount': props.get('amount')}
            return json.dumps(res, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_deal_properties(self, limit: int=25) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/properties/deals', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            properties = [{'name': p.get('name'), 'label': p.get('label')} for p in data.get('results', [])[:limit]]
            return json.dumps({'total_properties': len(properties), 'properties': properties}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_tickets(self, limit: int=50) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/tickets?limit={limit}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            tickets = [{'id': t.get('id'), 'subject': t.get('properties', {}).get('subject'), 'status': t.get('properties', {}).get('hs_pipeline_stage')} for t in data.get('results', [])]
            return json.dumps({'total_tickets': len(tickets), 'tickets': tickets}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_one_ticket(self, ticket_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/tickets/{ticket_id}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            props = data.get('properties', {})
            res = {'id': data.get('id'), 'subject': props.get('subject'), 'status': props.get('hs_pipeline_stage')}
            return json.dumps(res, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_ticket_properties(self, limit: int=25) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/properties/tickets', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            properties = [{'name': p.get('name'), 'label': p.get('label')} for p in data.get('results', [])[:limit]]
            return json.dumps({'total_properties': len(properties), 'properties': properties}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_products(self, limit: int=50) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/products?limit={limit}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            products = [{'id': p.get('id'), 'name': p.get('properties', {}).get('name'), 'price': p.get('properties', {}).get('price'), 'sku': p.get('properties', {}).get('hs_sku')} for p in data.get('results', [])]
            return json.dumps({'total_products': len(products), 'products': products}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_one_product(self, product_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/products/{product_id}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            props = data.get('properties', {})
            res = {'id': data.get('id'), 'name': props.get('name'), 'price': props.get('price'), 'sku': props.get('hs_sku')}
            return json.dumps(res, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_product_properties(self, limit: int=25) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/properties/products', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            properties = [{'name': p.get('name'), 'label': p.get('label')} for p in data.get('results', [])[:limit]]
            return json.dumps({'total_properties': len(properties), 'properties': properties}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_line_items(self, limit: int=50) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/line_items?limit={limit}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            items = [{'id': i.get('id'), 'name': i.get('properties', {}).get('name')} for i in data.get('results', [])]
            return json.dumps({'total_line_items': len(items), 'line_items': items}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_quotes(self, limit: int=50) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/quotes?limit={limit}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            quotes = [{'id': q.get('id'), 'title': q.get('properties', {}).get('hs_title')} for q in data.get('results', [])]
            return json.dumps({'total_quotes': len(quotes), 'quotes': quotes}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_associations(self, from_type: str, from_id: str, to_type: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            url = f'{self.baseUrl}/crm/v4/objects/{from_type}/{from_id}/associations/{to_type}'
            response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            results = [{'to_id': r.get('toObjectId'), 'type': r.get('associationType')} for r in data.get('results', [])]
            res = {'from_type': from_type, 'to_type': to_type, 'associations': results}
            return json.dumps(res, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_association_types(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v4/associations/', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            return json.dumps({'associations': data.get('results', [])}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_pipelines(self, object_type: str='deals') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/pipelines/{object_type}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            pipelines = [{'id': p.get('id'), 'label': p.get('label')} for p in data.get('results', [])]
            return json.dumps({'pipelines': pipelines}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_pipeline_stages(self, object_type: str, pipeline_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            url = f'{self.baseUrl}/crm/v3/pipelines/{object_type}/{pipeline_id}'
            response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            stages = [{'id': s.get('id'), 'label': s.get('label')} for s in data.get('stages', [])]
            return json.dumps({'stages': stages}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_owners(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/owners/', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            owners = [{'id': o.get('id'), 'email': o.get('email'), 'name': f"{o.get('firstName')} {o.get('lastName')}"} for o in data.get('results', [])]
            return json.dumps({'owners': owners}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_crm_stats(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            objects = ['contacts', 'companies', 'deals', 'tickets', 'products']
            stats = []
            for obj in objects:
                response = requests.get(f'{self.baseUrl}/crm/v3/objects/{obj}/meta', headers=headers, timeout=_REQUEST_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    stats.append({'object_type': obj, 'total_properties': len(data.get('properties', []))})
            return json.dumps({'crm_stats': stats}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_emails(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/emails', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            return json.dumps({'emails': [{'id': e.get('id')} for e in data.get('results', [])]}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_calls(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/calls', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            return json.dumps({'calls': [{'id': c.get('id')} for c in data.get('results', [])]}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_meetings(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/meetings', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            return json.dumps({'meetings': [{'id': m.get('id')} for m in data.get('results', [])]}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_notes(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/objects/notes', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            return json.dumps({'notes': [{'id': n.get('id')} for n in data.get('results', [])]}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_engagements_timeline(self, object_type: str, object_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            activities = ['emails', 'calls', 'meetings', 'notes']
            timeline = []
            for act in activities:
                response = requests.get(f'{self.baseUrl}/crm/v4/objects/{object_type}/{object_id}/associations/{act}', headers=headers, timeout=_REQUEST_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    for assoc in data.get('results', []):
                        timeline.append({'activity_type': act, 'activity_id': assoc.get('toObjectId')})
            return json.dumps({'timeline': timeline}, ensure_ascii=False)
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_property_groups(self, object_type: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/properties/{object_type}/groups', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            return json.dumps({'property_groups': [{'name': g.get('name')} for g in data.get('results', [])]}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_dashboards(self, query: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/analytics/v2/reports/dashboards', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            return json.dumps({'dashboards': [{'id': d.get('id'), 'name': d.get('name')} for d in data.get('results', [])]}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_pipeline_details(self, object_type: str, pipeline_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{self.baseUrl}/crm/v3/pipelines/{object_type}/{pipeline_id}', headers=headers, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
            data = response.json()
            stages = [{'id': s.get('id'), 'label': s.get('label')} for s in data.get('stages', [])]
            return json.dumps({'pipeline_id': pipeline_id, 'stages': stages}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def create_contact(self, email: str, firstname: str, lastname: str, phone: str='', company: str='', website: str='', lead_status: str='NEW') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'properties': {'email': email, 'firstname': firstname, 'lastname': lastname, 'phone': phone, 'company': company, 'website': website, 'hs_lead_status': lead_status}}
            response = requests.post(f'{self.baseUrl}/crm/v3/objects/contacts', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def create_company(self, name: str, domain: str, phone: str='', city: str='', country: str='', industry: str='') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'properties': {'name': name, 'domain': domain, 'phone': phone, 'city': city, 'country': country, 'industry': industry}}
            response = requests.post(f'{self.baseUrl}/crm/v3/objects/companies', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def create_deal(self, dealname: str, amount: float, dealstage: str, pipeline: str='default', close_date: str='', associated_contact_ids: list=None) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'properties': {'dealname': dealname, 'amount': amount, 'dealstage': dealstage, 'pipeline': pipeline, 'closedate': close_date}}
            if associated_contact_ids:
                data['associations'] = [{'to': {'id': c_id}, 'types': [{'associationCategory': 'HUBSPOT_DEFINED', 'associationTypeId': 3}]} for c_id in associated_contact_ids]
            response = requests.post(f'{self.baseUrl}/crm/v3/objects/deals', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def create_ticket(self, subject: str, content: str, pipeline: str='default', ticket_status: str='OPEN', associated_contact_id: str=None) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'properties': {'subject': subject, 'content': content, 'hs_pipeline': pipeline, 'hs_pipeline_stage': ticket_status}}
            if associated_contact_id:
                data['associations'] = [{'to': {'id': associated_contact_id}, 'types': [{'associationCategory': 'HUBSPOT_DEFINED', 'associationTypeId': 16}]}]
            response = requests.post(f'{self.baseUrl}/crm/v3/objects/tickets', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def create_product(self, name: str, price: float, sku: str='', description: str='', currency: str='USD') -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'properties': {'name': name, 'price': price, 'hs_sku': sku, 'description': description, 'currency': currency}}
            response = requests.post(f'{self.baseUrl}/crm/v3/objects/products', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def create_note(self, note_body: str, associated_object_type: str=None, associated_object_id: str=None) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'properties': {'hs_note_body': note_body}}
            if associated_object_type and associated_object_id:
                data['associations'] = [{'to': {'id': associated_object_id}, 'types': [{'associationCategory': 'HUBSPOT_DEFINED', 'associationTypeId': 12}]}]
            response = requests.post(f'{self.baseUrl}/crm/v3/objects/notes', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def update_contact(self, contact_id: str, properties: dict) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.patch(f'{self.baseUrl}/crm/v3/objects/contacts/{contact_id}', headers=headers, data=json.dumps({'properties': properties}), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def update_company(self, company_id: str, properties: dict) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.patch(f'{self.baseUrl}/crm/v3/objects/companies/{company_id}', headers=headers, data=json.dumps({'properties': properties}), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def update_deal(self, deal_id: str, properties: dict) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.patch(f'{self.baseUrl}/crm/v3/objects/deals/{deal_id}', headers=headers, data=json.dumps({'properties': properties}), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def update_ticket(self, ticket_id: str, properties: dict) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.patch(f'{self.baseUrl}/crm/v3/objects/tickets/{ticket_id}', headers=headers, data=json.dumps({'properties': properties}), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def update_product(self, product_id: str, properties: dict) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.patch(f'{self.baseUrl}/crm/v3/objects/products/{product_id}', headers=headers, data=json.dumps({'properties': properties}), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def update_note(self, note_id: str, new_body: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.patch(f'{self.baseUrl}/crm/v3/objects/notes/{note_id}', headers=headers, data=json.dumps({'properties': {'hs_note_body': new_body}}), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def associate_objects(self, from_object: str, from_id: str, to_object: str, to_id: str, association_type_id: int=1) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'inputs': [{'from': {'id': from_id}, 'to': {'id': to_id}, 'types': [{'associationCategory': 'HUBSPOT_DEFINED', 'associationTypeId': association_type_id}]}]}
            response = requests.post(f'{self.baseUrl}/crm/v4/associations/{from_object}/{to_object}/batch/create', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def create_task(self, title: str, due_date: str, owner_id: str='', notes: str='', associated_contact_id: str=None) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'properties': {'hs_task_subject': title, 'hs_task_body': notes, 'hs_timestamp': due_date}}
            if owner_id:
                data['properties']['hubspot_owner_id'] = owner_id
            if associated_contact_id:
                data['associations'] = [{'to': {'id': associated_contact_id}, 'types': [{'associationCategory': 'HUBSPOT_DEFINED', 'associationTypeId': 13}]}]
            response = requests.post(f'{self.baseUrl}/crm/v3/objects/tasks', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def create_call(self, call_title: str, call_status: str='COMPLETED', duration_seconds: int=60, notes: str='', associated_contact_id: str=None) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            data = {'properties': {'hs_call_title': call_title, 'hs_call_status': call_status, 'hs_call_duration': duration_seconds, 'hs_call_body': notes}}
            if associated_contact_id:
                data['associations'] = [{'to': {'id': associated_contact_id}, 'types': [{'associationCategory': 'HUBSPOT_DEFINED', 'associationTypeId': 25}]}]
            response = requests.post(f'{self.baseUrl}/crm/v3/objects/calls', headers=headers, data=json.dumps(data), timeout=_REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def update_owner(self, object_type: str, object_id: str, new_owner_id: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.patch(f'{self.baseUrl}/crm/v3/objects/{object_type}/{object_id}', headers=headers, data=json.dumps({'properties': {'hubspot_owner_id': new_owner_id}}), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def update_pipeline_stage(self, object_type: str, object_id: str, new_stage: str) -> str:
        try:
            token = self.get_valid_token()
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            props = {'dealstage': new_stage} if object_type == 'deals' else {'hs_pipeline_stage': new_stage}
            response = requests.patch(f'{self.baseUrl}/crm/v3/objects/{object_type}/{object_id}', headers=headers, data=json.dumps({'properties': props}), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f'HubSpot API Error ({response.status_code}): {response.text}')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno: {str(e)}')

    def get_tool_account_information(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_account_information', func=self.get_account_information, description='Devuelve información general de la cuenta HubSpot autenticada.', args_schema=EmptyOrQueryInput)

    def get_tool_portal_users(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_portal_users', func=self.get_portal_users, description='Lista los usuarios del portal HubSpot. Parámetros opcionales: limit.', args_schema=LimitInput)

    def get_tool_roles(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_roles', func=self.get_roles, description='Lista los roles disponibles en el portal de HubSpot.', args_schema=EmptyOrQueryInput)

    def get_tool_teams(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_teams', func=self.get_teams, description='Lista los equipos (teams) del portal de HubSpot.', args_schema=EmptyOrQueryInput)

    def get_tool_listar_contactos(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_contacts', func=self.get_contacts_hubspot, description='Lista todos los contactos registrados en HubSpot. Parámetros opcionales: limit.', args_schema=LimitInput)

    def get_tool_buscar_contacto_por_id(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_contact_by_id', func=self.get_one_contact_hubspot, description='Obtiene los detalles de un contacto de HubSpot usando su ID.', args_schema=ContactIdInput)

    def get_tool_listar_propiedades_contactos(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_contact_properties', func=self.get_contact_properties, description='Lista todas las propiedades configuradas para los contactos.', args_schema=LimitInput)

    def get_tool_listar_companias(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_companies', func=self.get_companies, description='Lista todas las compañías registradas en HubSpot.', args_schema=LimitInput)

    def get_tool_buscar_compania_por_id(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_company_by_id', func=self.get_one_company, description='Obtiene los detalles de una compañía específica usando su ID.', args_schema=CompanyIdInput)

    def get_tool_listar_propiedades_companias(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_company_properties', func=self.get_company_properties, description='Lista un subconjunto de las propiedades configuradas para las compañías.', args_schema=LimitInput)

    def get_tool_listar_deals(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_deals', func=self.get_deals, description='Lista todos los negocios (deals) registrados en HubSpot.', args_schema=LimitInput)

    def get_tool_buscar_deal_por_id(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_deal_by_id', func=self.get_one_deal, description='Obtiene los detalles de un negocio específico usando su ID.', args_schema=DealIdInput)

    def get_tool_listar_propiedades_deals(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_deal_properties', func=self.get_deal_properties, description='Lista un subconjunto de las propiedades configuradas para los negocios.', args_schema=LimitInput)

    def get_tool_listar_tickets(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_tickets', func=self.get_tickets, description='Lista todos los tickets registrados en HubSpot Service Hub.', args_schema=LimitInput)

    def get_tool_buscar_ticket_por_id(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_ticket_by_id', func=self.get_one_ticket, description='Obtiene los detalles de un ticket específico usando su ID.', args_schema=TicketIdInput)

    def get_tool_listar_propiedades_tickets(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_ticket_properties', func=self.get_ticket_properties, description='Lista un subconjunto de las propiedades configuradas para los tickets.', args_schema=LimitInput)

    def get_tool_listar_productos(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_products', func=self.get_products, description='Lista los productos registrados en HubSpot.', args_schema=LimitInput)

    def get_tool_buscar_producto_por_id(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_product_by_id', func=self.get_one_product, description='Obtiene la información detallada de un producto usando su ID.', args_schema=ProductIdInput)

    def get_tool_listar_items_linea(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_line_items', func=self.get_line_items, description='Lista los ítems de línea registrados en HubSpot.', args_schema=LimitInput)

    def get_tool_listar_cotizaciones(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_quotes', func=self.get_quotes, description='Lista las cotizaciones (quotes) creadas en HubSpot.', args_schema=LimitInput)

    def get_tool_buscar_asociaciones(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_associations', func=self.get_associations, description='Devuelve los objetos relacionados en HubSpot. Requiere from_type, from_id, to_type.', args_schema=GetAssociationsInput)

    def get_tool_listar_tipos_asociaciones(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_association_types', func=self.get_association_types, description='Lista todos los tipos de asociaciones configuradas entre objetos del CRM.', args_schema=EmptyOrQueryInput)

    def get_tool_listar_pipelines(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_pipelines', func=self.get_pipelines, description='Lista los pipelines configurados para un tipo de objeto del CRM.', args_schema=GetPipelinesInput)

    def get_tool_listar_etapas_pipeline(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_pipeline_stages', func=self.get_pipeline_stages, description='Muestra las etapas de un pipeline específico dentro del CRM de HubSpot.', args_schema=GetPipelineStagesInput)

    def get_tool_listar_owners(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_owners', func=self.get_owners, description='Lista todos los dueños activos del CRM en HubSpot.', args_schema=EmptyOrQueryInput)

    def get_tool_resumen_crm(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_crm_summary', func=self.get_crm_stats, description='Devuelve un resumen general del CRM.', args_schema=EmptyOrQueryInput)

    def get_tool_listar_emails(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_emails', func=self.get_emails, description='Lista todos los correos electrónicos registrados en el CRM.', args_schema=EmptyOrQueryInput)

    def get_tool_listar_llamadas(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_calls', func=self.get_calls, description='Lista todas las llamadas registradas en el CRM.', args_schema=EmptyOrQueryInput)

    def get_tool_listar_reuniones(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_meetings', func=self.get_meetings, description='Lista todas las reuniones registradas en HubSpot.', args_schema=EmptyOrQueryInput)

    def get_tool_listar_notas(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_notes', func=self.get_notes, description='Lista todas las notas registradas en el CRM de HubSpot.', args_schema=EmptyOrQueryInput)

    def get_tool_listar_asociaciones(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_associations', func=self.get_association_types, description='Lista todos los tipos de asociaciones de objetos relacionados al CRM.', args_schema=EmptyOrQueryInput)

    def get_tool_historial_actividades(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_activity_history', func=self.get_engagements_timeline, description='Muestra el historial completo de actividades relacionadas con un registro.', args_schema=TimelineInput)

    def get_tool_listar_grupos_propiedades(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_property_groups', func=self.get_property_groups, description='Devuelve los grupos de propiedades disponibles para un objeto.', args_schema=PropertyGroupsInput)

    def get_tool_listar_dashboards(self) -> StructuredTool:
        return self._make_tool(name='list_hubspot_dashboards', func=self.get_dashboards, description='Lista todos los dashboards e informes configurados.', args_schema=EmptyOrQueryInput)

    def get_tool_detalles_pipeline(self) -> StructuredTool:
        return self._make_tool(name='get_hubspot_pipeline_details', func=self.get_pipeline_details, description='Devuelve información completa de un pipeline específico.', args_schema=GetPipelineStagesInput)

    def get_tool_crear_contacto(self) -> StructuredTool:
        return self._make_tool(name='create_hubspot_contact', func=self.create_contact, description='Crea un nuevo contacto en HubSpot.', args_schema=CreateContactInput)

    def get_tool_crear_compania(self) -> StructuredTool:
        return self._make_tool(name='create_hubspot_company', func=self.create_company, description='Crea una nueva compañía en HubSpot.', args_schema=CreateCompanyInput)

    def get_tool_crear_deal(self) -> StructuredTool:
        return self._make_tool(name='create_hubspot_deal', func=self.create_deal, description='Crea un nuevo Deal (negocio) en HubSpot.', args_schema=CreateDealInput)

    def get_tool_crear_ticket(self) -> StructuredTool:
        return self._make_tool(name='create_hubspot_ticket', func=self.create_ticket, description='Crea un nuevo Ticket de soporte en HubSpot.', args_schema=CreateTicketInput)

    def get_tool_crear_producto(self) -> StructuredTool:
        return self._make_tool(name='create_hubspot_product', func=self.create_product, description='Crea un nuevo Producto en HubSpot.', args_schema=CreateProductInput)

    def get_tool_crear_nota(self) -> StructuredTool:
        return self._make_tool(name='create_hubspot_note', func=self.create_note, description='Crea una nueva Nota en HubSpot.', args_schema=CreateNoteInput)

    def get_tool_actualizar_contacto(self) -> StructuredTool:
        return self._make_tool(name='update_hubspot_contact', func=self.update_contact, description='Actualiza los campos de un contacto existente.', args_schema=UpdateContactInput)

    def get_tool_actualizar_compania(self) -> StructuredTool:
        return self._make_tool(name='update_hubspot_company', func=self.update_company, description='Actualiza los datos de una compañía existente.', args_schema=UpdateCompanyInput)

    def get_tool_actualizar_deal(self) -> StructuredTool:
        return self._make_tool(name='update_hubspot_deal', func=self.update_deal, description='Actualiza los datos de un Deal existente.', args_schema=UpdateDealInput)

    def get_tool_actualizar_ticket(self) -> StructuredTool:
        return self._make_tool(name='update_hubspot_ticket', func=self.update_ticket, description='Actualiza un ticket de soporte en HubSpot.', args_schema=UpdateTicketInput)

    def get_tool_actualizar_producto(self) -> StructuredTool:
        return self._make_tool(name='update_hubspot_product', func=self.update_product, description='Actualiza un producto en HubSpot.', args_schema=UpdateProductInput)

    def get_tool_actualizar_nota(self) -> StructuredTool:
        return self._make_tool(name='update_hubspot_note', func=self.update_note, description='Actualiza el cuerpo de una nota existente.', args_schema=UpdateNoteInput)

    def get_tool_asociar_objetos(self) -> StructuredTool:
        return self._make_tool(name='associate_hubspot_objects', func=self.associate_objects, description='Asocia dos objetos del CRM.', args_schema=AssociateObjectsInput)

    def get_tool_crear_tarea(self) -> StructuredTool:
        return self._make_tool(name='create_hubspot_task', func=self.create_task, description='Crea una tarea en HubSpot.', args_schema=CreateTaskInput)

    def get_tool_crear_llamada(self) -> StructuredTool:
        return self._make_tool(name='create_hubspot_call', func=self.create_call, description='Registra una llamada en HubSpot.', args_schema=CreateCallInput)

    def get_tool_actualizar_propietario(self) -> StructuredTool:
        return self._make_tool(name='update_hubspot_owner', func=self.update_owner, description='Cambia el propietario asignado de un objeto CRM.', args_schema=UpdateOwnerInput)

    def get_tool_actualizar_etapa_pipeline(self) -> StructuredTool:
        return self._make_tool(name='update_hubspot_pipeline_stage', func=self.update_pipeline_stage, description='Actualiza la etapa de pipeline de un Deal o Ticket.', args_schema=UpdatePipelineStageInput)

    def get_all_tools(self) -> List[Any]:
        """Registro para inyectar al agente de LangGraph"""
        return [self.get_tool_account_information(), self.get_tool_portal_users(), self.get_tool_roles(), self.get_tool_teams(), self.get_tool_listar_contactos(), self.get_tool_buscar_contacto_por_id(), self.get_tool_listar_propiedades_contactos(), self.get_tool_listar_companias(), self.get_tool_buscar_compania_por_id(), self.get_tool_listar_propiedades_companias(), self.get_tool_listar_deals(), self.get_tool_buscar_deal_por_id(), self.get_tool_listar_propiedades_deals(), self.get_tool_listar_tickets(), self.get_tool_buscar_ticket_por_id(), self.get_tool_listar_propiedades_tickets(), self.get_tool_listar_productos(), self.get_tool_buscar_producto_por_id(), self.get_tool_listar_items_linea(), self.get_tool_listar_cotizaciones(), self.get_tool_buscar_asociaciones(), self.get_tool_listar_tipos_asociaciones(), self.get_tool_listar_pipelines(), self.get_tool_listar_etapas_pipeline(), self.get_tool_listar_owners(), self.get_tool_resumen_crm(), self.get_tool_listar_emails(), self.get_tool_listar_llamadas(), self.get_tool_listar_reuniones(), self.get_tool_listar_notas(), self.get_tool_listar_asociaciones(), self.get_tool_historial_actividades(), self.get_tool_listar_grupos_propiedades(), self.get_tool_listar_dashboards(), self.get_tool_detalles_pipeline(), self.get_tool_crear_contacto(), self.get_tool_crear_compania(), self.get_tool_crear_deal(), self.get_tool_crear_ticket(), self.get_tool_crear_producto(), self.get_tool_crear_nota(), self.get_tool_actualizar_contacto(), self.get_tool_actualizar_compania(), self.get_tool_actualizar_deal(), self.get_tool_actualizar_ticket(), self.get_tool_actualizar_producto(), self.get_tool_actualizar_nota(), self.get_tool_asociar_objetos(), self.get_tool_crear_tarea(), self.get_tool_crear_llamada(), self.get_tool_actualizar_propietario(), self.get_tool_actualizar_etapa_pipeline()]
if __name__ == '__main__':
    logger.info('Modulo HubspotToolProvider inicializado.')

