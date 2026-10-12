"""
OAuth Base Flow (JWT-only, Stateless) — FastAPI Version
"""
import os
import jwt
import secrets
import requests
from typing import Optional, List, Dict
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode, quote
from config import Config
JWT_SECRET = Config.SECRET_KEY
JWT_ALGO = 'HS256'

def token_required(request: Request) -> str:
    token = request.query_params.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        raise HTTPException(status_code=401, detail='Missing token')
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        user_id = payload.get('user_id')
        if not user_id:
            raise HTTPException(status_code=401, detail='Invalid token payload')
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid token')

def generate_state() -> str:
    return secrets.token_urlsafe(32)

def validate_state(front_state: str, back_state: str) -> bool:
    return bool(front_state and back_state and (front_state == back_state))

def oauth_login_base(auth_url: str, client_id: str, redirect_uri: str, scope: Optional[List[str]]=None, state: Optional[str]=None, extra_params: Optional[Dict]=None, scopes: Optional[List[str]]=None):
    """
    Construye la URL de autorización OAuth y redirige.
    Compatible con `scope` o `scopes`.
    """
    scope_list = scopes if scopes is not None else scope or []
    scope_str = ' '.join(scope_list) if scope_list else ''
    params = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': redirect_uri, 'scope': scope_str, 'state': state or ''}
    if extra_params:
        params.update(extra_params)
    params_no_scope = {k: v for k, v in params.items() if k != 'scope'}
    query = urlencode(params_no_scope, doseq=True)
    scope_encoded = quote(scope_str, safe='') if scope_str else ''
    if scope_encoded:
        query = f'{query}&scope={scope_encoded}' if query else f'scope={scope_encoded}'
    return RedirectResponse(f'{auth_url}?{query}')

def oauth_callback_base(token_url: str, client_id: str, client_secret: str, redirect_uri: str, code: str, extra_data: Optional[Dict]=None):
    data = {'grant_type': 'authorization_code', 'code': code, 'client_id': client_id, 'client_secret': client_secret, 'redirect_uri': redirect_uri}
    if extra_data:
        data.update(extra_data)
    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return (None, response.text)
    return (response.json(), None)
