from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class ScheduledEventAnswer(BaseModel):
    question: str
    answer: str

class ScheduledEventEnrichment(BaseModel):
    linkedin_summary: Optional[str] = None
    augmented_note: Optional[str] = None
    enriched_at: Optional[datetime] = None

class ScheduledEvent(BaseModel):
    scheduling_link_id: str
    email: str
    scheduled_for: str  # ISO format datetime string
    duration_minutes: int = 30
    linkedin: Optional[str] = None
    answers: List[ScheduledEventAnswer] = []
    enrichment: Optional[ScheduledEventEnrichment] = None
    created_at: Optional[datetime] = None

class ScheduledEventResponse(BaseModel):
    id: str
    scheduling_link_id: str
    user_id: str
    scheduled_for: str
    duration_minutes: int
    email: str
    linkedin: str
    answers: List[ScheduledEventAnswer]
    created_at: datetime
    enrichment: Optional[ScheduledEventEnrichment] = None 