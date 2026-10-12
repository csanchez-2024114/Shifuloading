"""
situation — modo "resumen de situación" (agent_personality.prompt_mode == "brief").

En el modo por defecto el responder recibe DIRECTIVAS apiladas ("TONE DIRECTIVE", "EFFORT DIRECTIVE", "ANTI-LOOPING RULE",
"VALIDATION PAUSED... 1-2 sentences max", "Your ONLY task is to deliver..."). Cada fallo se parchaba añadiendo o quitando una,
y varias chocaban entre sí. En este modo el código solo describe la SITUACIÓN (hechos) y el modelo decide cómo hablar:
quién es el usuario, qué está bloqueado y por qué, qué ya se entendió. Las garantías duras siguen en el código.

Son funciones puras sobre el estado del turno: no leen Mongo ni llaman a ningún modelo.
"""


def drop_shadowed_auth_errors(reports: list[dict]) -> list[dict]:
    """Una app que el catalogo no tiene no puede estar "sin conectar": no existe boton ni forma de conectarla.
    Es la misma regla que ya aplica _build_ui_actions; el texto que lee el modelo debe coincidir con lo que la UI muestra
    (antes le decian a la vez "UNSUPPORTED APP" y "el boton ya esta en la interfaz", y el modelo inventaba el boton)."""
    from app.agent.shared.helpers.platform_context import app_has_actions
    unsupported = {str(r.get("app", "")).lower() for r in reports if r.get("source") == "catalog" and r.get("status") == "error"}
    # Tambien las apps con las que la plataforma no puede hacer nada: pedirle al usuario que conecte algo que no le sirve
    # es exponer un dato interno (y el texto decia "no puedo hacer nada con Notion" junto a un boton "Conectar Notion").
    # Un pedido explicito de conectar (add_account) se respeta.
    return [r for r in reports
            if not (r.get("source") == "auth" and r.get("status") == "error"
                    and (str(r.get("app", "")).lower() in unsupported or not app_has_actions(r.get("app_key") or r.get("app", ""))))]


def has_connectable_block(reports: list[dict]) -> bool:
    """True si hay una app que el usuario SI puede conectar y esta bloqueando el turno (cuenta sin conectar o por elegir).
    Los textos de compromiso del tipo "lo hare en cuanto conectes la cuenta" solo tienen sentido en ese caso: aplicarlos
    a una app que no existe en la plataforma hacia prometer algo imposible (paso con Shopify)."""
    return any(r.get("status") in ("error", "pending_selection", "add_account") and r.get("source") != "catalog"
               for r in drop_shadowed_auth_errors(reports))


def pause_facts(reports: list[dict], missing_vars: list[str] | None = None) -> str:
    """Por qué el turno no puede avanzar todavía, como hechos (sin ordenar cuántas frases ni qué decir)."""
    lines: list[str] = []
    for r in drop_shadowed_auth_errors(reports):
        app = str(r.get("app") or "").replace("_", " ").title()
        status, source = r.get("status"), r.get("source")
        if status == "error" and source == "auth":
            lines.append(f"{app} is not connected for this user. A 'Connect {app}' button is shown right under your reply.")
        elif status == "error" and source == "catalog":
            lines.append(f"{app} is not integrated yet — the team keeps adding new integrations, so it may be possible later (no dates, no guarantees); today it cannot be connected, used as a trigger or used for any action, so offer what works today.")
        elif status == "error":
            lines.append(f"{app}: {r.get('message') or r.get('reason') or 'there is a problem'}.")
        elif status == "pending_selection":
            emails = [a.get("email") or a.get("account_id", "?") for a in r.get("accounts", [])]
            lines.append(f"{app}: the user has several connected accounts ({', '.join(emails)}); one must be chosen to continue.")
        elif status == "add_account":
            lines.append(f"The user wants to connect {app}; its 'Connect {app}' button is shown right under your reply.")
    if missing_vars:
        lines.append(f"Parameters still missing for the request: {missing_vars}.")
    if not lines:
        return ""
    return "SITUATION — the request cannot move forward yet:\n" + "\n".join(f"- {line}" for line in lines)


def mood_fact(mood_state: str | None, sentiment: str | None) -> str | None:
    """Lo observado del usuario, no una orden de tono. Neutral/amable no necesita decirse."""
    if mood_state == "CLOSING":
        return "The user is saying goodbye."
    if mood_state == "DIRECT_EMPATHY":
        return f"Observed: the user seems frustrated or in a hurry (sentiment: {sentiment or 'frustrated'})."
    return None


def flow_facts(structured: str) -> str:
    """El flujo de crear workflows dejo HECHOS para este turno (que falta conectar, que app solo lee o aun no esta). El
    responder arma UNA respuesta: contesta lo que el usuario pregunto y dice lo que falta. El texto fijo ignoraba la
    pregunta del turno ("¿y las dudas de los clientes tambien se puede?" recibia solo "conecta Gmail")."""
    return (
        "AUTOMATION SETUP — FACTS FOR THIS TURN (checked by the system, they are true): the user is setting up an "
        "automation and it cannot be built yet for the reasons below. Write ONE reply that (1) answers whatever the user "
        "asked or said in their last message, using what you know about the platform, and (2) tells them what they need "
        "to do first, with every fact below. When the facts say an account is not connected, its Connect button is "
        "already on screen: point to it. Never ask for credentials. Do not say the automation is ready or active, do not contradict these facts, and do not invent "
        "other requirements.\n"
        f"«{structured}»"
    )


def flow_fact(structured: str) -> str:
    """El flujo guiado de automatización ya decidió qué sigue: se entrega como insumo, no como guion a repetir."""
    return (
        "The guided-automation flow reached this step. What its requirements assistant suggests saying next:\n"
        f"«{structured}»\n"
        "Say it in your own voice, using what you know about this user and the platform; "
        "do not ask for anything the user already told you."
    )
