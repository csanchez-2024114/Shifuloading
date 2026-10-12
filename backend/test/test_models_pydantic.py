from datetime import datetime, timezone

from app.models.user_model import UserModel
from app.models.process_model import ProcessModel, ProcessTempModel


def test_user_model_accepts_spanish_and_english_fields():
    # Now DB uses English field names; ensure English payloads validate
    data_en = {
        "email": "test@example.com",
        "name": "Test",
        "last_name": "User",
        "preferences": {"theme": "dark"},
        "is_active": True,
    }

    u = UserModel.model_validate(data_en)
    assert u.email == "test@example.com"
    assert u.name == "Test"
    assert u.last_name == "User"
    assert u.preferences.get("theme") == "dark"
    assert u.is_active is True
    data_en2 = {
        "email": "eng@example.com",
        "name": "Eng",
        "last_name": "Tester",
        "preferences": {"k": "v"},
        "is_active": False,
    }

    u2 = UserModel.model_validate(data_en2)
    assert u2.email == "eng@example.com"
    assert u2.name == "Eng"
    assert u2.last_name == "Tester"
    assert u2.preferences.get("k") == "v"
    assert u2.is_active is False


def test_process_model_accepts_aliases_and_defaults():
    data_en = {
        "process_name": "Mi proceso",
        "user_email": "owner@example.com",
        "user_input": "do something",
        "steps": [],
        "total_steps": 0,
    }

    p = ProcessModel.model_validate(data_en)
    assert p.process_name == "Mi proceso"
    assert p.user_email == "owner@example.com"
    assert isinstance(p.created_at, datetime)


def test_process_temp_model_requires_expires_at():
    data_en = {
        "process_name": "Temp proc",
        "user_email": "owner2@example.com",
        "user_input": "temp",
        "steps": [],
        "expires_at": datetime.now(timezone.utc).isoformat(),
    }

    pt = ProcessTempModel.model_validate(data_en)
    assert pt.process_name == "Temp proc"
    assert pt.expires_at is not None
