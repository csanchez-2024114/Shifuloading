"""
Cloudinary Infrastructure Service.
High-reliability persistence layer for Shifu Multimodal Engine.
Eliminación de os.getenv y uso de Config centralizado.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union, BinaryIO
import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary.exceptions import Error as CloudinaryError
from pydantic import BaseModel, HttpUrl, Field
from tenacity import retry, stop_after_attempt, wait_exponential
from config import Config
logger = logging.getLogger('shifu.infrastructure.cloudinary')
logging.basicConfig(level=logging.INFO)

class CloudinaryResource(BaseModel):
    public_id: str
    secure_url: HttpUrl
    resource_type: str
    format: str
    bytes: int
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CloudinaryService:
    """
    Singleton Service for Cloudinary interactions.
    Implements retries, strict typing, and deep observability.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CloudinaryService, cls).__new__(cls)
            cls._instance.enabled = False
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Inicialización única del cliente."""
        if not all([Config.CLOUDINARY_CLOUD_NAME, Config.CLOUDINARY_API_KEY, Config.CLOUDINARY_API_SECRET]):
            logger.warning('⚠️ Cloudinary credentials not fully configured. Service will be disabled.')
            self.enabled = False
            return
        try:
            cloudinary.config(cloud_name=Config.CLOUDINARY_CLOUD_NAME, api_key=Config.CLOUDINARY_API_KEY, api_secret=Config.CLOUDINARY_API_SECRET, secure=True)
            self.enabled = True
            logger.info('🚀 Cloudinary Engine initialized successfully.')
        except Exception as e:
            logger.warning(f'⚠️ Cloudinary initialization failed: {str(e)}')
            self.enabled = False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    def upload_file(self, file: Union[str, BinaryIO, bytes], folder: str='shifu_v2', user_email: Optional[str]=None, tags: List[str]=None) -> CloudinaryResource:
        """
        Sube un archivo con reintento exponencial y validación Pydantic.
        """
        start_time = datetime.now(timezone.utc)
        clean_email = self._sanitize_identifier(user_email or 'anonymous')
        unique_suffix = uuid.uuid4().hex[:6]
        timestamp = int(start_time.timestamp())
        public_id = f'{folder}/{clean_email}/{timestamp}_{unique_suffix}'
        try:
            logger.info(f' Uploading resource to path: {public_id}')
            upload_result = cloudinary.uploader.upload(file, public_id=public_id, resource_type='auto', overwrite=False, tags=[clean_email] + (tags or []), context={'user_identity': user_email, 'environment': Config.ENVIRONMENT, 'v_engine': 'shifu_v2_enterprise'})
            resource = CloudinaryResource(public_id=upload_result['public_id'], secure_url=upload_result['secure_url'], resource_type=upload_result['resource_type'], format=upload_result.get('format', 'raw'), bytes=upload_result['bytes'], created_at=upload_result['created_at'], metadata=upload_result.get('context', {}).get('custom', {}))
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f' Resource uploaded in {duration}s. ID: {resource.public_id}')
            return resource
        except CloudinaryError as ce:
            logger.error(f' Cloudinary API Error: {str(ce)}')
            raise
        except Exception as e:
            logger.error(f' Unexpected Upload Failure: {str(e)}')
            raise

    def delete_resources(self, public_ids: List[str]) -> bool:
        """Eliminación masiva optimizada."""
        try:
            result = cloudinary.api.delete_resources(public_ids)
            status = all((v == 'deleted' for v in result.get('deleted', {}).values()))
            logger.warning(f"🗑️ Bulk deletion executed. Status: {result.get('deleted')}")
            return status
        except Exception as e:
            logger.error(f' Deletion failed: {str(e)}')
            return False

    def get_user_inventory(self, user_email: str, next_cursor: str=None) -> Dict[str, Any]:
        """Listado con paginación real (Enterprise Standard)."""
        try:
            clean_email = self._sanitize_identifier(user_email)
            return cloudinary.api.resources(type='upload', prefix=f'shifu_v2/{clean_email}/', max_results=30, next_cursor=next_cursor)
        except Exception as e:
            logger.error(f'❌ Inventory retrieval failed: {str(e)}')
            return {'resources': [], 'next_cursor': None}

    @staticmethod
    def _sanitize_identifier(identifier: str) -> str:
        """Limpia emails y nombres para que sean paths válidos en la nube."""
        return identifier.lower().replace('@', '_at_').replace('.', '_')
cloudinary_service = CloudinaryService()
