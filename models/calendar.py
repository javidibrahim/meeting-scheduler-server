from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Event(BaseModel):
    id: str = Field(..., description="Event ID from Google Calendar")
    calendar_id: str = Field(..., description="ID of the calendar this event belongs to")
    summary: str = Field(..., description="Event title/summary")
    description: Optional[str] = Field(None, description="Event description")
    start_time: datetime = Field(..., description="Event start time")
    end_time: datetime = Field(..., description="Event end time")
    location: Optional[str] = Field(None, description="Event location")
    status: str = Field(..., description="Event status (confirmed, tentative, cancelled)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Calendar(BaseModel):
    id: str = Field(..., description="Calendar ID from Google")
    name: str = Field(..., description="Calendar name")
    email: str = Field(..., description="Calendar owner's email")
    user_email: str = Field(..., description="User who connected this calendar")
    events_count: int = Field(default=0, description="Number of events in the calendar")
    access_role: str = Field(..., description="User's role for this calendar (owner, writer, reader)")
    is_read_only: bool = Field(..., description="Whether the calendar is read-only")
    access_token: str = Field(..., description="Google OAuth access token")
    refresh_token: Optional[str] = Field(None, description="Google OAuth refresh token")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)