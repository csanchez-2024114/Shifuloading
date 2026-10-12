"""
User Memories Service - Motor de Cognición y Aprendizaje Continuo.
Gestiona el grafo de conocimiento del usuario y sus preferencias semánticas.
"""
import datetime
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from bson import ObjectId
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from config import Config
from app.core.mongo import get_sync_database
from app.core.db_utils import canonicalize_email, find_memories_by_email, upsert_memories_by_email
load_dotenv()

class UserMemoriesService:

    def __init__(self, user_email: str):
        self.user_email = user_email
        self.user_email = canonicalize_email(user_email) or (user_email or '').lower()
        self.db = get_sync_database()
        self.collection = self.db.user_memories
        self.llm = ChatOpenAI(model=Config.MODEL_NAME, api_key=Config.OPENAI_API_KEY, temperature=0)

    def get_or_create_memories(self) -> Dict[str, Any]:
        """Recupera el cerebro digital del usuario o inicializa uno nuevo."""
        try:
            e = self.user_email
            doc = find_memories_by_email(db=self.db, email=e)
            if doc:
                return doc
            now = datetime.datetime.now(datetime.timezone.utc)
            new_doc = {'user_email': e, 'memories': [], 'entity_registry': {}, 'created_at': now, 'updated_at': now, 'total_memories': 0, 'average_confidence': 0.0, 'is_active': True}
            res = upsert_memories_by_email(db=self.db, email=e, doc=new_doc)
            if res.get('upserted_id'):
                new_doc['_id'] = res.get('upserted_id')
            else:
                doc = find_memories_by_email(db=self.db, email=e)
                if doc:
                    return doc
            return new_doc
        except Exception as e:
            print(f' Error en Memory Document: {e}')
            return {}

    def detect_and_update_memories(self, user_input: str, llm_response: str, memory_doc: Dict) -> Dict:
        """Analiza la interacción actual para extraer nuevos conocimientos."""
        try:
            extraction = self._extract_with_llm(user_input, llm_response)
            changes = {'added': [], 'updated': [], 'removed': []}
            now = datetime.datetime.now(datetime.timezone.utc)
            for item in extraction.get('deletions', []):
                if self._remove_memory(memory_doc, item):
                    changes['removed'].append(item['key'])
            for item in extraction.get('preferences', []):
                if not self._validate_and_sanitize(item):
                    continue
                status = self._upsert_memory_logic(memory_doc, item, now)
                if status:
                    changes[status].append(item['key'])
            if any(changes.values()):
                self._finalize_update(memory_doc, now)
                return {'success': True, 'changes': changes}
            return {'success': False, 'message': 'No hay cambios nuevos'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _validate_and_sanitize(self, item: Dict) -> bool:
        """Evita que Shifu guarde datos prohibidos (Tarjetas, Passwords, etc)."""
        val = str(item.get('value', '')).lower()
        key = str(item.get('key', '')).lower()
        prohibido = ['card', 'pin', 'cvv', 'password', 'contraseña', 'token', 'api_key', 'cuenta']
        if any((p in val or p in key for p in prohibido)):
            return False
        if re.search('\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b', val):
            return False
        return True

    def format_memories_for_llm(self, memory_doc: Dict) -> str:
        """Transforma el JSON de DB en un prompt legible para el agente."""
        memories = memory_doc.get('memories', [])
        if not memories:
            return ''
        output = '\n [MEMORIA DEL USUARIO DETECTADA]:\n'
        output += '------------------------------------------\n'
        categories = {}
        for m in memories:
            cat = m.get('category', 'general')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(m)
        for cat, items in categories.items():
            output += f' {cat.upper()}:\n'
            for i in items:
                output += f"  • {i['key']}: {i['value']} (Confianza: {i['confidence']})\n"
        return output + '------------------------------------------\n'

    def _extract_with_llm(self, ui: str, lr: str) -> Dict:
        """Llamada maestra al LLM para diseccionar la conversación."""
        prompt = f'Analiza la conversación y extrae preferencias del usuario en JSON. \n        Usuario: {ui}\n        Asistente: {lr}\n        Responde SOLO JSON: {{"preferences": [{{key, value, category, confidence, description, subject: {{entity_id, entity_type, entity_name}}, semantic_tags: [], relations: []}}], "deletions": []}}'
        res = self.llm.invoke(prompt).content
        return json.loads(re.search('\\{.*\\}', res, re.DOTALL).group())

    def _upsert_memory_logic(self, doc: Dict, item: Dict, now: datetime.datetime) -> Optional[str]:
        """Lógica de actualización vs inserción."""
        for m in doc['memories']:
            if m['key'] == item['key']:
                m.update({'value': item['value'], 'updated_at': now})
                m['update_count'] = m.get('update_count', 1) + 1
                return 'updated'
        item.update({'memory_id': f'mem_{uuid.uuid4().hex[:8]}', 'created_at': now, 'updated_at': now, 'update_count': 1})
        doc['memories'].append(item)
        return 'added'

    def _finalize_update(self, doc: Dict, now: datetime.datetime):
        """Recalcula estadísticas y guarda en Mongo."""
        doc['total_memories'] = len(doc['memories'])
        doc['updated_at'] = now
        upsert_memories_by_email(db=self.db, email=self.user_email, doc=doc)
