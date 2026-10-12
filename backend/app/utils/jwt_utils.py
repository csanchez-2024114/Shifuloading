"""
JWT Identity Service V2 - FastAPI compatible utilities.
"""
import jwt
import logging
import os
from typing import Dict, Any, Optional, Tuple
from fastapi import Request
from pydantic import BaseModel, EmailStr, ValidationError
logger = logging.getLogger('shifu.security.jwt')

class JWTPayload(BaseModel):
    user_id: str
    email: EmailStr
    exp: int
    iat: Optional[int] = None
    role: Optional[str] = 'user'

class JWTIdentityService:
    """Servicio centralizado para parseo y validación de JWT."""

    @staticmethod
    def _get_secret_key(request: Optional[Request]=None) -> str:
        if request and getattr(request, 'app', None):
            app_secret = getattr(request.app.state, 'secret_key', None)
            if app_secret:
                return app_secret
        return os.environ.get('SECRET_KEY', 'dev-secret-keep-it-hidden')

    @classmethod
    def decode_token(cls, token: str, request: Optional[Request]=None) -> Tuple[Optional[JWTPayload], Optional[Dict[str, Any]]]:
        try:
            raw_payload = jwt.decode(token, cls._get_secret_key(request), algorithms=['HS256'])
            validated_data = JWTPayload(**raw_payload)
            return (validated_data, None)
        except jwt.ExpiredSignatureError:
            logger.warning('Intento de acceso con token expirado.')
            return (None, {'error': 'token_expired', 'message': 'La sesión ha expirado', 'status': 401})
        except (jwt.InvalidTokenError, ValidationError) as exc:
            logger.error('Error de validación de token: %s', exc)
            return (None, {'error': 'invalid_token', 'message': 'Token de seguridad no válido', 'status': 401})
        except Exception as exc:
            logger.critical('Error crítico en auth JWT: %s', exc)
            return (None, {'error': 'internal_auth_error', 'message': 'Error interno de autenticación', 'status': 500})

    @classmethod
    def get_payload_from_request(cls, request: Optional[Request]=None, authorization_header: Optional[str]=None, query_token: Optional[str]=None) -> Tuple[Optional[JWTPayload], Optional[Tuple[Dict[str, Any], int]]]:
        auth_header = authorization_header or ''
        if request is not None and (not auth_header):
            auth_header = request.headers.get('Authorization', '')
        token = None
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()
        if not token:
            token = query_token
        if not token and request is not None:
            token = request.query_params.get('token')
        if not token:
            return (None, ({'error': 'unauthorized', 'message': 'Se requiere token de acceso'}, 401))
        payload, error = cls.decode_token(token, request=request)
        if error:
            return (None, (error, error.get('status', 401)))
        return (payload, None)

def get_jwt_payload(app=None, request: Optional[Request]=None, authorization_header: Optional[str]=None, query_token: Optional[str]=None):
    """Wrapper de compatibilidad para código legacy."""
    payload, error = JWTIdentityService.get_payload_from_request(request=request, authorization_header=authorization_header, query_token=query_token)
    if error:
        return (None, error)
    return (payload.model_dump(), None)

def validate_email_match(payload: Dict, body_data: Dict) -> Tuple[Optional[str], Optional[Tuple[Dict[str, Any], int]]]:
    token_email = payload.get('email')
    body_email = body_data.get('email')
    if token_email and body_email and (token_email.lower() != body_email.lower()):
        logger.warning('POSIBLE ATAQUE IDOR: token_email=%s body_email=%s', token_email, body_email)
        return (None, ({'error': 'forbidden', 'message': 'No tienes permisos para realizar acciones sobre este correo.'}, 403))
    return (token_email or body_email, None)
