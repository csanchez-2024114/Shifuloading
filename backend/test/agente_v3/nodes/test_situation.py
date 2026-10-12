"""situation: el modo 'brief' describe hechos de la situacion, no ordena como hablar."""
from app.agent.shared.helpers import situation as st
from app.agent.shared.helpers.identity_loader import _build_static_block


def test_pause_facts_state_what_is_blocked_without_prescribing_the_reply():
    reports = [{"source": "auth", "app": "gmail", "status": "error", "reason": "not_connected"},
               {"source": "catalog", "app": "gmail", "status": "ok"}]
    out = st.pause_facts(reports, ["fecha"])
    assert "Gmail is not connected" in out and "'Connect Gmail' button" in out and "fecha" in out
    assert "sentences" not in out and "Tell the user" not in out   # nada de topes ni ordenes de redaccion


def test_pause_facts_cover_unavailable_apps_and_account_choice():
    out = st.pause_facts([
        {"source": "catalog", "app": "shopify", "status": "error", "message": "not in catalog"},
        {"source": "auth", "app": "asana", "status": "pending_selection", "accounts": [{"email": "a@x.com"}, {"email": "b@x.com"}]},
    ])
    assert "Shopify is not integrated yet" in out and "may be possible later" in out and "a@x.com, b@x.com" in out


def test_pause_facts_is_empty_when_nothing_is_blocked():
    assert st.pause_facts([{"source": "auth", "app": "gmail", "status": "ok"}]) == ""


def test_mood_fact_reports_observation_only_when_not_neutral():
    assert "frustrated" in st.mood_fact("DIRECT_EMPATHY", "urgent") and "urgent" in st.mood_fact("DIRECT_EMPATHY", "urgent")
    assert st.mood_fact("CLOSING", None) == "The user is saying goodbye."
    assert st.mood_fact("HELPFUL", "calm") is None and st.mood_fact("DEFAULT", None) is None


def test_flow_fact_hands_over_the_step_instead_of_a_script_to_repeat():
    out = st.flow_fact("¿Cuál es el proceso?")
    assert "¿Cuál es el proceso?" in out and "own voice" in out
    assert "ONLY task" not in out and "Do NOT modify" not in out


def test_default_style_rules_in_code_are_skipped_in_brief_mode_unless_the_document_defines_them():
    assert "Communication Style" in _build_static_block({}, {})                                  # modo por defecto: igual que antes
    assert "Communication Style" not in _build_static_block({}, {"prompt_mode": "brief"})
    assert "Communication Style" in _build_static_block({}, {"prompt_mode": "brief", "communication_style": {"use_emojis": True}})


_SHOPIFY = [{"source": "auth", "app": "shopify", "status": "error", "reason": "not_connected"},
            {"source": "catalog", "app": "shopify", "status": "error", "reason": "not_found"}]


def test_an_app_the_catalog_does_not_have_is_never_reported_as_connectable():
    # paso en la evaluacion: el agente decia "ya tienes el boton Conectar Shopify" y la UI no mostraba ninguno
    out = st.pause_facts(_SHOPIFY)
    assert "Shopify is not integrated yet" in out and "may be possible later" in out and "Connect Shopify" not in out


def test_directive_mode_pause_text_agrees_with_the_ui_buttons_too():
    from app.agent.shared.nodes.responder import _build_error_context
    out = _build_error_context(_SHOPIFY, [])
    assert "APP NOT INTEGRATED YET: 'shopify'" in out and "NOT CONNECTED" not in out
    gmail = _build_error_context([{"source": "auth", "app": "gmail", "status": "error", "reason": "not_connected"}], [])
    assert "NOT CONNECTED: 'gmail'" in gmail   # lo normal sigue igual


def test_commitment_text_only_applies_to_apps_the_user_can_actually_connect():
    gmail = [{"source": "auth", "app": "gmail", "status": "error", "reason": "not_connected"}]
    assert st.has_connectable_block(gmail) is True
    assert st.has_connectable_block(_SHOPIFY) is False        # app inexistente: no se promete "lo hare cuando conectes"
    assert st.has_connectable_block(_SHOPIFY + gmail) is True  # si ademas hay una conectable, sigue aplicando
    assert st.has_connectable_block([{"source": "auth", "app": "gmail", "status": "ok"}]) is False
