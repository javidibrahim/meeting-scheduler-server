from fastapi import APIRouter, HTTPException, Request
from db.mongo import db
from datetime import datetime, timedelta
from bson import ObjectId
import logging
from typing import List, Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meetings", tags=["meetings"])

def init_meetings_routes():
    """
    Initialize meetings routes that require authentication.
    Returns the router with all meetings endpoints configured.
    """
    
    @router.get("")
    async def get_user_meetings(request: Request):
        """Get all scheduled meetings for the authenticated user"""
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            logger.info(f"Fetching scheduled meetings for user {user_email}")
            
            # Fetch upcoming scheduled events
            now = datetime.utcnow()
            
            scheduled_events = await db["scheduled_events"].find(
                {
                    "user_id": user_email,
                    # Use string comparison for date range since scheduled_for is stored as string
                    "scheduled_for": {
                        "$gte": now.isoformat().split('T')[0]
                    }
                }
            ).sort("scheduled_for", 1).to_list(length=None)
            
            # Process scheduled events to include more details
            processed_events = []
            for event in scheduled_events:
                # Fetch the scheduling link to get more context
                link_id = event.get("scheduling_link_id")
                link = None
                if link_id:
                    try:
                        link = await db["schedule_links"].find_one({"_id": ObjectId(link_id)})
                    except Exception as e:
                        logger.error(f"Error fetching link for event: {str(e)}")
                
                # Calculate times
                start_time_str = event.get("scheduled_for")
                duration_minutes = event.get("duration_minutes", 30)
                
                try:
                    # Parse the scheduled_for field
                    if 'T' in start_time_str:  # ISO format with time
                        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    else:  # Date only format
                        # Default to 9 AM if only date is provided
                        start_time = datetime.fromisoformat(f"{start_time_str}T09:00:00+00:00")
                        
                    end_time = start_time + timedelta(minutes=duration_minutes)
                    
                    # Check if event has enrichment data
                    has_enrichment = bool(event.get("enrichment"))
                    
                    # Create a processed event object
                    processed_event = {
                        "id": str(event.get("_id", "")),
                        "client_email": event.get("email", ""),
                        "client_linkedin": event.get("linkedin", ""),
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "duration_minutes": duration_minutes,
                        "answers": event.get("answers", []),
                        "link_slug": link.get("slug") if link else None,
                        "created_at": event.get("created_at").isoformat() if event.get("created_at") else None,
                        "has_enrichment": has_enrichment
                    }
                    
                    processed_events.append(processed_event)
                except Exception as e:
                    logger.error(f"Error processing event {start_time_str}: {str(e)}")
                
            return processed_events
            
        except Exception as e:
            logger.error(f"Error fetching scheduled meetings: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{meeting_id}")
    async def get_meeting_details(request: Request, meeting_id: str):
        """Get details for a specific scheduled meeting"""
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            
            # Fetch the meeting
            meeting = await db["scheduled_events"].find_one({
                "_id": ObjectId(meeting_id),
                "user_id": user_email
            })
            
            if not meeting:
                raise HTTPException(status_code=404, detail="Meeting not found")
            
            # Fetch associated scheduling link
            link = None
            if meeting.get("scheduling_link_id"):
                try:
                    link = await db["schedule_links"].find_one({"_id": ObjectId(meeting.get("scheduling_link_id"))})
                except Exception as e:
                    logger.error(f"Error fetching link for meeting: {str(e)}")
            
            # Calculate times
            start_time_str = meeting.get("scheduled_for")
            duration_minutes = meeting.get("duration_minutes", 30)
            
            try:
                # Parse the scheduled_for field
                if 'T' in start_time_str:  # ISO format with time
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                else:  # Date only format
                    # Default to 9 AM if only date is provided
                    start_time = datetime.fromisoformat(f"{start_time_str}T09:00:00+00:00")
                    
                end_time = start_time + timedelta(minutes=duration_minutes)
                
                # Get enrichment data if it exists
                enrichment = meeting.get("enrichment", {})
                
                # Create response object
                response = {
                    "id": str(meeting.get("_id", "")),
                    "client_email": meeting.get("email", ""),
                    "client_linkedin": meeting.get("linkedin", ""),
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration_minutes": duration_minutes,
                    "answers": meeting.get("answers", []),
                    "link_details": {
                        "id": str(link.get("_id")) if link else None,
                        "slug": link.get("slug") if link else None,
                        "customQuestions": link.get("customQuestions", []) if link else []
                    } if link else None,
                    "created_at": meeting.get("created_at").isoformat() if meeting.get("created_at") else None,
                    "enrichment": {
                        "linkedin_summary": enrichment.get("linkedin_summary"),
                        "augmented_note": enrichment.get("augmented_note"),
                        "enriched_at": enrichment.get("enriched_at").isoformat() if enrichment.get("enriched_at") else None
                    } if enrichment else None
                }
                
                return response
                
            except Exception as e:
                logger.error(f"Error processing meeting {start_time_str}: {str(e)}")
                raise HTTPException(status_code=500, detail="Error processing meeting data")
            
        except HTTPException as he:
            # Re-raise HTTP exceptions
            raise he
        except Exception as e:
            logger.error(f"Error fetching meeting details: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return router 