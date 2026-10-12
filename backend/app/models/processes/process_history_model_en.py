"""
Process History Models (English)
Strict DTO contracts for persistence and serialization of visual flows (Spider) from the Frontend.
"""
from typing import List, Optional, Any
from datetime import datetime, timezone
from app.models._base import AppBaseModel
from pydantic import Field

class ProcessSubStepEN(AppBaseModel):
    id: str = Field(..., description='Unique substep ID generated in frontend or backend')
    app_id: Optional[str] = Field(default=None, description="App/integration identifier (e.g. '1000-1')")
    title: str = Field(..., description='Human-readable substep title')
    description: Optional[str] = Field(default='', description='Technical or detailed description')
    image: Optional[str] = Field(default=None, description="URL or path to the tool's icon")
    status: str = Field(default='pending', description="Status: 'pending', 'completed', 'error', etc.")
    details: Optional[List[str]] = Field(default_factory=list, description='List of technical execution details')

class ProcessStepEN(AppBaseModel):
    id: str = Field(..., description='Unique step ID')
    app_id: Optional[str] = Field(default=None, description="App/integration identifier (e.g. '1000')")
    title: str = Field(..., description="Human-readable step title (e.g. 'User Request')")
    description: Optional[str] = Field(default='', description='Description of what the step does')
    image: Optional[str] = Field(default=None, description='URL or path to the icon')
    status: str = Field(default='pending', description='Step status')
    details: Optional[List[str]] = Field(default_factory=list, description='Main step details')
    sub_steps: Optional[List[ProcessSubStepEN]] = Field(default_factory=list, description='List of nested sub-steps')

class ProcessHistoryCreateEN(AppBaseModel):
    """Expected payload when creating a new record from the Frontend or LangGraph Engine."""
    session_id: str = Field(..., description='Chat session or context ID')
    title: str = Field(..., description='General process title')
    description: Optional[str] = Field(default='', description='Process objective description')
    status: str = Field(default='running', description='General process status')
    details: Optional[List[str]] = Field(default_factory=list)
    steps: Optional[List[ProcessStepEN]] = Field(default_factory=list)

class ProcessHistoryUpdateEN(AppBaseModel):
    """Expected payload for partial updates."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    details: Optional[List[str]] = None
    steps: Optional[List[ProcessStepEN]] = None

class ProcessHistoryResponseEN(AppBaseModel):
    """Exact contract consumed by the Frontend."""
    id: str = Field(..., description='Mongo ObjectId as String')
    user_id: str = Field(..., description="Owner's ID")
    session_id: str
    title: str
    description: str
    status: str
    details: List[str]
    steps: List[ProcessStepEN]
    created_at: datetime
    updated_at: datetime
