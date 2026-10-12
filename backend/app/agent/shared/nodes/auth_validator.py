"""
auth_validator — agente_v3 validation layer

Checks that the user has an active OAuth token for each app in apps_involved.
Runs in parallel with catalog_checker and tavily_searcher.

Connection status handling (user_connected_accounts.status):
  "active"        → OK, usable
  "needs_refresh" → OK, usable (auto-refresh is transparent)
  "expired"       → Error: user must reconnect (no refresh token available)
  "revoked"       → Error: user must reauthorize (provider rejected the token)
  not in DB       → Error: never connected

Multi-account scenarios (per app, for usable accounts):
  A (0 usable)     : error — no usable account (not_connected / expired / revoked)
  B (1 usable)     : auto-select → writes to selected_accounts
  C (2+ usable)    : check selected_accounts
    - already chosen and valid → ok
    - not chosen yet           → pending_selection + writes to available_accounts

Writes to: validation_reports, selected_accounts, available_accounts, user_connected_apps.
"""

import logging
import os
from collections import defaultdict

from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.utils.app_resolver import resolve_app_key
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print
from app.agent.shared.utils.login_paths import LOGIN_PATHS as _LOGIN_PATHS
from app.core.constants import Collections, ConnectedAccountStatus
from app.core.mongo import mongo_manager

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("FRONTEND_URL", "https://hypershifu.com")


def _auth_url(app: str) -> str:
    path = _LOGIN_PATHS.get(app.lower())
    return path if path else f"{_BASE_URL}/settings/integrations?connect={app}"


def _dev_box_validate(
    reports: list,
    accounts_by_provider: dict,
    all_statuses_by_provider: dict,
) -> None:
    lines = []
    for r in reports:
        app    = r["app"]
        rstatus = r["status"]
        reason = r.get("reason", "")
        if rstatus == "ok":
            acct = r.get("account", {})
            lines.append(f"  ✓ {app:<14} status={all_statuses_by_provider.get(app.lower(), ['?'])[0]:<14}  → {acct.get('email') or '(auto)'}")
        elif rstatus == "pending_selection":
            emails = [a.get("email", "?") for a in r.get("accounts", [])]
            lines.append(f"  ⏳ {app:<14} status=active            → choose from: {emails}")
        else:
            raw_statuses = all_statuses_by_provider.get(app.lower(), [])
            status_disp  = raw_statuses[0] if raw_statuses else "not_found"
            lines.append(f"  ✗ {app:<14} status={status_disp:<14}  reason={reason}")
    dev_print(
        f"\n┌─ Auth Validator ───────────────────────────────────────────\n"
        + "".join(f"│{l}\n" for l in lines)
        + f"└────────────────────────────────────────────────────────────"
    )



async def auth_validator_node(state: ShifuState) -> dict:
    apps    = state.get("apps_involved") or []
    user_id = state.get("user_id") or ""
    mode    = state.get("catalog_query_mode") or ("validate" if apps else None)

    logger.info("[auth_validator] ▶ mode=%s  user=%s  apps_to_check=%s", mode, user_id or "?", apps)

    if not apps and mode != "list_connected":
        logger.info("[auth_validator] skip — no apps_involved and mode=%s", mode)
        return {"validation_reports": [], "user_connected_apps": None}

    if mode == "list_available":
        # Listing platform catalog — no per-user auth check needed.
        # apps_involved may be non-empty (user asked about a specific app)
        # but auth state is irrelevant here; catalog_checker answers this.
        logger.info("[auth_validator] skip — mode=list_available (no auth check needed)")
        return {"validation_reports": [], "user_connected_apps": None}

    if not user_id:
        logger.warning("[auth_validator] skip — no user_id in state")
        return {"validation_reports": [
            {"source": "auth", "app": a, "status": "error", "reason": "not_connected",
             "message": "User not authenticated"} for a in apps
        ], "user_connected_apps": None}

    db = mongo_manager.db
    if db is None:
        logger.error("[auth_validator] DB not available")
        return {"validation_reports": [
            {"source": "auth", "app": a, "status": "error", "reason": "not_connected",
             "message": "Auth DB unavailable"} for a in apps
        ], "user_connected_apps": None}

    # ── list_connected: return all providers + accounts for this user ────────
    if mode == "list_connected":
        provider_filter = {"provider": {"$in": [a.lower() for a in apps]}} if apps else {}
        all_cursor = db[Collections.USER_CONNECTED_ACCOUNTS].find(
            {"user_id": user_id, **provider_filter},
            {"provider": 1, "account_id": 1, "email": 1, "status": 1},
        )
        all_docs = await all_cursor.to_list(length=None)

        connected: dict[str, list[str]] = {}
        for doc in all_docs:
            provider = (doc.get("provider") or "").lower()
            if not provider:
                continue
            status     = doc.get("status") or ConnectedAccountStatus.ACTIVE
            email      = doc.get("email") or ""
            account_id = str(doc.get("account_id") or "")
            identifier = email or account_id
            if not identifier:
                continue
            if status not in ConnectedAccountStatus.USABLE:
                identifier = f"{identifier} (expirada — reconectar)"
            connected.setdefault(provider, [])
            if identifier not in connected[provider]:
                connected[provider].append(identifier)

        connected = {p: sorted(accts) for p, accts in sorted(connected.items())}

        # Emit connect-needed reports for requested providers that aren't connected
        missing_reports = []
        if apps:
            for app in apps:
                if app.lower() not in connected:
                    missing_reports.append({
                        "source":     "auth",
                        "app":        app,
                        "status":     "error",
                        "reason":     "not_connected",
                        "needs_auth": True,
                        "auth_url":   _auth_url(app),
                        "message":    f"'{app}' is not connected.",
                    })

        logger.info("[auth_validator] ◀ list_connected — %d providers  filter=%s  missing=%d",
                    len(connected), list(apps) if apps else "all", len(missing_reports))
        if DEV_MODE:
            dev_print(
                f"\n┌─ Auth Validator ───────────────────────────────────────────\n"
                f"│  mode     : list_connected\n"
                f"│  accounts : {connected}\n"
                f"│  missing  : {[r['app'] for r in missing_reports]}\n"
                f"└────────────────────────────────────────────────────────────"
            )

        return {
            "validation_reports":  missing_reports,
            "user_connected_apps": connected if connected else None,
            "selected_accounts":   None,
            "available_accounts":  None,
        }

    # ── add_account: user wants to connect an additional account ─────────────
    if mode == "add_account":
        reports = []
        for app in apps:
            app_key = await resolve_app_key(app.lower())
            reports.append({
                "source":     "auth",
                "app":        app,
                "app_key":    app_key,
                "status":     "add_account",  # NOT "error" — _aggregate() ignores this
                "needs_auth": True,
                "auth_url":   _auth_url(app_key),
                "message":    f"Add another '{app}' account.",
            })
        logger.info("[auth_validator] ◀ add_account — apps=%s", apps)
        if DEV_MODE:
            dev_print(
                f"\n┌─ Auth Validator ───────────────────────────────────────────\n"
                f"│  mode        : add_account\n"
                f"│  apps        : {apps}\n"
                f"│  auth_urls   : {[_auth_url(a) for a in apps]}\n"
                f"└────────────────────────────────────────────────────────────"
            )
        return {
            "validation_reports": reports,
            "user_connected_apps": None,
            "selected_accounts":   None,
            "available_accounts":  None,
        }

    # ── validate: check specific apps_involved ────────────────────────────────
    # Load ALL accounts for this user (no status filter — need full picture)
    cursor = db[Collections.USER_CONNECTED_ACCOUNTS].find(
        {"user_id": user_id},
        {"provider": 1, "account_id": 1, "email": 1, "status": 1},
    )
    docs = await cursor.to_list(length=None)

    # accounts_by_provider: only USABLE accounts (for scenario B/C selection logic)
    accounts_by_provider: dict[str, list] = defaultdict(list)
    # all_statuses_by_provider: all statuses per provider (for error reason detection)
    all_statuses_by_provider: dict[str, list] = defaultdict(list)

    for doc in docs:
        provider   = (doc.get("provider") or "").lower()
        doc_status = (doc.get("status") or ConnectedAccountStatus.ACTIVE)
        if not provider:
            continue
        all_statuses_by_provider[provider].append(doc_status)
        if doc_status in ConnectedAccountStatus.USABLE:
            accounts_by_provider[provider].append({
                "account_id": str(doc.get("account_id") or doc.get("_id") or ""),
                "email":      doc.get("email") or "",
            })

    logger.info("[auth_validator] providers found: %s",
                {p: len(v) for p, v in accounts_by_provider.items()})

    existing_selected      = dict(state.get("selected_accounts") or {})
    selected_accounts_out  = dict(existing_selected)
    available_accounts_out = dict(state.get("available_accounts") or {})

    reports: list[dict] = []

    for app in apps:
        app_key      = await resolve_app_key(app.lower())
        app_accounts = accounts_by_provider.get(app_key, [])      # USABLE only
        all_statuses = all_statuses_by_provider.get(app_key, [])  # all statuses

        if not app_accounts and not all_statuses:
            # ── Scenario A: never connected ────────────────────────────────────
            reports.append({
                "source": "auth", "app": app, "status": "error",
                "reason": "not_connected",
                "needs_auth": True, "auth_url": _auth_url(app_key), "app_key": app_key,
                "message": f"'{app}' is not connected. Please authorize it first.",
            })
            logger.info("[auth_validator] %s → not_connected", app)

        elif not app_accounts:
            # ── Scenario A variant: account exists but unusable ────────────────
            if ConnectedAccountStatus.REVOKED in all_statuses:
                reason  = "revoked"
                message = f"Access to '{app}' was revoked. Please authorize it again."
            else:
                reason  = "expired"
                message = f"Your '{app}' connection has expired. Please reconnect it."
            reports.append({
                "source": "auth", "app": app, "status": "error",
                "reason": reason,
                "needs_auth": True, "auth_url": _auth_url(app_key), "app_key": app_key,
                "message": message,
            })
            logger.info("[auth_validator] %s → %s", app, reason)

        elif len(app_accounts) == 1:
            # ── Scenario B: exactly one usable account — auto-select ───────────
            account    = app_accounts[0]
            identifier = account["email"] or account["account_id"]
            selected_accounts_out[app_key] = identifier
            available_accounts_out.pop(app_key, None)
            reports.append({
                "source": "auth", "app": app, "status": "ok",
                "account": account,
            })
            logger.info("[auth_validator] %s → B (auto-selected: %s)", app, identifier)

        else:
            # ── Scenario C: multiple usable accounts ───────────────────────────
            if app_key in existing_selected:
                chosen = existing_selected[app_key]
                valid  = any(
                    a["email"] == chosen or a["account_id"] == chosen
                    for a in app_accounts
                )
                if valid:
                    available_accounts_out.pop(app_key, None)
                    reports.append({
                        "source": "auth", "app": app, "status": "ok",
                        "account": {"email": chosen},
                    })
                    logger.info("[auth_validator] %s → C resolved (chosen: %s)", app, chosen)
                else:
                    available_accounts_out[app_key] = app_accounts
                    reports.append({
                        "source": "auth", "app": app, "status": "pending_selection",
                        "accounts": app_accounts,
                        "message": f"Previously selected '{app}' account is no longer available.",
                    })
                    logger.info("[auth_validator] %s → C re-pending (stale selection)", app)
            else:
                available_accounts_out[app_key] = app_accounts
                reports.append({
                    "source": "auth", "app": app, "status": "pending_selection",
                    "accounts": app_accounts,
                    "message": f"'{app}' has {len(app_accounts)} accounts connected.",
                })
                logger.info("[auth_validator] %s → C pending (%d accounts)",
                            app, len(app_accounts))

    ok_count      = sum(1 for r in reports if r["status"] == "ok")
    err_count     = sum(1 for r in reports if r["status"] == "error")
    pending_count = sum(1 for r in reports if r["status"] == "pending_selection")
    logger.info("[auth_validator] ◀ ✓ %d ok  ✗ %d error  ⏳ %d pending",
                ok_count, err_count, pending_count)

    if DEV_MODE:
        _dev_box_validate(reports, accounts_by_provider, all_statuses_by_provider)

    return {
        "validation_reports":  reports,
        "selected_accounts":   selected_accounts_out,
        "available_accounts":  available_accounts_out or None,
        "user_connected_apps": None,
    }

