"""Blog Routes V2 - FastAPI native implementation."""
from datetime import datetime, timezone
from typing import List
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter(tags=['Blog'])

class CreatePostPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    content: str = Field(..., min_length=1)
    author: str = Field(default='Shifu AI', min_length=1, max_length=120)
    tags: List[str] = Field(default_factory=list)
    status: str = Field(default='draft')

def _serialize_post(post):
    post['_id'] = str(post['_id'])
    for field in ('created_at', 'updated_at'):
        if isinstance(post.get(field), datetime):
            post[field] = post[field].isoformat()
    return post

@router.get('/posts')
async def get_all_posts(request: Request):
    db = request.app.state.db
    try:
        cursor = db.posts.find({'status': 'published'}).sort('created_at', -1)
        posts = [_serialize_post(post) async for post in cursor]
        return {'success': True, 'count': len(posts), 'data': posts}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

@router.post('/posts', status_code=status.HTTP_201_CREATED)
async def create_post(payload: CreatePostPayload, request: Request):
    db = request.app.state.db
    now = datetime.now(timezone.utc)
    doc = {'title': payload.title, 'content': payload.content, 'author': payload.author, 'tags': payload.tags, 'status': payload.status, 'created_at': now, 'updated_at': now}
    try:
        result = await db.posts.insert_one(doc)
        return {'success': True, 'message': 'Artículo creado con éxito', 'post_id': str(result.inserted_id)}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc