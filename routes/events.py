from fastapi import APIRouter, Request, HTTPException
from services.event_db import EventDBService
from services.calendar_service import CalendarService
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

def init_events_routes(oauth_client):
    event_db = EventDBService()
    calendar_service = CalendarService(oauth_client)

    @router.get("/{calendar_id}")
    async def get_calendar_events(request: Request, calendar_id: str):
        """Get all events for a calendar"""
        try:
            # Verify user is authenticated
            user = request.session.get('user')
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")
            
            user_email = user['email']
            logger.info(f"Fetching events for calendar {calendar_id} for user {user_email}")

            # Verify calendar belongs to user
            try:
                calendar = await calendar_service.calendar_db.get_calendar(calendar_id, user_email)
                if not calendar:
                    logger.warning(f"Calendar {calendar_id} not found for user {user_email}")
                    return []  # Return empty list instead of 404 for non-existent calendars
            except Exception as e:
                logger.error(f"Error checking calendar access: {str(e)}")
                raise HTTPException(status_code=500, detail="Error checking calendar access")

            # Get events from database
            try:
                events = await event_db.get_calendar_events(calendar_id)
                logger.info(f"Retrieved {len(events)} events for calendar {calendar_id}")
                
                # Convert to simple response format
                return [
                    {
                        "id": event["id"],
                        "summary": event["summary"],
                        "start": event["start_time"].isoformat(),
                        "end": event["end_time"].isoformat(),
                        "status": event["status"]
                    }
                    for event in events
                ]
            except Exception as e:
                logger.error(f"Database error fetching events: {str(e)}")
                raise HTTPException(status_code=500, detail="Database error fetching events")

        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Unexpected error fetching events: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to fetch events")

    return router