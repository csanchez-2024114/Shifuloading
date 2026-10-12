"""
WhatsApp Business API — Webhook y Mensajería
Maneja verificación de webhook y recepción de mensajes entrantes.
"""
import os
import logging
import hmac
import hashlib
import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
logger = logging.getLogger('whatsapp.webhook')
router = APIRouter()
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN')
WHATSAPP_APP_SECRET = os.getenv('WHATSAPP_APP_SECRET')
WHATSAPP_PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
WHATSAPP_ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')

async def send_whatsapp_text(to_number: str, message_body: str):
    url = f'https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_NUMBER_ID}/messages'
    headers = {'Authorization': f'Bearer {WHATSAPP_ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    payload = {'messaging_product': 'whatsapp', 'to': to_number, 'type': 'text', 'text': {'body': message_body}}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f' Mensaje enviado exitosamente a {to_number}')
        except httpx.HTTPStatusError as e:
            logger.error(f'Error de Meta al enviar mensaje: {e.response.text}')
        except Exception as e:
            logger.error(f'Error de conexión al enviar mensaje: {e}')

@router.get('/webhook')
async def verify_webhook(request: Request):
    mode = request.query_params.get('hub.mode')
    token = request.query_params.get('hub.verify_token')
    challenge = request.query_params.get('hub.challenge')
    if not mode or not token:
        raise HTTPException(status_code=400, detail='Faltan parámetros de verificación')
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logger.info('Handshake exitoso con Meta WhatsApp')
        return PlainTextResponse(content=challenge, status_code=200)
    logger.warning('Verify Token incorrecto en handshake de WhatsApp')
    raise HTTPException(status_code=403, detail='Verify token mismatch')

@router.post('/webhook')
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Recibe mensajes entrantes de WhatsApp.
    """
    signature = request.headers.get('X-Hub-Signature-256', '')
    body = await request.body()
    if WHATSAPP_APP_SECRET:
        expected = 'sha256=' + hmac.new(WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning('Firma inválida en webhook de WhatsApp')
            raise HTTPException(status_code=403, detail='Invalid signature')
    payload = await request.json()
    try:
        entry = payload.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        messages = value.get('messages', [])
        if messages:
            message = messages[0]
            from_number = message.get('from')
            message_type = message.get('type')
            if message_type == 'text':
                text = message.get('text', {}).get('body', '')
                logger.info(f'Mensaje de {from_number}: {text}')
                respuesta = f"Hola, soy Shifu. Recibí tu mensaje: '{text}'. ¡Gracias por contactarnos!"
                background_tasks.add_task(send_whatsapp_text, from_number, respuesta)
    except Exception as e:
        logger.error(f'Error procesando mensaje WhatsApp: {e}', exc_info=True)
    return JSONResponse({'status': 'ok'}, status_code=200)


# ── Service Layer ──────────────────────────────────────────────────────────────


