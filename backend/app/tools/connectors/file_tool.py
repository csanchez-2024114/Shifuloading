"""
File Provider Tool para LangGraph / LangChain
Refactorización: Eliminación de Fallos Silenciosos.
- Registra cada error para telemetría (logs).
- Implementa degradación elegante en PDFs (Hi-Res -> PyPDF -> OCR).
- Retorna strings controlados al LLM si falla la lectura, preservando el input del usuario.

get_text_and_meta()/fetch_bytes() reusan la misma cascada de extracción que
getContext() (vía los helpers privados _extract_*) para document_analyzer,
que necesita texto plano cacheable/comparable en vez de content-blocks
multimodales listos para inyectar directo en un mensaje de chat.
"""
import os
import base64
import logging
from io import BytesIO
from typing import Union
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from unstructured.partition.docx import partition_docx
from unstructured.partition.msg import partition_msg
from unstructured.partition.pptx import partition_pptx
from pypdf import PdfReader
from unstructured.partition.pdf import partition_pdf
from pdf2image import convert_from_bytes
import pytesseract
import pandas as pd
import json
from openai import AsyncOpenAI
from langchain_core.tools import ToolException
from config import Config

logger = logging.getLogger('tools.file_provider')

class FileProvider:

    def __init__(self):
        self._vision_client = None

    def _ext(self, filename: str) -> str:
        """Extrae la extensión del archivo de forma segura."""
        return os.path.splitext(filename)[1].lower().lstrip('.')

    def _to_bytesio(self, file_content_or_file) -> BytesIO:
        """Convierte bytes o file-like objects a BytesIO en memoria."""
        if hasattr(file_content_or_file, 'read'):
            pos = file_content_or_file.tell() if hasattr(file_content_or_file, 'tell') else None
            data = file_content_or_file.read()
            try:
                if pos is not None:
                    file_content_or_file.seek(pos)
            except Exception as e:
                logger.debug(f'[FileProvider] No se pudo resetear el cursor del stream: {e}')
        else:
            data = file_content_or_file
        return BytesIO(data)

    def _decode_text(self, raw_bytes: bytes) -> str:
        """Decodificación robusta intentando múltiples codificaciones."""
        for enc in ('utf-8', 'latin1', 'cp1252'):
            try:
                return raw_bytes.decode(enc)
            except Exception:
                continue
        return raw_bytes.decode('utf-8', errors='ignore')

    def _collapse_ws(self, s: str) -> str:
        """Colapsa múltiples espacios en blanco y saltos de línea."""
        return ' '.join(s.replace('\r', ' ').replace('\n', ' ').split())

    # ── Descarga remota (Cloudinary u otra URL HTTPS) ─────────────────────────

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    async def fetch_bytes(url: str, *, timeout: float = 30.0) -> bytes:
        """Descarga un recurso (ej. secure_url de Cloudinary) a memoria."""
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    # ── Cascadas de extracción compartidas (texto plano, sin formatear) ──────

    def _extract_pdf(self, file_bytes: bytes, *, ocr_allowed: bool = True) -> dict:
        """Cascada: unstructured(hi_res) -> pypdf -> OCR (pytesseract, si ocr_allowed
        y el texto extraído es pobre). Retorna texto plano + metadata del motor usado,
        nunca lanza excepción."""
        try:
            elements = partition_pdf(file=BytesIO(file_bytes), strategy='hi_res', infer_table_structure=True)
            chunks = [e.text for e in elements if getattr(e, 'text', None)]
            text = '\n'.join(chunks).strip()
            if text:
                page_count = None
                try:
                    reader = PdfReader(BytesIO(file_bytes))
                    page_count = len(reader.pages)
                except Exception:
                    pass
                return {'text': text, 'engine': 'hi_res', 'page_count': page_count, 'ocr_used': False, 'error': None}
        except Exception as e:
            logger.warning(f"[FileProvider] Falló estrategia 'hi_res' en PDF: {e}. Iniciando fallback PyPDF.")

        quick_text = ''
        page_count = None
        try:
            reader = PdfReader(BytesIO(file_bytes))
            page_count = len(reader.pages)
            pages_text = []
            for i, p in enumerate(reader.pages):
                try:
                    pages_text.append(p.extract_text() or '')
                except Exception as page_e:
                    logger.warning(f'[FileProvider] Error extrayendo página {i} de PyPDF: {page_e}')
                    pages_text.append('[Error en lectura de página]')
            quick_text = '\n'.join(pages_text).strip()
        except Exception as e:
            logger.error(f'[FileProvider] Falla crítica en PyPDF: {e}')

        if len(quick_text) < 50:
            if not ocr_allowed:
                return {'text': quick_text, 'engine': 'pypdf', 'page_count': page_count,
                        'ocr_used': False, 'error': 'ocr_blocked_by_plan' if not quick_text else None}
            logger.info('[FileProvider] Texto escaso detectado. Iniciando motor OCR...')
            try:
                images = convert_from_bytes(file_bytes, dpi=200)
                ocr_texts = []
                for i, img in enumerate(images[:10]):
                    try:
                        ocr_texts.append(pytesseract.image_to_string(img, lang='spa+eng'))
                    except Exception as ocr_e:
                        logger.warning(f'[FileProvider] Error de Tesseract OCR en página {i}: {ocr_e}')
                        ocr_texts.append('[Error OCR en página]')
                ocr_text = '\n'.join(ocr_texts).strip()
                if ocr_text:
                    return {'text': ocr_text, 'engine': 'ocr', 'page_count': page_count, 'ocr_used': True, 'error': None}
            except Exception as e:
                logger.error(f'[FileProvider] Fallo total de OCR: {e}')
                return {'text': quick_text, 'engine': 'pypdf', 'page_count': page_count,
                        'ocr_used': False, 'error': f'ocr_failed: {e}'}

        return {'text': quick_text, 'engine': 'pypdf', 'page_count': page_count, 'ocr_used': False, 'error': None}

    def _extract_docx(self, file_bytes: bytes) -> dict:
        try:
            elements = partition_docx(file=BytesIO(file_bytes))
            chunks = [e.text for e in elements if getattr(e, 'text', None)]
            return {'text': '\n'.join(chunks), 'engine': 'docx', 'page_count': None, 'ocr_used': False, 'error': None}
        except Exception as e:
            logger.error(f'[FileProvider] Error extrayendo DOCX: {e}')
            return {'text': '', 'engine': 'docx', 'page_count': None, 'ocr_used': False, 'error': str(e)}

    def _extract_pptx(self, file_bytes: bytes) -> dict:
        try:
            elements = partition_pptx(file=BytesIO(file_bytes))
            chunks = [e.text for e in elements if getattr(e, 'text', None)]
            return {'text': '\n'.join(chunks), 'engine': 'pptx', 'page_count': None, 'ocr_used': False, 'error': None}
        except Exception as e:
            logger.error(f'[FileProvider] Error extrayendo PPTX: {e}')
            return {'text': '', 'engine': 'pptx', 'page_count': None, 'ocr_used': False, 'error': str(e)}

    def _extract_msg(self, file_bytes: bytes) -> dict:
        try:
            elements = partition_msg(file=BytesIO(file_bytes))
            chunks = [e.text for e in elements if getattr(e, 'text', None)]
            return {'text': '\n'.join(chunks), 'engine': 'msg', 'page_count': None, 'ocr_used': False, 'error': None}
        except Exception as e:
            logger.error(f'[FileProvider] Error extrayendo MSG: {e}')
            return {'text': '', 'engine': 'msg', 'page_count': None, 'ocr_used': False, 'error': str(e)}

    def _extract_excel(self, file_bytes: bytes) -> dict:
        try:
            xls = pd.ExcelFile(BytesIO(file_bytes))
            all_sheets_text = []
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                sheet_text = df.to_string(index=False, na_rep='')
                all_sheets_text.append(f'--- Hoja: {sheet_name} ---\n{sheet_text}')
            return {'text': '\n\n'.join(all_sheets_text), 'engine': 'pandas', 'page_count': None, 'ocr_used': False, 'error': None}
        except Exception as e:
            logger.error(f'[FileProvider] Error procesando Excel: {e}')
            return {'text': '', 'engine': 'pandas', 'page_count': None, 'ocr_used': False, 'error': str(e)}

    def _extract_csv(self, file_bytes: bytes) -> dict:
        try:
            df = pd.read_csv(BytesIO(file_bytes))
            return {'text': df.to_string(index=False), 'engine': 'pandas', 'page_count': None, 'ocr_used': False, 'error': None}
        except Exception as e:
            logger.error(f'[FileProvider] Error procesando CSV: {e}')
            return {'text': '', 'engine': 'pandas', 'page_count': None, 'ocr_used': False, 'error': str(e)}

    def _extract_json(self, file_bytes: bytes) -> dict:
        try:
            data = json.loads(file_bytes)
            return {'text': json.dumps(data, indent=2), 'engine': 'text', 'page_count': None, 'ocr_used': False, 'error': None}
        except Exception as e:
            logger.error(f'[FileProvider] Error procesando JSON: {e}')
            return {'text': '', 'engine': 'text', 'page_count': None, 'ocr_used': False, 'error': str(e)}

    def _extract_generic_text(self, file_bytes: bytes) -> dict:
        try:
            text = self._collapse_ws(self._decode_text(file_bytes))
            return {'text': text, 'engine': 'text', 'page_count': None, 'ocr_used': False, 'error': None}
        except Exception as e:
            logger.error(f'[FileProvider] Error leyendo texto genérico: {e}')
            return {'text': '', 'engine': 'text', 'page_count': None, 'ocr_used': False, 'error': str(e)}

    async def _transcribe_image(self, img_bytes: bytes, ext: str) -> dict:
        """Transcribe una foto/imagen de documento a texto plano vía visión
        (gpt-4o-mini). Cuenta como OCR para efectos de plan-gating (ver
        get_text_and_meta): una foto de una factura escaneada es, en costo y
        producto, la misma operación que el fallback OCR de un PDF escaneado."""
        try:
            if self._vision_client is None:
                self._vision_client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            mime = 'jpeg' if ext == 'jpg' else ext
            resp = await self._vision_client.chat.completions.create(
                model='gpt-4o-mini',
                temperature=0,
                max_tokens=4000,
                messages=[{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': (
                            'Transcribe verbatim ALL text visible in this image (document, receipt, '
                            'form, table, etc.). Preserve structure/line breaks. If it is not a '
                            'document (e.g. a photo with no text), describe it briefly instead.'
                        )},
                        {'type': 'image_url', 'image_url': {'url': f'data:image/{mime};base64,{img_b64}'}},
                    ],
                }],
            )
            text = (resp.choices[0].message.content or '').strip()
            return {'text': text, 'engine': 'vision', 'page_count': None, 'ocr_used': True, 'error': None}
        except Exception as e:
            logger.error(f'[FileProvider] Error transcribiendo imagen vía vision: {e}')
            return {'text': '', 'engine': 'vision', 'page_count': None, 'ocr_used': False, 'error': str(e)}

    async def get_text_and_meta(self, file_bytes: bytes, filename: str, *, ocr_allowed: bool = True) -> dict:
        """
        Extrae texto plano + metadata (para caché/chunking/comparación entre
        documentos), a diferencia de getContext() que arma content-blocks
        multimodales listos para inyectar directo en un mensaje de chat.
        Retorna: {"text": str, "engine": str, "page_count": int|None,
                   "ocr_used": bool, "error": str|None}
        """
        ext = self._ext(filename)
        if ext in {'png', 'jpg', 'jpeg', 'webp'}:
            if not ocr_allowed:
                return {'text': '', 'engine': 'vision_blocked_by_plan', 'page_count': None, 'ocr_used': False, 'error': None}
            return await self._transcribe_image(file_bytes, ext)
        if ext == 'pdf':
            return self._extract_pdf(file_bytes, ocr_allowed=ocr_allowed)
        if ext == 'docx':
            return self._extract_docx(file_bytes)
        if ext == 'pptx':
            return self._extract_pptx(file_bytes)
        if ext == 'ppt':
            return {'text': '', 'engine': 'pptx', 'page_count': None, 'ocr_used': False,
                    'error': 'formato .ppt (binario legacy) no soportado, solo .pptx'}
        if ext == 'msg':
            return self._extract_msg(file_bytes)
        if ext in {'xlsx', 'xls'}:
            return self._extract_excel(file_bytes)
        if ext == 'csv':
            return self._extract_csv(file_bytes)
        if ext == 'json':
            return self._extract_json(file_bytes)
        return self._extract_generic_text(file_bytes)

    def getContext(self, file_content_or_file: Union[bytes, BytesIO], filename: str, user_input: str):
        """
        Extrae el contenido de diversos tipos de archivos y lo empaqueta
        junto con el prompt del usuario en formato de mensaje para LLMs multimodales.
        """
        ext = self._ext(filename)
        if ext in {'png', 'jpg', 'jpeg', 'webp'}:
            try:
                bio = self._to_bytesio(file_content_or_file)
                img_b = bio.read()
                img_base64 = base64.b64encode(img_b).decode('utf-8')
                content = [{'type': 'text', 'text': user_input}, {'type': 'image_url', 'image_url': {'url': f"data:image/{(ext if ext != 'jpg' else 'jpeg')};base64,{img_base64}"}}]
                return content
            except Exception as e:
                logger.error(f'[FileProvider] Error procesando imagen {filename}: {e}')
                return [{'type': 'text', 'text': f'Error procesando la imagen: {e}\n{user_input}'}]
        if ext == 'docx':
            logger.info(f'📄 Extrayendo datos de DOCX: {filename}')
            result = self._extract_docx(self._to_bytesio(file_content_or_file).getvalue())
            if result['error']:
                return [{'type': 'text', 'text': f"Error al procesar archivo Word DOCX: {result['error']}\n{user_input}"}]
            merged = f"Context: {result['text']}\n{user_input}"
            return [{'type': 'text', 'text': merged}]
        if ext == 'pdf':
            logger.info(f'📄 Procesando PDF: {filename}')
            result = self._extract_pdf(self._to_bytesio(file_content_or_file).getvalue(), ocr_allowed=True)
            if result['error'] and not result['text']:
                return [{'type': 'text', 'text': f"Error procesando PDF escaneado (OCR falló): {result['error']}\n{user_input}"}]
            label = {'hi_res': 'PDF, AI', 'ocr': 'PDF, OCR', 'pypdf': 'PDF'}.get(result['engine'], 'PDF')
            extracted = f"Context ({label}): " + (result['text'] or '[Documento vacío o ilegible]')
            merged = f'{extracted}\n{user_input}'
            return [{'type': 'text', 'text': merged}]
        if ext in {'xlsx', 'xls'}:
            logger.info(f'📊 Extrayendo datos de Excel: {filename}')
            result = self._extract_excel(self._to_bytesio(file_content_or_file).getvalue())
            if result['error']:
                return [{'type': 'text', 'text': f"Error al procesar hoja de cálculo Excel: {result['error']}\n{user_input}"}]
            merged = f"Context (Excel):\n{result['text']}\n{user_input}"
            return [{'type': 'text', 'text': merged}]
        if ext == 'csv':
            logger.info(f'📉 Extrayendo datos de CSV: {filename}')
            result = self._extract_csv(self._to_bytesio(file_content_or_file).getvalue())
            if result['error']:
                return [{'type': 'text', 'text': f"Error al leer archivo CSV: {result['error']}\n{user_input}"}]
            merged = f"Context (CSV):\n{result['text']}\n{user_input}"
            return [{'type': 'text', 'text': merged}]
        if ext == 'json':
            logger.info(f'📑 Extrayendo datos de JSON: {filename}')
            result = self._extract_json(self._to_bytesio(file_content_or_file).getvalue())
            if result['error']:
                return [{'type': 'text', 'text': f"Error de formato al leer JSON: {result['error']}\n{user_input}"}]
            merged = f"Context (JSON):\n{result['text']}\n{user_input}"
            return [{'type': 'text', 'text': merged}]
        logger.info(f'📝 Extrayendo datos de archivo de texto genérico: {filename}')
        result = self._extract_generic_text(self._to_bytesio(file_content_or_file).getvalue())
        if result['error']:
            return [{'type': 'text', 'text': f"Error procesando el archivo de texto: {result['error']}\n{user_input}"}]
        merged = f"{result['text']}\n{user_input}"
        return [{'type': 'text', 'text': merged}]
