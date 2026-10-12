"""Saludo: el codigo dice que NO hay nada que reportar, para que el modelo no invente avisos ni compromisos a un usuario nuevo."""
from app.agent.shared.helpers.identity_loader import build_system_messages

RULE = {"greeting_behavior": {"first_message": "If 'Notices the user has NOT seen yet' lists something, tell it."}}


def _turn(user_memory=None, is_greeting=True):
    msgs = build_system_messages({}, RULE, is_first_turn=True, requirement_level=None, is_closing=False,
                                 is_greeting=is_greeting, user_memory=user_memory)
    return next((str(m.content) for m in msgs if str(m.content).startswith("## This Turn")), "")


def test_user_with_nothing_to_report_gets_the_fact():
    for memory in (None, "Facts the user told you: role: contador"):
        assert "NO unseen notices, NO commitments with a date and NO earlier conversations" in _turn(memory)


def test_any_existing_list_leaves_the_greeting_rule_untouched():
    # negar una parte hacia que el modelo callara tambien lo que si existia (memoria_entre_conversaciones)
    for memory in ("Commitments with a date:\n- nomina — 2026-10-16", "Earlier conversations, oldest first:\n1. c",
                   "Notices the user has NOT seen yet (x):\n- a"):
        assert "FACT" not in _turn(memory)


def test_no_greeting_rule_no_fact():
    assert _turn(is_greeting=False) == ""
