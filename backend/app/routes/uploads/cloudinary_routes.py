"""Cloudinary API Routes V2 - FastAPI native implementation."""
from typing import Optional
from urllib.parse import unquote
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from app.database import get_current_user
from app.services.cloudinary_service import cloudinary_service

router = APIRouter(tags=['Uploads'])
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv', 'txt', 'json', 'xml', 'pptx', 'ppt', 'odp', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'mp4', 'mov', 'avi', 'webm', 'zip', 'rar', 'md', 'rtf'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@router.post('/', status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile = File(...), folder: str = Form(default='shifu_v2_uploads'), user = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Nombre de archivo vacío')
    if not allowed_file(file.filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Extensión no permitida para análisis')
    user_email = user.get('correo') or user.get('email') or 'anonymous_ai'
    try:
        uploaded = cloudinary_service.upload_file(file=file.file, folder=folder, user_email=user_email)
        return {'success': True, 'data': uploaded.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

@router.delete('/{public_id:path}')
async def delete_file(public_id: str, user = Depends(get_current_user)):
    clean_id = unquote(public_id)
    try:
        deleted = cloudinary_service.delete_resources([clean_id])
        if not deleted:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='No se pudo eliminar el recurso')
        return {'success': True, 'public_id': clean_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

@router.get('/')
async def list_files(folder: str = 'shifu_v2_uploads', next_cursor: Optional[str] = None, user = Depends(get_current_user)):
    user_email = user.get('correo') or user.get('email')
    if not user_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Usuario sin email asociado')
    try:
        inventory = cloudinary_service.get_user_inventory(user_email=user_email, next_cursor=next_cursor)
        return {'success': True, 'folder': folder, 'data': inventory}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc