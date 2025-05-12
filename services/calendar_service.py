import httpx
from typing import List, Dict
from fastapi import HTTPException
import logging
from services.event_db import EventDBService
from services.calendar_db import CalendarDBService

logger = logging.getLogger(__name__)

class CalendarService:
    def __init__(self, oauth_client):
        self.oauth_client = oauth_client
        self.event_db = EventDBService()
        self.calendar_db = CalendarDBService()

    async def get_calendars(self, token: Dict, user_email: str) -> List[Dict]:
        """Main method: returns list of connected calendars and stores their events"""
        try:
            async with httpx.AsyncClient() as client:
                headers = self._get_auth_headers(token)
                user_info = await self._verify_token(client, headers)
                calendars = await self._fetch_calendar_list(client, headers)

                processed_calendars = await self._process_calendars(client, headers, calendars, token, user_info)
                
                # Store calendars in database
                await self.calendar_db.save_calendars(user_email, processed_calendars)
                
                return processed_calendars
        except Exception as e:
            logger.error(f"Error in get_calendars: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch calendars: {str(e)}")

    def _get_auth_headers(self, token: Dict) -> Dict:
        return {'Authorization': f'Bearer {token["access_token"]}'}

    async def _verify_token(self, client: httpx.AsyncClient, headers: Dict) -> Dict:
        try:
            user_response = await client.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers=headers
            )
            user_info = user_response.json()
            logger.info(f"Token verified for user: {user_info.get('email')}")
            return user_info
        except Exception as e:
            logger.error(f"Failed to verify token: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid token")

    async def _fetch_calendar_list(self, client: httpx.AsyncClient, headers: Dict) -> List[Dict]:
        logger.info("Fetching calendar list")
        response = await client.get(
            'https://www.googleapis.com/calendar/v3/users/me/calendarList',
            headers=headers
        )
        if not response.is_success:
            logger.error(f"Failed to fetch calendars: {response.status_code} - {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch calendars")
        return response.json().get('items', [])

    async def _process_calendars(self, client, headers, calendars, token, user_info) -> List[Dict]:
        results = []
        for calendar in calendars:
            access_role = calendar.get('accessRole')
            logger.info(f"Calendar: {calendar.get('summary')} - Access Role: {access_role}")

            if access_role in ['owner', 'writer', 'reader']:
                try:
                    events = await self._fetch_calendar_events(client, headers, calendar['id'])
                    if events:
                        await self.event_db.save_events(calendar['id'], events)
                        logger.info(f"Stored {len(events)} events for calendar {calendar['summary']}")
                    
                    results.append({
                        'id': calendar['id'],
                        'name': calendar['summary'],
                        'email': calendar.get('id'),
                        'eventsCount': len(events),
                        'accessRole': access_role,
                        'isReadOnly': access_role == 'reader',
                        'accessToken': token['access_token'],
                        'refreshToken': token.get('refresh_token')
                    })
                except Exception as e:
                    logger.error(f"Failed to fetch events for calendar {calendar.get('summary')}: {str(e)}")
            else:
                logger.info(f"Skipping calendar {calendar.get('summary')} due to insufficient permissions")

        logger.info(f"Returning {len(results)} calendars with write access")
        return results

    async def _fetch_calendar_events(self, client, headers, calendar_id):
        response = await client.get(
            f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events',
            headers=headers,
            params={'maxResults': 100, 'timeMin': '2024-01-01T00:00:00Z'}
        )
        return response.json().get('items', [])

    async def disconnect_calendar(self, calendar_id: str, user_email: str) -> bool:
        """Remove a calendar and delete its events"""
        try:
            # Delete events first
            await self.event_db.delete_calendar_events(calendar_id)
            logger.info(f"Deleted all events for calendar {calendar_id}")
            
            # Then delete the calendar
            deleted = await self.calendar_db.delete_calendar(calendar_id, user_email)
            logger.info(f"Deleted calendar {calendar_id} for user {user_email}")
            
            return deleted
        except Exception as e:
            logger.error(f"Error disconnecting calendar {calendar_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to disconnect calendar: {str(e)}")

    async def get_stored_calendars(self, user_email: str) -> List[Dict]:
        """Get calendars from database"""
        try:
            calendars = await self.calendar_db.get_user_calendars(user_email)
            return [cal.dict() for cal in calendars]
        except Exception as e:
            logger.error(f"Error getting stored calendars for user {user_email}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get calendars: {str(e)}")
