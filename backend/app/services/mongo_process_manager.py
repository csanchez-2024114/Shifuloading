"""
Manager Legacy de Procesos en MongoDB.
Responsabilidad: Consultar reglas de plan y persistir procesos históricos.
Arquitectura Refactorizada: Normalización robusta, Logging y Telemetría.
"""
import logging
from datetime import datetime, timezone
from pymongo import MongoClient
from bson import ObjectId
from config import Config
from app.billing.plans import get_plan_rules
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email, find_user_by_email
logger = logging.getLogger(__name__)

class MongoProcessManager:

    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI)
        self.db = self.client[Config.MONGO_DB_NAME]
        self.collection = self.db[Collections.PROCESSES]
        self.usuarios_coll = self.db[Collections.USERS]

    def get_user_plan_limits(self, user_email: str):
        """
        Consulta el plan del usuario en la BD y retorna las reglas
        definidas en la clase Config centralizada.
        """
        if not user_email:
            return get_plan_rules('free')
        email_safe = canonicalize_email(user_email)
        user = find_user_by_email(self.db, email_safe)
        plan_name = user.get('plan', 'free') if user else 'free'
        return get_plan_rules(plan_name)

    def save_process(self, proceso: dict, user_email: str):
        """
        Guarda un proceso ligado al usuario, incluyendo metadata del plan y telemetría de errores.
        """
        if not user_email:
            logger.error('No se puede guardar el proceso: user_email no proporcionado.')
            return None
        email_safe = canonicalize_email(user_email)
        steps = proceso.get('steps', [])
        has_errors = False
        for s in steps:
            if isinstance(s, dict):
                if s.get('error'):
                    has_errors = True
                    break
                obs = s.get('observation', '')
                if isinstance(obs, str):
                    obs_lower = obs.lower()
                    if any((keyword in obs_lower for keyword in ['error', 'exception', 'invalid_grant', 'fail'])):
                        has_errors = True
                        break
            elif 'error' in str(s).lower():
                has_errors = True
                break
        process_status = 'failed' if has_errors else 'success'
        user = find_user_by_email(self.db, email_safe)
        user_id = str(user.get('_id')) if user else None
        plan_name = user.get('plan', 'free') if user else 'free'
        doc = {'user_id': user_id, 'user_email': email_safe, 'process_name': proceso.get('nombre', 'Proceso sin nombre'), 'description': proceso.get('descripcion', ''), 'steps': steps, 'output': proceso.get('output', ''), 'quantitative_summary': proceso.get('quantitative_summary', ''), 'created_at': datetime.now(timezone.utc), 'total_steps': len(steps) if isinstance(steps, list) else proceso.get('total_steps', 0), 'status': process_status, 'metadata': {'plan_at_execution': plan_name, 'version_config': '1.1'}}
        try:
            result = self.collection.insert_one(doc)
            logger.info(f"Proceso '{doc.get('process_name') or doc.get('nombre_proceso')}' guardado con status='{process_status}'. ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            logger.error(f'Fallo al intentar guardar el proceso en MongoDB: {e}', exc_info=True)
            return None

    def load_process(self, process_name: str, user_email: str):
        if not user_email:
            return None
        email_safe = canonicalize_email(user_email)
        return self.collection.find_one({'process_name': process_name, 'user_email': email_safe})

    def load_all_by_user(self, user_email: str, user_id: str | None = None):
        if not user_email and not user_id:
            return []
        email_safe = canonicalize_email(user_email) if user_email else ""
        conditions: list = []
        if email_safe:
            conditions.append({"user_email": email_safe})
        if user_id:
            conditions.append({"user_id": user_id})
        query = {"$or": conditions} if len(conditions) > 1 else conditions[0]
        return list(self.collection.find(query))
