from fastapi import APIRouter, HTTPException, Body, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request as StarletteRequest
from db.mongo import db
from models.schedule_links import ScheduleLink
from models.scheduled_events import ScheduledEvent
from datetime import datetime, timedelta, date
from bson import ObjectId
import logging
import json
from typing import List, Dict, Any
from services.email_service import send_meeting_notification

# Set up logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Helper function to convert MongoDB documents to JSON serializable format
def make_serializable(obj):
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_serializable(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    else:
        # Try to convert other types to string
        try:
            return str(obj)
        except Exception:
            return None

router = APIRouter(prefix="/public", tags=["public"])

def init_public_routes():
    """
    Initialize public routes that don't require authentication.
    Returns the router with all public endpoints configured.
    """
    logger.info("Initializing public routes")
    
    @router.get("/schedule/{slug}")
    async def get_public_schedule_link(slug: str):
        """Get public scheduling link data by slug without authentication"""
        logger.info(f"[PUBLIC] GET /schedule/{slug} - Fetching public schedule link")
        try:
            # Find the link by slug
            logger.info(f"[PUBLIC] Searching for schedule link with slug: {slug}")
            link = await db["schedule_links"].find_one({"slug": slug})
            
            if not link:
                logger.warning(f"[PUBLIC] Schedule link not found for slug: {slug}")
                raise HTTPException(status_code=404, detail="Schedule link not found")
            
            logger.info(f"[PUBLIC] Found link: {link.get('slug')} - Fields: maxDaysInAdvance={link.get('maxDaysInAdvance')}, meetingLength={link.get('meetingLength')}")
            
            # Check if link has expired
            if link.get("expirationDate"):
                expiration_date = datetime.fromisoformat(link["expirationDate"]) if isinstance(link["expirationDate"], str) else link["expirationDate"]
                if expiration_date.date() < datetime.now().date():
                    logger.warning(f"[PUBLIC] Link {slug} has expired on {expiration_date.date()}")
                    raise HTTPException(status_code=400, detail="This link has expired")
            
            # Check if link has reached maximum uses
            if link.get("maxUses") and link.get("uses", 0) >= link["maxUses"]:
                logger.warning(f"[PUBLIC] Link {slug} has reached max uses: {link.get('uses')}/{link.get('maxUses')}")
                raise HTTPException(status_code=400, detail="This link has reached its maximum number of uses")
            
            # Get advisor data
            user_email = link.get("userId")
            logger.info(f"[PUBLIC] Fetching advisor data for email: {user_email}")
            
            advisor = await db["users"].find_one({"email": user_email})
            advisor_data = None
            if advisor:
                advisor_data = {
                    "name": advisor.get("name", "Advisor"),
                    "email": advisor.get("email")
                }
                logger.info(f"[PUBLIC] Found advisor: {advisor_data['name']}")
            else:
                advisor_data = {
                    "name": "Advisor",
                    "email": user_email
                }
                logger.warning(f"[PUBLIC] No advisor found for email: {user_email}, using default")
            
            # Get availability windows
            logger.info(f"[PUBLIC] Fetching availability windows for user: {user_email}")
            availability_docs = await db["availability_windows"].find(
                {"user_id": user_email}
            ).to_list(length=None)
            
            logger.info(f"[PUBLIC] Found {len(availability_docs)} availability windows")
            
            # Get events
            logger.info(f"[PUBLIC] Fetching calendar events for user: {user_email}")
            calendars = await db["calendars"].find(
                {"user_email": user_email}
            ).to_list(length=None)
            
            calendar_ids = [cal.get("id") for cal in calendars if cal.get("id")]
            logger.info(f"[PUBLIC] Found {len(calendar_ids)} connected calendars")
            
            # Get maxDaysInAdvance from the link or default to 14
            max_days_in_advance = link.get("maxDaysInAdvance", 14)
            now = datetime.utcnow()
            max_date = now + timedelta(days=max_days_in_advance)
            
            events = []
            for calendar_id in calendar_ids:
                try:
                    logger.info(f"[PUBLIC] Fetching events for calendar: {calendar_id}")
                    calendar_events = await db["events"].find(
                        {
                            "calendar_id": calendar_id,
                            "start_time": {"$lte": max_date},
                            "end_time": {"$gte": now}
                        }
                    ).to_list(length=None)
                    
                    logger.info(f"[PUBLIC] Found {len(calendar_events)} events for calendar {calendar_id}")
                    events.extend(calendar_events)
                    
                except Exception as e:
                    logger.error(f"[PUBLIC] Error fetching events for calendar {calendar_id}: {str(e)}")
            
            # Get scheduled events
            logger.info(f"[PUBLIC] Fetching scheduled events for user: {user_email}")
            try:
                scheduled_events = await db["scheduled_events"].find(
                    {
                        "user_id": user_email,
                        "scheduled_for": {
                            "$gte": now.isoformat().split('T')[0],
                            "$lte": max_date.isoformat().split('T')[0] + 'T23:59:59'
                        }
                    }
                ).to_list(length=None)
                
                logger.info(f"[PUBLIC] Found {len(scheduled_events)} scheduled events")
                events.extend(scheduled_events)
                
            except Exception as e:
                logger.error(f"[PUBLIC] Error fetching scheduled events: {str(e)}")
            
            # Prepare response
            response_data = {
                "link": link,
                "advisor": advisor_data,
                "availability": availability_docs,
                "events": events
            }
            
            logger.info(f"[PUBLIC] Successfully prepared response for slug: {slug}")
            return make_serializable(response_data)
            
        except HTTPException as he:
            logger.error(f"[PUBLIC] HTTP Exception for slug {slug}: {str(he)}")
            raise
        except Exception as e:
            logger.error(f"[PUBLIC] Error fetching public schedule link for {slug}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("/schedule/book")
    async def book_meeting(booking: ScheduledEvent):
        """Book a meeting through a public scheduling link without authentication"""
        logger.info(f"[PUBLIC] POST /schedule/book - Received booking request for email: {booking.email}")
        try:
            logger.info(f"[PUBLIC] Attempting to book meeting with link ID: {booking.scheduling_link_id}")
            # Find the link by ID
            link = await db["schedule_links"].find_one({"_id": ObjectId(booking.scheduling_link_id)})
            
            if not link:
                raise HTTPException(status_code=404, detail="Schedule link not found")
                
            logger.info(f"Found link: {link.get('slug')} with fields: maxDaysInAdvance={link.get('maxDaysInAdvance')}, meetingLength={link.get('meetingLength')}")
            
            # Check if link has expired
            if link.get("expirationDate"):
                expiration_date = datetime.fromisoformat(link["expirationDate"]) if isinstance(link["expirationDate"], str) else link["expirationDate"]
                if expiration_date.date() < datetime.now().date():
                    raise HTTPException(status_code=400, detail="This link has expired")
            
            # Check if link has reached maximum uses
            if link.get("maxUses") and link.get("uses", 0) >= link["maxUses"]:
                raise HTTPException(status_code=400, detail="This link has reached its maximum number of uses")
                
            # Check if booking date is within maxDaysInAdvance
            max_days_in_advance = link.get("maxDaysInAdvance", 14)
            
            # Parse received date - without timezone info it's assumed to be in local time
            logger.info(f"Received booking request for time: {booking.scheduled_for}")
            scheduled_date = datetime.fromisoformat(booking.scheduled_for)
            logger.info(f"Parsed scheduled date as: {scheduled_date}")
            
            # Create timezone-aware now and max_date for proper comparison
            now = datetime.utcnow()
            max_date = now + timedelta(days=max_days_in_advance)
            
            if scheduled_date > max_date:
                raise HTTPException(status_code=400, detail=f"Cannot book more than {max_days_in_advance} days in advance")
                
            # Check for duplicate bookings at the same time
            existing_booking = await db["scheduled_events"].find_one({
                "user_id": link.get("userId"),
                "scheduled_for": booking.scheduled_for
            })
            
            if existing_booking:
                logger.warning(f"Duplicate booking attempt at {booking.scheduled_for}")
                raise HTTPException(status_code=400, detail="This time slot is no longer available. Please select another time.")
                
            # Verify meeting duration matches the link's meetingLength
            if booking.duration_minutes != link.get("meetingLength"):
                logger.warning(f"Duration mismatch: requested {booking.duration_minutes} min but link specifies {link.get('meetingLength')} min")
                # Use the correct duration from the link
                booking.duration_minutes = link.get("meetingLength")
            
            # Create a scheduled event
            scheduled_event = {
                "scheduling_link_id": booking.scheduling_link_id,
                "user_id": link.get("userId"),  # advisor email
                "scheduled_for": booking.scheduled_for,
                "duration_minutes": booking.duration_minutes,
                "email": booking.email,
                "linkedin": booking.linkedin,
                "answers": [answer.dict() for answer in booking.answers],
                "created_at": datetime.utcnow()
            }
            
            logger.info(f"Creating scheduled event: {json.dumps(scheduled_event, default=str)}")
            
            # Insert the scheduled event
            result = await db["scheduled_events"].insert_one(scheduled_event)
            scheduled_event_id = result.inserted_id
            
            # Increment the use counter for the link
            await db["schedule_links"].update_one(
                {"_id": ObjectId(booking.scheduling_link_id)},
                {"$inc": {"uses": 1}}
            )
            
            logger.info(f"Meeting scheduled successfully for {booking.email} with advisor {link.get('userId')}")
            
            # Send email notification to the advisor
            try:
                logger.info(f"Initiating email notification to advisor: {link.get('userId')}")
                email_sent = await send_meeting_notification(
                    advisor_email=link.get("userId"),
                    client_email=booking.email,
                    scheduled_date=scheduled_date,
                    duration=booking.duration_minutes,
                    answers=booking.answers,
                    client_linkedin=booking.linkedin,
                    scheduling_link_id=booking.scheduling_link_id
                )
                if email_sent:
                    logger.info("Email notification successfully completed")
                else:
                    logger.warning("Email notification process completed but email was not sent")
            except Exception as e:
                logger.warning(f"Failed to send notification email: {str(e)}")
                # Continue with the response even if email fails
            
            response_data = {
                "success": True,
                "message": "Meeting scheduled successfully",
                "scheduled_event_id": str(result.inserted_id)
            }
            
            return response_data
            
        except HTTPException as he:
            # Re-raise HTTP exceptions directly
            raise
        except Exception as e:
            logger.error(f"Error booking meeting: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Add a catch-all route to handle direct URL access
    @router.get("/{slug}")
    async def redirect_public_schedule_link(slug: str):
        """Redirect to the proper public schedule link format"""
        logger.info(f"[PUBLIC] GET /{slug} - Redirecting to proper schedule link format")
        return await get_public_schedule_link(slug)
    
    logger.info("Public routes initialization complete")
    return router 