from fastapi import APIRouter, HTTPException, Body, Request, BackgroundTasks
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
from services.linkedin_scraper_service import create_linkedin_summary
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
                expiration_date_str = str(link["expirationDate"])
                if 'Z' in expiration_date_str:
                    expiration_date = datetime.fromisoformat(expiration_date_str.replace('Z', '+00:00'))
                elif '+' in expiration_date_str or '-' in expiration_date_str and 'T' in expiration_date_str:
                    expiration_date = datetime.fromisoformat(expiration_date_str)
                else:
                    expiration_date = datetime.fromisoformat(expiration_date_str)
                
                # Convert to naive datetime for comparison
                if expiration_date.tzinfo is not None:
                    expiration_date = expiration_date.replace(tzinfo=None)
                
                if expiration_date.date() < datetime.utcnow().date():
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
    async def book_meeting(booking: ScheduledEvent, background_tasks: BackgroundTasks):
        """Book a meeting through a public scheduling link without authentication"""
        try:
            logger.info(f"[Booking] Starting booking process for email: {booking.email}")
            
            # Find the scheduling link
            logger.info(f"[Booking] Looking up schedule link ID: {booking.scheduling_link_id}")
            link = await db["schedule_links"].find_one({"_id": ObjectId(booking.scheduling_link_id)})
            if not link:
                logger.error(f"[Booking] Schedule link not found: {booking.scheduling_link_id}")
                raise HTTPException(status_code=404, detail="Schedule link not found")
            
            # get advisor email
            user_email = link.get("userId")
            logger.info(f"[Booking] Advisor email: {user_email}")
            
            # Validate link expire time
            if link.get("expirationDate"):
                logger.info(f"[Booking] Validating expiration date: {link.get('expirationDate')}")
                expiration_date = datetime.fromisoformat(str(link["expirationDate"]))
                # Convert to naive datetime for comparison if it's timezone-aware
                if expiration_date.tzinfo is not None:
                    expiration_date = expiration_date.replace(tzinfo=None)
                
                now = datetime.utcnow()  # Use naive UTC time
                if expiration_date.date() < now.date():
                    logger.warning(f"[Booking] Link expired on {expiration_date.date()}")
                    raise HTTPException(status_code=400, detail="This link has expired")
            
            # validate max uses
            current_uses = link.get("uses", 0)
            max_uses = link.get("maxUses")
            if max_uses:
                logger.info(f"[Booking] Checking usage limit: {current_uses}/{max_uses}")
                if current_uses >= max_uses:
                    logger.warning(f"[Booking] Link reached max uses: {current_uses}/{max_uses}")
                    raise HTTPException(status_code=400, detail="This link has reached its maximum number of uses")
            
            # Parse dates and validate booking time
            logger.info(f"[Booking] Validating scheduled date: {booking.scheduled_for}")
            scheduled_date = datetime.fromisoformat(booking.scheduled_for)
            # Convert to naive datetime for comparison if it's timezone-aware
            if scheduled_date.tzinfo is not None:
                scheduled_date = scheduled_date.replace(tzinfo=None)
            
            max_days = link.get("maxDaysInAdvance", 14)
            max_future_date = datetime.utcnow() + timedelta(days=max_days)
            
            if scheduled_date > max_future_date:
                logger.warning(f"[Booking] Date too far in future: {scheduled_date} > {max_future_date}")
                raise HTTPException(status_code=400, detail=f"Cannot book more than {max_days} days in advance")
            
            # Check for double booking
            logger.info(f"[Booking] Checking for double booking at {booking.scheduled_for}")
            existing_booking = await db["scheduled_events"].find_one({
                "user_id": user_email,
                "scheduled_for": booking.scheduled_for
            })
            if existing_booking:
                logger.warning(f"[Booking] Time slot already booked: {booking.scheduled_for}")
                raise HTTPException(status_code=400, detail="This time slot is no longer available")
            
            # Use correct duration from link
            booking.duration_minutes = link.get("meetingLength", booking.duration_minutes)
            logger.info(f"[Booking] Using duration: {booking.duration_minutes} minutes")
            
            # Create and save the scheduled event
            event = {
                "scheduling_link_id": booking.scheduling_link_id,
                "user_id": user_email,
                "scheduled_for": booking.scheduled_for,
                "duration_minutes": booking.duration_minutes,
                "email": booking.email,
                "linkedin": booking.linkedin,
                "answers": [answer.dict() for answer in booking.answers],
                "created_at": datetime.utcnow()
            }
            
            logger.info("[Booking] Inserting scheduled event")
            result = await db["scheduled_events"].insert_one(event)
            
            # Update link usage counter
            logger.info("[Booking] Updating link usage counter")
            await db["schedule_links"].update_one(
                {"_id": ObjectId(booking.scheduling_link_id)},
                {"$inc": {"uses": 1}}
            )

            # Get insert id 
            event_id = result.inserted_id
            logger.info(f"[Booking] Event created with ID: {event_id}")
            
            # Use non-deprecated way to get UTC time
            event_created_at = datetime.utcnow()
            
            # Ensure internal calendar exists for the advisor
            logger.info(f"[Booking] Ensuring internal calendar exists for advisor: {user_email}")
            internal_calendar = {
                "id": "internal",
                "user_email": user_email,
                "access_role": "owner",
                "access_token": "internal",
                "created_at": datetime.utcnow(),
                "email": user_email,
                "events_count": 0,
                "is_read_only": False,
                "name": "Internal Calendar",
                "refresh_token": None,
                "updated_at": datetime.utcnow()
            }
            await db["calendars"].update_one(
                {"id": "internal", "user_email": user_email},
                {"$set": internal_calendar},
                upsert=True
            )
            logger.info(f"[Booking] Internal calendar ensured for advisor: {user_email}")
            
            # insert to events for advisor
            calendar_event = {
                "calendar_id": "internal",
                "id": str(event_id),  # Convert ObjectId to string
                "created_at": event_created_at,
                "description": None,
                "end_time": datetime.fromisoformat(booking.scheduled_for) + timedelta(minutes=booking.duration_minutes),
                "location": None,
                "start_time": datetime.fromisoformat(booking.scheduled_for),
                "status": "confirmed",
                "summary": "Meeting with client " + booking.email,
                "updated_at": event_created_at
            }

            logger.info("[Booking] Creating calendar event")
            calendar_event_result = await db["events"].insert_one(calendar_event)
            
            if not calendar_event_result.inserted_id:
                logger.error("[Booking] Failed to insert calendar event")
                raise HTTPException(status_code=500, detail="Failed to insert calendar event")
            
            logger.info(f"[Booking] calendar event created with id: {calendar_event_result.inserted_id}")
        
            # Add email notification to background tasks instead of awaiting it
            logger.info("[Booking] Scheduling email notification")
            background_tasks.add_task(
                send_meeting_notification,
                advisor_email=user_email,
                client_email=booking.email,
                scheduled_date=scheduled_date,
                duration=booking.duration_minutes,
                answers=booking.answers,
                client_linkedin=booking.linkedin,
                scheduling_link_id=booking.scheduling_link_id
            )
            
            # run background task to get reponse summary and insights text
            if booking.linkedin:
                logger.info(f"[Booking] Scheduling LinkedIn analysis for profile: {booking.linkedin}")
                background_tasks.add_task(
                    create_linkedin_summary,
                    event_id=str(result.inserted_id),
                    profile_url=booking.linkedin,
                    questions=booking.answers,
                    answers=booking.answers
                )
            
            logger.info("[Booking] Successfully completed booking process")
            return {
                "success": True,
                "message": "Meeting scheduled successfully",
                "scheduled_event_id": str(result.inserted_id)
            }
            
        except HTTPException as he:
            logger.error(f"[Booking] HTTP Exception: {str(he.detail)}")
            raise
        except Exception as e:
            logger.error(f"[Booking] Unexpected error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Add a catch-all route to handle direct URL access
    @router.get("/{slug}")
    async def redirect_public_schedule_link(slug: str):
        """Redirect to the proper public schedule link format"""
        logger.info(f"[PUBLIC] GET /{slug} - Redirecting to proper schedule link format")
        return await get_public_schedule_link(slug)
    
    logger.info("Public routes initialization complete")
    return router 