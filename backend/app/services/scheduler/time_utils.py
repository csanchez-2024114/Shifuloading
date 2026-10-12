from datetime import datetime, timedelta
import pytz

def normalize_run_at(hour: int, minute: int, user_tz: str) -> datetime:
    """
    Convierte una hora local del usuario a UTC.
    Si la hora ya pasó hoy, programa para mañana.
    """
    tz = pytz.timezone(user_tz)
    now_local = datetime.now(tz)
    candidate_local = tz.localize(datetime(year=now_local.year, month=now_local.month, day=now_local.day, hour=hour, minute=minute, second=0, microsecond=0))
    if candidate_local <= now_local:
        candidate_local += timedelta(days=1)
    return candidate_local.astimezone(pytz.utc)
