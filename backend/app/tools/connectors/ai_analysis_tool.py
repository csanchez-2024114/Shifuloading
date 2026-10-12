"""
Tool para análisis de archivos con GPT-vision
Flujo: Archivo local → Cloudinary → GPT-vision → Análisis JSON
Soporte especial para PDFs grandes con procesamiento por lotes

Refactorización:
- Erradicación de fallos silenciosos (uso estricto de ToolException).
- Inyección de handle_tool_error=True vía _make_tool.
- Integración con Config centralizado.
- Corrección de orfandad: Implementación de get_all_tools().
"""
import base64
import io
import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
import tempfile
from dotenv import load_dotenv
from langchain_core.tools import StructuredTool, ToolException
from openai import OpenAI
from pydantic import BaseModel, Field
try:
    import fitz
    from PIL import Image
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print(' PyMuPDF no disponible. Instala con: pip install PyMuPDF Pillow')
from app.services.cloudinary_service import cloudinary_service
from config import Config
from app.core.db_utils import canonicalize_email
load_dotenv()
logger = logging.getLogger('tools.ai_analysis')

class UploadFileInput(BaseModel):
    file_path: str = Field(..., alias='ruta_archivo', description='Ruta del archivo local a subir (ej: /tmp/documento.pdf)')
    folder: str = Field(default='ai_analysis', alias='carpeta', description='Carpeta en Cloudinary')

class AnalyzeWithVisionInput(BaseModel):
    file_urls: List[str] = Field(..., alias='urls_archivo', description='Una o varias URLs (secure_url) de Cloudinary')
    analysis_prompt: str = Field(default='Analiza este archivo y proporciona un resumen detallado de su contenido, hallazgos principales y observaciones importantes.', description='Instrucción personalizada para GPT-vision')

class AnalyzePDFByBatchesInput(BaseModel):
    pdf_path: str = Field(..., alias='ruta_pdf', description='Ruta del archivo PDF local a analizar (ej: /tmp/documento.pdf)')
    batch_size: int = Field(default=10, alias='tamanio_lote', description='Número de páginas por lote (default: 10)')
    analysis_prompt: str = Field(default='Analiza estas páginas del PDF y proporciona un resumen detallado del contenido.', description='Instrucción personalizada para el análisis')

class AIAnalysisToolProvider:

    def __init__(self, user_email: str | None=None):
        email_source = user_email or 'system_ai_vision'
        canonical = canonicalize_email(email_source) or (email_source or 'system_ai_vision')
        self.user_email = canonical
        self.openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.MODEL_NAME if hasattr(Config, 'MODEL_NAME') else 'gpt-4o'
        self.pdf_batch_size = 10
        self.max_pdf_pages = 200
        self.supported_types = {'image': ['jpg', 'jpeg', 'png', 'gif', 'webp'], 'video': ['mp4', 'mov', 'webm'], 'pdf': ['pdf']}

    def _make_tool(self, name: str, func: Callable, description: str, args_schema: type[BaseModel]) -> StructuredTool:
        """Helper Enterprise para inyectar handle_tool_error=True en todas las herramientas."""
        return StructuredTool.from_function(func=func, name=name, description=description, args_schema=args_schema, handle_tool_error=True)

    def _convert_pdf_pages_to_images(self, pdf_path: str, start_page: int=0, end_page: int=None) -> List[Tuple[int, str]]:
        if not PYMUPDF_AVAILABLE:
            raise ToolException('PyMuPDF no está disponible en el entorno. No se pueden procesar PDFs locales.')
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            end_page = min(end_page or total_pages, total_pages)
            images = []
            for page_num in range(start_page, end_page):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes('png')
                img_base64 = base64.b64encode(img_data).decode('utf-8')
                images.append((page_num + 1, f'data:image/png;base64,{img_base64}'))
            doc.close()
            return images
        except Exception as e:
            logger.error(f'[AIAnalysisTool] Error convirtiendo PDF a imágenes: {e}')
            raise ToolException(f'Error procesando las páginas del PDF: {str(e)}')

    def _analyze_pdf_by_batches(self, pdf_path: str, batch_size: int=10, analysis_prompt: str='Analiza estas páginas del PDF.') -> str:
        if not PYMUPDF_AVAILABLE:
            raise ToolException('PyMuPDF (fitz) no instalado. Es requerido para procesar PDFs.')
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()
            if total_pages > self.max_pdf_pages:
                raise ToolException(f'El documento excede el límite permitido ({total_pages} > {self.max_pdf_pages} páginas).')
            batch_results = []
            actual_batch_size = batch_size or self.pdf_batch_size
            num_batches = (total_pages + actual_batch_size - 1) // actual_batch_size
            for batch_idx in range(num_batches):
                start = batch_idx * actual_batch_size
                end = min(start + actual_batch_size, total_pages)
                page_images = self._convert_pdf_pages_to_images(pdf_path, start, end)
                if not page_images:
                    continue
                content = [{'type': 'text', 'text': f'{analysis_prompt}\n\n[Páginas {start + 1}-{end} de {total_pages}]'}]
                for _, img_data in page_images:
                    content.append({'type': 'image_url', 'image_url': {'url': img_data, 'detail': 'high'}})
                response = self.openai_client.chat.completions.create(model=self.model, messages=[{'role': 'user', 'content': content}], temperature=0.3, max_tokens=2000)
                batch_results.append({'batch': batch_idx + 1, 'pages': f'{start + 1}-{end}', 'analysis': response.choices[0].message.content})
            combined = f'ANÁLISIS DE PDF COMPLETO ({total_pages} páginas)\n'
            for r in batch_results:
                combined += f"\n--- PÁGINAS {r['pages']} ---\n{r['analysis']}\n"
            return json.dumps({'success': True, 'analysis': combined, 'total_pages': total_pages}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f'[AIAnalysisTool] Error en análisis por lotes de PDF: {e}')
            raise ToolException(f'Fallo durante el análisis del PDF: {str(e)}')

    def upload_file_to_cloudinary(self, file_path: str, folder: str='ai_analysis') -> str:
        try:
            if not os.path.exists(file_path):
                raise ToolException(f'Archivo local no encontrado en la ruta: {file_path}')
            with open(file_path, 'rb') as f:

                class FileObj:

                    def __init__(self, stream, name):
                        self.stream = stream
                        self.filename = name

                    def read(self, *args):
                        return self.stream.read(*args)

                    def seek(self, *args):
                        return self.stream.seek(*args)
                result = cloudinary_service.upload_file(file=FileObj(f, os.path.basename(file_path)), folder=folder, user_email=self.user_email)
            res_dict = result.model_dump() if hasattr(result, 'model_dump') else result
            return json.dumps(res_dict, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f'[AIAnalysisTool] Error subiendo archivo a Cloudinary: {e}')
            raise ToolException(f'Fallo al subir el archivo a la nube: {str(e)}')

    def analyze_with_gpt_vision(self, file_urls: List[str], analysis_prompt: str='Analiza este archivo detalladamente.') -> str:
        try:
            if not file_urls:
                raise ToolException('No se proporcionaron URLs para analizar. Sube el archivo primero.')
            content = [{'type': 'text', 'text': analysis_prompt}]
            for url in file_urls:
                content.append({'type': 'image_url', 'image_url': {'url': url, 'detail': 'high'}})
            response = self.openai_client.chat.completions.create(model=self.model, messages=[{'role': 'user', 'content': content}], max_tokens=2000)
            return json.dumps({'success': True, 'analysis': response.choices[0].message.content, 'urls': file_urls}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f'[AIAnalysisTool] Error en analyze_with_gpt_vision: {e}')
            raise ToolException(f'Error procesando la imagen/documento con GPT-Vision: {str(e)}')

    def get_tool_upload_to_cloudinary(self) -> StructuredTool:
        return self._make_tool(name='upload_file_to_cloudinary', func=self.upload_file_to_cloudinary, description='Sube un archivo local a la nube (Cloudinary) y devuelve los metadatos y la URL segura para ser analizada por IA.', args_schema=UploadFileInput)

    def get_tool_analyze_with_gpt_vision(self) -> StructuredTool:
        return self._make_tool(name='analyze_with_gpt_vision', func=self.analyze_with_gpt_vision, description='Utiliza GPT-4o Vision para analizar imágenes o documentos a partir de sus URLs en la nube.', args_schema=AnalyzeWithVisionInput)

    def get_tool_analyze_pdf_by_batches(self) -> StructuredTool:
        return self._make_tool(name='analyze_pdf_by_batches', func=self._analyze_pdf_by_batches, description='Herramienta especializada para analizar PDFs largos dividiéndolos en lotes de imágenes. Extrae el contenido directamente del archivo local.', args_schema=AnalyzePDFByBatchesInput)

    def get_all_tools(self) -> List[Any]:
        """Registro para inyectar al agente de LangGraph"""
        return [self.get_tool_upload_to_cloudinary(), self.get_tool_analyze_with_gpt_vision(), self.get_tool_analyze_pdf_by_batches()]
