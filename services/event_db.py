from typing import List, Optional, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from db.mongo import db
import logging

logger = logging.getLogger(__name__)

class EventDBService:
    def __init__(self):
        self.collection = db["events"]

    async def create_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new event"""
        try:
            event_data["created_at"] = datetime.utcnow()
            result = await self.collection.insert_one(event_data)
            event_data["_id"] = str(result.inserted_id)
            return event_data
        except Exception as e:
            logger.error(f"Error creating event: {str(e)}")
            raise

    async def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get an event by ID"""
        try:
            event = await self.collection.find_one({"_id": event_id})
            if event:
                event["_id"] = str(event["_id"])
            return event
        except Exception as e:
            logger.error(f"Error getting event: {str(e)}")
            raise

    async def get_events_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all events for a user"""
        try:
            cursor = self.collection.find({"user_id": user_id})
            events = await cursor.to_list(length=None)
            for event in events:
                event["_id"] = str(event["_id"])
            return events
        except Exception as e:
            logger.error(f"Error getting user events: {str(e)}")
            raise

    async def update_event(self, event_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an event"""
        try:
            update_data["updated_at"] = datetime.utcnow()
            result = await self.collection.update_one(
                {"_id": event_id},
                {"$set": update_data}
            )
            if result.modified_count > 0:
                event = await self.collection.find_one({"_id": event_id})
                if event:
                    event["_id"] = str(event["_id"])
                return event
            return None
        except Exception as e:
            logger.error(f"Error updating event: {str(e)}")
            raise

    async def delete_event(self, event_id: str) -> bool:
        """Delete an event"""
        try:
            result = await self.collection.delete_one({"_id": event_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting event: {str(e)}")
            raise

    async def get_events_by_date_range(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get events within a date range for a user"""
        try:
            cursor = self.collection.find({
                "user_id": user_id,
                "start_time": {"$gte": start_date},
                "end_time": {"$lte": end_date}
            })
            events = await cursor.to_list(length=None)
            for event in events:
                event["_id"] = str(event["_id"])
            return events
        except Exception as e:
            logger.error(f"Error getting events by date range: {str(e)}")
            raise

    async def save_events(self, calendar_id: str, events: List[dict]) -> List[dict]:
        """Save or update events for a calendar"""
        try:
            event_models = []
            for event_dict in events:
                event = self._parse_event_dict(calendar_id, event_dict)
                await self._upsert_event(event)
                event_models.append(event)
            
            logger.info(f"Processed {len(event_models)} events for calendar {calendar_id}")
            return event_models
        except Exception as e:
            logger.error(f"Error saving events: {str(e)}")
            raise

    def _parse_event_dict(self, calendar_id: str, event: dict) -> dict:
        """Convert raw dict to Event model"""
        start_time = self._parse_time(event['start'])
        end_time = self._parse_time(event['end'])

        return {
            "id": event['id'],
            "calendar_id": calendar_id,
            "summary": event['summary'],
            "description": event.get('description'),
            "start_time": start_time,
            "end_time": end_time,
            "location": event.get('location'),
            "status": event.get('status', 'confirmed'),
            "updated_at": datetime.utcnow()
        }

    def _parse_time(self, time_dict: dict) -> datetime:
        """Handle both datetime and all-day date-only events"""
        value = time_dict.get('dateTime') or time_dict.get('date')
        return datetime.fromisoformat(value.replace('Z', '+00:00'))

    async def _upsert_event(self, event: dict):
        """Update or insert an event using upsert"""
        try:
            # Prepare update data
            update_data = event
            # Remove created_at from update data
            created_at = update_data.pop('created_at', None)
            
            # Use upsert to update or insert
            result = await self.collection.update_one(
                {"id": event['id'], "calendar_id": event['calendar_id']},
                {
                    "$set": update_data,
                    "$setOnInsert": {"created_at": created_at or datetime.utcnow()}
                },
                upsert=True
            )
            
            if result.upserted_id:
                logger.info(f"Added new event {event['summary']} for calendar {event['calendar_id']}")
            else:
                logger.info(f"Updated event {event['summary']} for calendar {event['calendar_id']}")
        except Exception as e:
            logger.error(f"Error upserting event: {str(e)}")
            raise

    async def get_calendar_events(self, calendar_id: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[dict]:
        """Get all events for a calendar within an optional time range"""
        try:
            query = {"calendar_id": calendar_id}
            if start_time and end_time:
                query["start_time"] = {"$gte": start_time}
                query["end_time"] = {"$lte": end_time}

            cursor = self.collection.find(query)
            events = await cursor.to_list(length=None)
            
            # Convert the dictionary data to formatted events
            formatted_events = []
            for event_data in events:
                # Ensure _id is converted to string
                if "_id" in event_data:
                    event_data["_id"] = str(event_data["_id"])
                formatted_events.append(event_data)
                
            return formatted_events
        except Exception as e:
            logger.error(f"Error getting events for calendar {calendar_id}: {str(e)}")
            raise

    async def delete_calendar_events(self, calendar_id: str) -> bool:
        """Delete all events for a calendar"""
        try:
            result = await self.collection.delete_many({"calendar_id": calendar_id})
            logger.info(f"Deleted {result.deleted_count} events for calendar {calendar_id}")
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting events for calendar {calendar_id}: {str(e)}")
            raise
