from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import base64
from urllib.parse import urlencode
router = APIRouter()

class OAuthRequest(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    code: str | None = None
    redirect_uri: str | None = None
    grant_type: str = 'authorization_code'
    refresh_token: str | None = None
    code_verifier: str | None = None

async def post_form_token(url: str, payload: dict, headers=None):
    headers = headers or {'Content-Type': 'application/x-www-form-urlencoded'}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=urlencode(payload), headers=headers)
        return (resp.status_code, resp.json())

@router.post('/clickup')
async def clickup_proxy(data: OAuthRequest):
    if not all([data.client_id, data.client_secret, data.code, data.redirect_uri]):
        raise HTTPException(400, 'Missing required fields')
    status, res = await post_form_token('https://api.clickup.com/api/v2/oauth/token', {'client_id': data.client_id, 'client_secret': data.client_secret, 'code': data.code, 'redirect_uri': data.redirect_uri})
    return res if status == 200 else {'error': 'ClickUp error', 'details': res}

@router.post('/dropbox')
async def dropbox_proxy(data: OAuthRequest):
    if not all([data.client_id, data.client_secret, data.code, data.redirect_uri]):
        raise HTTPException(400, 'Missing required fields')
    status, res = await post_form_token('https://api.dropbox.com/oauth2/token', {'code': data.code, 'grant_type': 'authorization_code', 'client_id': data.client_id, 'client_secret': data.client_secret, 'redirect_uri': data.redirect_uri})
    return res

@router.post('/notion')
async def notion_proxy(data: OAuthRequest):
    creds = base64.b64encode(f'{data.client_id}:{data.client_secret}'.encode()).decode()
    status, res = await post_form_token('https://api.notion.com/v1/oauth/token', {'grant_type': 'authorization_code', 'code': data.code, 'redirect_uri': data.redirect_uri}, headers={'Authorization': f'Basic {creds}', 'Notion-Version': '2022-06-28', 'Content-Type': 'application/x-www-form-urlencoded'})
    return res

@router.post('/hubspot')
async def hubspot_proxy(data: OAuthRequest):
    status, res = await post_form_token('https://api.hubapi.com/oauth/v1/token', {'grant_type': 'authorization_code', 'client_id': data.client_id, 'client_secret': data.client_secret, 'redirect_uri': data.redirect_uri, 'code': data.code})
    return res

@router.post('/facebook')
@router.post('/whatsapp')
async def facebook_proxy(data: OAuthRequest):
    payload = {'client_id': data.client_id, 'client_secret': data.client_secret, 'redirect_uri': data.redirect_uri, 'grant_type': data.grant_type}
    if data.grant_type == 'authorization_code':
        payload['code'] = data.code
    else:
        payload['fb_exchange_token'] = data.refresh_token
    status, res = await post_form_token('https://graph.facebook.com/v20.0/oauth/access_token', payload)
    return res

@router.post('/instagram')
async def instagram_proxy(data: OAuthRequest):
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    status, res = await post_form_token('https://api.instagram.com/oauth/access_token', {'client_id': data.client_id, 'client_secret': data.client_secret, 'redirect_uri': data.redirect_uri, 'grant_type': 'authorization_code', 'code': data.code}, headers)
    short_token = res.get('access_token')
    if not short_token:
        return {'error': 'Instagram step1 failed', 'details': res}
    status, res2 = await post_form_token('https://graph.instagram.com/access_token', {'grant_type': 'ig_exchange_token', 'client_secret': data.client_secret, 'access_token': short_token}, headers)
    return res2 if status == 200 else res
