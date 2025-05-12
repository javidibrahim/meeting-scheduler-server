from typing import List, Optional, Dict
from datetime import datetime
from models.calendar import Event
from db.mongo import db
import logging

logger = logging.getLogger(__name__)

class EventDBService:
    def __init__(self):
        self.collection = db["events"]

    async def save_events(self, calendar_id: str, events: List[dict]) -> List[Event]:
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

    def _parse_event_dict(self, calendar_id: str, event: dict) -> Event:
        """Convert raw dict to Event model"""
        start_time = self._parse_time(event['start'])
        end_time = self._parse_time(event['end'])

        return Event(
            id=event['id'],
            calendar_id=calendar_id,
            summary=event['summary'],
            description=event.get('description'),
            start_time=start_time,
            end_time=end_time,
            location=event.get('location'),
            status=event.get('status', 'confirmed'),
            updated_at=datetime.utcnow()
        )

    def _parse_time(self, time_dict: dict) -> datetime:
        """Handle both datetime and all-day date-only events"""
        value = time_dict.get('dateTime') or time_dict.get('date')
        return datetime.fromisoformat(value.replace('Z', '+00:00'))

    async def _upsert_event(self, event: Event):
        """Update or insert an event using upsert"""
        try:
            # Prepare update data
            update_data = event.dict()
            # Remove created_at from update data
            created_at = update_data.pop('created_at', None)
            
            # Use upsert to update or insert
            result = await self.collection.update_one(
                {"id": event.id, "calendar_id": event.calendar_id},
                {
                    "$set": update_data,
                    "$setOnInsert": {"created_at": created_at or datetime.utcnow()}
                },
                upsert=True
            )
            
            if result.upserted_id:
                logger.info(f"Added new event {event.summary} for calendar {event.calendar_id}")
            else:
                logger.info(f"Updated event {event.summary} for calendar {event.calendar_id}")
        except Exception as e:
            logger.error(f"Error upserting event: {str(e)}")
            raise

    async def get_calendar_events(self, calendar_id: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Event]:
        """Get all events for a calendar within an optional time range"""
        try:
            query = {"calendar_id": calendar_id}
            if start_time and end_time:
                query["start_time"] = {"$gte": start_time}
                query["end_time"] = {"$lte": end_time}

            cursor = self.collection.find(query)
            events = await cursor.to_list(length=None)
            return [Event(**event) for event in events]
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

    async def get_event(self, calendar_id: str, event_id: str) -> Optional[Event]:
        """Get a specific event"""
        try:
            event = await self.collection.find_one({
                "calendar_id": calendar_id,
                "id": event_id
            })
            return Event(**event) if event else None
        except Exception as e:
            logger.error(f"Error getting event {event_id} for calendar {calendar_id}: {str(e)}")
            raise
