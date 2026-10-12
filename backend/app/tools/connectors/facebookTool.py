"""
Facebook Tool para LangGraph / LangChain
Migración a Bóveda Segura y Resiliencia V2.
- Erradicación de variables de entorno sueltas (Fuga de configuración solucionada).
- Implementación de timeouts nativos en requests (15s).
- Uso estricto de ToolException y handle_tool_error=True.
- Salidas estandarizadas a JSON Strings.
"""
import json
import logging
import requests
from typing import Optional
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field
import app.integrations.providers.facebook as FaceBookConnection
from app.core.db_utils import canonicalize_email
logger = logging.getLogger('tools.facebook')
_REQUEST_TIMEOUT = 15

class GetAccountDetailsInput(BaseModel):
    query: Optional[str] = Field(default='', alias='consulta', description='Parámetro opcional, dejar vacío.')

class FacebookToolProvider:

    def __init__(self, user_email: str | None=None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or '')
        self.user_email = canonical
        self.baseUrl = 'https://graph.facebook.com/v20.0'
        self.fields = 'id,name,email,picture'

    def get_account_details(self, query: str='') -> str:
        """Obtiene los detalles de la cuenta llamando a Facebook Graph API."""
        try:
            API_token = FaceBookConnection.getCredentials(self.user_email)
            if not API_token:
                raise ToolException(f"No se encontraron credenciales de Facebook para '{self.user_email}'.")
            headers = {'Authorization': f'Bearer {API_token}'}
            params = {'fields': self.fields}
            endpoint = f'{self.baseUrl}/me'
            response = requests.get(endpoint, headers=headers, params=params, timeout=_REQUEST_TIMEOUT)
            if response.status_code != 200:
                logger.error(f'[FacebookTool] Error API {response.status_code}: {response.text}')
                raise ToolException(f'Facebook API respondió con error {response.status_code}: {response.text}')
            return json.dumps(response.json(), ensure_ascii=False)
        except requests.Timeout:
            logger.error(f'[FacebookTool] Timeout ({_REQUEST_TIMEOUT}s) conectando a Facebook para {self.user_email}')
            raise ToolException('Tiempo de espera agotado al conectar con los servidores de Facebook.')
        except requests.RequestException as e:
            logger.error(f'[FacebookTool] Error de red: {e}')
            raise ToolException(f'Error de red al contactar Facebook Graph API: {str(e)}')
        except ToolException:
            raise
        except Exception as e:
            logger.error(f'[FacebookTool] Error interno inesperado: {e}')
            raise ToolException(f'Error interno al procesar la cuenta de Facebook: {str(e)}')

    def get_tool_account_details(self) -> StructuredTool:
        return StructuredTool.from_function(func=self.get_account_details, name='get_account_details', description='Accede a todos los detalles de tu cuenta de usuario en Facebook. Obtiene la información completa del perfil.', args_schema=GetAccountDetailsInput, handle_tool_error=True)

