import datetime
from datetime import datetime, timezone
from app.core.mongo import get_sync_database

class MongoScheduleManager:

    def __init__(self):
        self.db = get_sync_database()
        self.collection = self.db['scheduled_processes']

    def create_job(self, user_email, user_input, run_at, repeat_every_seconds: int=None, schedule_type: str='once', time_of_day: str=None, start_at=None, end_at=None, scheduled_timezone: str=None):
        """
        Crea un job programado.

        Parámetros adicionales soportados mediante kwargs (opcionales):
        - repeat_every_seconds: int (intervalo en segundos)
        - schedule_type: 'once'|'interval'|'daily'
        - time_of_day: 'HH:MM' usado para schedule_type='daily'
        - start_at, end_at: datetime para rangos
        - scheduled_timezone: IANA timezone del usuario al momento de programar
        """
        doc = {'user_email': user_email, 'user_input': user_input, 'run_at': run_at, 'repeat_every_seconds': repeat_every_seconds, 'schedule_type': schedule_type, 'time_of_day': time_of_day, 'start_at': start_at, 'end_at': end_at, 'scheduled_timezone': scheduled_timezone, 'status': 'PENDING', 'created_at': datetime.now(timezone.utc), 'last_run_at': None, 'error': None}
        result = self.collection.insert_one(doc)
        return result.inserted_id

    def fetch_due_jobs(self):
        now = datetime.now(timezone.utc)
        return list(self.collection.find({'status': 'PENDING', 'run_at': {'$lte': now}}))

    def mark_running(self, job_id):
        self.collection.update_one({'_id': job_id}, {'$set': {'status': 'RUNNING', 'last_run_at': datetime.now(timezone.utc)}})

    def mark_done(self, job_id, next_run=None):
        update = {'status': 'DONE', 'error': None}
        if next_run:
            update['status'] = 'PENDING'
            update['run_at'] = next_run
        self.collection.update_one({'_id': job_id}, {'$set': update})

    def mark_error(self, job_id, error):
        self.collection.update_one({'_id': job_id}, {'$set': {'status': 'ERROR', 'error': error}})
