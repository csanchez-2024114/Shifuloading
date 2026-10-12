"""
OnlyFans Integration
Manual Authorization Flow (No official OAuth)
FastAPI Version
"""
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
router = APIRouter()

@router.get('/login')
async def onlyfans_login():
    """
    Redirects the user to the official OnlyFans website.
    This is NOT OAuth, just a manual redirect.
    """
    return RedirectResponse(url='https://onlyfans.com/', status_code=307)
