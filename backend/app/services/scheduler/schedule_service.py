from app.services.scheduler.time_utils import normalize_run_at
from app.services.mongo_schedule_manager import MongoScheduleManager
from app.core.db_utils import canonicalize_email
import datetime

class ScheduleService:

    def __init__(self):
        self.manager = MongoScheduleManager()

    def schedule_process(self, user_email: str, user_input: str, hour: int, minute: int, user_timezone: str):
        run_at_utc = normalize_run_at(hour=hour, minute=minute, user_tz=user_timezone)
        if run_at_utc <= datetime.datetime.utcnow():
            raise ValueError('La fecha programada ya pasó')
        email_safe = canonicalize_email(user_email)
        job = self.manager.create_job(user_email=email_safe or user_email, user_input=user_input, run_at=run_at_utc, repeat_every_seconds=None, schedule_type='once', time_of_day=None, start_at=run_at_utc, end_at=None, scheduled_timezone=user_timezone)
        return {'message': 'Proceso programado correctamente', 'run_at_utc': run_at_utc.isoformat(), 'job_id': str(job)}
