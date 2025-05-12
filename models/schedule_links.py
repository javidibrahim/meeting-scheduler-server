from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import date, datetime
import json

class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)

class ScheduleLink(BaseModel):
    slug: str = Field(..., min_length=3, max_length=50)
    meetingLength: int = Field(..., gt=0)
    maxUses: Optional[int] = Field(None, gt=0)
    expirationDate: Optional[date] = None
    maxDaysInAdvance: int = Field(30, gt=0)
    customQuestions: List[str] = []

    @validator('slug')
    def validate_slug(cls, v):
        # Allow only letters, numbers, hyphens, and underscores
        import re
        if not re.match(r'^[a-zA-Z0-9\-_]+$', v):
            raise ValueError('Slug must contain only letters, numbers, hyphens and underscores')
        return v.lower()  # Convert to lowercase for consistency
    
    @validator('expirationDate')
    def convert_expiration_date(cls, v):
        # Convert string date to datetime.date if needed
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v).date()
            except ValueError:
                raise ValueError('Invalid date format, use YYYY-MM-DD')
        return v
    
    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat()
        }

class ScheduleLinkRequest(BaseModel):
    links: List[ScheduleLink]

class ScheduleLinkResponse(BaseModel):
    _id: str
    slug: str
    meetingLength: int
    maxUses: Optional[int] = None
    expirationDate: Optional[date] = None
    maxDaysInAdvance: int
    customQuestions: List[str]
    userId: str
    createdAt: datetime
    updatedAt: datetime
    uses: int = 0
    
    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat()
        } 