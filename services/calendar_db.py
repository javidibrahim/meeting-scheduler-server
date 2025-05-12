from typing import List, Optional
from datetime import datetime
from models.calendar import Calendar
from db.mongo import db
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

class CalendarDBService:
    def __init__(self):
        self.collection = db["calendars"]

    async def save_calendar(self, calendar: Calendar) -> Calendar:
        """Save or update a calendar"""
        try:
            await self.collection.update_one(
                {"id": calendar.id, "user_email": calendar.user_email},
                {"$set": calendar.dict()},
                upsert=True
            )
            logger.info(f"Saved calendar {calendar.name} for user {calendar.user_email}")
            return calendar
        except Exception as e:
            logger.error(f"Error saving calendar: {str(e)}")
            raise

    async def save_calendars(self, user_email: str, calendars: List[dict]) -> List[Calendar]:
        """Save or update multiple calendars for a user"""
        try:
            calendar_models = [
                Calendar(
                    id=cal['id'],
                    name=cal['name'],
                    email=cal['email'],
                    user_email=user_email,
                    events_count=cal.get('eventsCount', 0),
                    access_role=cal['accessRole'],
                    is_read_only=cal.get('isReadOnly', False),
                    access_token=cal['accessToken'],
                    refresh_token=cal.get('refreshToken'),
                    updated_at=datetime.utcnow()
                )
                for cal in calendars
            ]

            for calendar in calendar_models:
                await self.save_calendar(calendar)

            return calendar_models
        except Exception as e:
            logger.error(f"Error saving calendars for user {user_email}: {str(e)}")
            raise

    async def get_user_calendars(self, user_email: str) -> List[Calendar]:
        """Get all calendars for a user"""
        try:
            cursor = self.collection.find({"user_email": user_email})
            calendars = await cursor.to_list(length=None)
            return [Calendar(**cal) for cal in calendars]
        except Exception as e:
            logger.error(f"Error getting calendars for user {user_email}: {str(e)}")
            raise

    async def get_calendar(self, calendar_id: str, user_email: str) -> Optional[Calendar]:
        """Get a specific calendar"""
        try:
            calendar = await self.collection.find_one({
                "id": calendar_id,
                "user_email": user_email
            })
            return Calendar(**calendar) if calendar else None
        except Exception as e:
            logger.error(f"Error getting calendar {calendar_id} for user {user_email}: {str(e)}")
            raise

    async def delete_calendar(self, calendar_id: str, user_email: str) -> bool:
        """Delete a calendar"""
        try:
            result = await self.collection.delete_one({
                "id": calendar_id,
                "user_email": user_email
            })
            logger.info(f"Deleted calendar {calendar_id} for user {user_email}")
            return result.deleted_count > 0
        except Exception as e:
            error_msg = f"Error deleting calendar {calendar_id} for user {user_email}: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg) 