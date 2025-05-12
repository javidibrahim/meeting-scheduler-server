from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from services.calendar_service import CalendarService
from services.event_db import EventDBService
import os
import logging
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google/calendar", tags=["calendar"])
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://meeting-scheduler-client-delta.vercel.app")

def init_calendar_routes(oauth_client):
    calendar_service = CalendarService(oauth_client)
    event_db = EventDBService()

    @router.get("")
    async def google_calendar_auth(request: Request):
        """Start Google Calendar OAuth flow"""
        # Check if user is logged in
        user = request.session.get('user')
        if not user:
            logger.error("No user found in session during calendar auth")
            return RedirectResponse(url=f'{FRONTEND_URL}/dashboard?error=not_authenticated')
            
        redirect_uri = request.url_for('calendar_callback')
        logger.info(f"Starting calendar OAuth flow for user {user.get('email')} with redirect URI: {redirect_uri}")
        return await oauth_client.google.authorize_redirect(
            request, 
            redirect_uri,
            access_type='offline',
            prompt='consent'
        )

    @router.get("/callback")
    async def calendar_callback(request: Request):
        """Handle Google Calendar OAuth callback"""
        try:
            # Verify user is logged in
            user = request.session.get('user')
            if not user:
                logger.error("No user found in session during calendar callback")
                return RedirectResponse(url=f'{FRONTEND_URL}/dashboard?error=not_authenticated')

            user_email = user.get('email')
            logger.info(f"Starting calendar callback process for user {user_email}")
            
            token = await oauth_client.google.authorize_access_token(request)
            logger.info("Successfully obtained access token")
            logger.info(f"Token scopes: {token.get('scope', '').split()}")
            
            calendar_details = await calendar_service.get_calendars(token, user_email)
            logger.info(f"Retrieved {len(calendar_details)} calendars")
            if calendar_details:
                logger.info(f"First calendar details: {calendar_details[0]}")
            
            # Redirect with success parameter
            redirect_url = f'{FRONTEND_URL}/dashboard?success=true'
            logger.info(f"Redirecting to: {redirect_url}")
            return RedirectResponse(url=redirect_url)
            
        except Exception as e:
            logger.error(f"Calendar auth callback error: {str(e)}")
            logger.error(f"Full exception details: {repr(e)}")
            return RedirectResponse(
                url=f'{FRONTEND_URL}/dashboard?error=calendar_auth_failed&message={str(e)}'
            )

    @router.get("/list")
    async def list_calendars(request: Request):
        """Get list of connected calendars"""
        try:
            user = request.session.get('user')
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")
            
            user_email = user.get('email')
            logger.info(f"Calendar list request for user {user_email}")
            
            # Get calendars from database first
            try:
                calendars = await calendar_service.get_stored_calendars(user_email)
                if calendars:
                    logger.info(f"Retrieved {len(calendars)} calendars from database for user {user_email}")
                    return calendars
            except Exception as e:
                logger.warning(f"Failed to get calendars from database: {str(e)}")
            
            # If no calendars in database or error, fetch from Google
            token = request.session.get('google_token')
            if not token:
                raise HTTPException(status_code=401, detail="No Google token found")
            
            calendars = await calendar_service.get_calendars(token, user_email)
            logger.info(f"Retrieved {len(calendars)} calendars from Google for user {user_email}")
            return calendars
        except Exception as e:
            logger.error(f"Error listing calendars: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/{calendar_id}")
    async def disconnect_calendar(request: Request, calendar_id: str):
        """Disconnect a calendar"""
        try:
            user = request.session.get('user')
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")
            
            user_email = user.get('email')
            logger.info(f"Disconnecting calendar {calendar_id} for user {user_email}")
            
            try:
                deleted = await calendar_service.disconnect_calendar(calendar_id, user_email)
                
                if not deleted:
                    raise HTTPException(status_code=404, detail="Calendar not found")
                
                return {"message": "Calendar disconnected successfully"}
            except HTTPException as he:
                # Re-raise HTTP exceptions as is
                raise he
            except Exception as e:
                # Log the full error and raise a new HTTP exception
                error_msg = f"Failed to disconnect calendar: {str(e)}"
                logger.error(error_msg)
                logger.error(f"Full exception details: {repr(e)}")
                raise HTTPException(status_code=500, detail=error_msg)
        except HTTPException as he:
            # Re-raise HTTP exceptions from the outer try block
            raise he
        except Exception as e:
            # Handle any other unexpected errors
            error_msg = f"Unexpected error disconnecting calendar: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Full exception details: {repr(e)}")
            raise HTTPException(status_code=500, detail=error_msg)

    return router