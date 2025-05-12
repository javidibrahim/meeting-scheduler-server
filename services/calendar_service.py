import httpx
from typing import List, Dict, Optional, Any
from fastapi import HTTPException
import logging
from services.event_db import EventDBService
from db.mongo import get_db
from services.oauth_service import OAuthService
from datetime import datetime

logger = logging.getLogger(__name__)

class CalendarService:
    def __init__(self, oauth_client: OAuthService):
        self.oauth_client = oauth_client
        self.event_db = EventDBService()
        self.collection_name = "calendars"

    async def get_user_calendars(self, user_email: str) -> List[Dict[str, Any]]:
        """Get all calendars for a user from database"""
        try:
            async with get_db() as db:
                collection = db[self.collection_name]
                cursor = collection.find({"user_email": user_email})
                calendars = await cursor.to_list(length=None)
                for calendar in calendars:
                    calendar["_id"] = str(calendar["_id"])
                return calendars
        except Exception as e:
            logger.error(f"Error getting calendars for user {user_email}: {str(e)}")
            raise

    async def save_calendar(self, calendar_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save or update a calendar"""
        try:
            async with get_db() as db:
                collection = db[self.collection_name]
                calendar_data["updated_at"] = datetime.utcnow()
                
                # Try to find existing calendar
                existing = await collection.find_one({
                    "user_email": calendar_data["user_email"],
                    "calendar_id": calendar_data["calendar_id"]
                })
                
                if existing:
                    # Update existing calendar
                    result = await collection.update_one(
                        {
                            "user_email": calendar_data["user_email"],
                            "calendar_id": calendar_data["calendar_id"]
                        },
                        {"$set": calendar_data}
                    )
                    if result.modified_count > 0:
                        calendar = await collection.find_one({
                            "user_email": calendar_data["user_email"],
                            "calendar_id": calendar_data["calendar_id"]
                        })
                        if calendar:
                            calendar["_id"] = str(calendar["_id"])
                        return calendar
                else:
                    # Create new calendar
                    calendar_data["created_at"] = datetime.utcnow()
                    result = await collection.insert_one(calendar_data)
                    calendar_data["_id"] = str(result.inserted_id)
                    return calendar_data
                
                raise Exception("Failed to save calendar")
        except Exception as e:
            logger.error(f"Error saving calendar: {str(e)}")
            raise

    async def delete_calendar(self, user_email: str, calendar_id: str) -> bool:
        """Delete a calendar and its events"""
        try:
            async with get_db() as db:
                collection = db[self.collection_name]
                # Delete calendar
                result = await collection.delete_one({
                    "user_email": user_email,
                    "calendar_id": calendar_id
                })
                
                if result.deleted_count > 0:
                    # Delete associated events
                    await self.event_db.delete_calendar_events(calendar_id)
                    return True
                return False
        except Exception as e:
            logger.error(f"Error deleting calendar: {str(e)}")
            raise

    async def get_calendar(self, user_email: str, calendar_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific calendar"""
        try:
            async with get_db() as db:
                collection = db[self.collection_name]
                calendar = await collection.find_one({
                    "user_email": user_email,
                    "calendar_id": calendar_id
                })
                if calendar:
                    calendar["_id"] = str(calendar["_id"])
                return calendar
        except Exception as e:
            logger.error(f"Error getting calendar: {str(e)}")
            raise

    async def sync_calendars(self, token: Dict, user_email: str) -> List[Dict]:
        """Sync calendars from Google Calendar API and store in database"""
        try:
            async with httpx.AsyncClient() as client:
                headers = self._get_auth_headers(token)
                user_info = await self._verify_token(client, headers)
                calendars = await self._fetch_calendar_list(client, headers)

                processed_calendars = await self._process_calendars(client, headers, calendars, token, user_info)
                
                # Store calendars in database
                for calendar in processed_calendars:
                    await self.save_calendar({
                        "user_email": user_email,
                        "calendar_id": calendar["id"],
                        "name": calendar["name"],
                        "email": calendar["email"],
                        "access_role": calendar["accessRole"],
                        "is_read_only": calendar["isReadOnly"],
                        "access_token": calendar["accessToken"],
                        "refresh_token": calendar.get("refreshToken"),
                        "events_count": calendar["eventsCount"]
                    })
                
                return processed_calendars
        except Exception as e:
            logger.error(f"Error in sync_calendars: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to sync calendars: {str(e)}")

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
            deleted = await self.delete_calendar(user_email, calendar_id)
            logger.info(f"Deleted calendar {calendar_id} for user {user_email}")
            
            return deleted
        except Exception as e:
            logger.error(f"Error disconnecting calendar {calendar_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to disconnect calendar: {str(e)}")
