from fastapi import APIRouter, Depends, HTTPException, Request
from models.availability import AvailabilityRequest, AvailabilityWindow
from db.mongo import db
from typing import List
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from bson import ObjectId

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/availability", tags=["availability"])

def init_availability_routes():
    """
    Initialize availability routes.
    Returns the router with all availability endpoints configured.
    """
    @router.post("")
    async def save_availability(request: Request, payload: AvailabilityRequest):
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            logger.info(f"Adding availability windows for user {user_email}")
            
            # Convert windows to database format
            new_windows = [
                {
                    "user_id": user_email,
                    "weekday": window.weekday,
                    "start_time": window.start_time,
                    "end_time": window.end_time
                }
                for window in payload.windows
            ]
            
            if new_windows:
                await db["availability_windows"].insert_many(new_windows)
                logger.info(f"Added {len(new_windows)} windows for user {user_email}")
            
            return {"status": "ok", "message": "Availability windows saved successfully"}
            
        except Exception as e:
            logger.error(f"Error saving availability: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/{window_id}")
    async def delete_availability_window(request: Request, window_id: str):
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            
            result = await db["availability_windows"].delete_one({
                "_id": ObjectId(window_id),
                "user_id": user_email
            })
            
            if result.deleted_count == 0:
                raise HTTPException(status_code=404, detail="Window not found")
            
            return {"status": "ok", "message": "Window deleted successfully"}
            
        except Exception as e:
            logger.error(f"Error deleting window: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("")
    async def get_availability(request: Request):
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            logger.info(f"Fetching availability windows for user {user_email}")
            
            windows = await db["availability_windows"].find(
                {"user_id": user_email}
            ).to_list(length=None)
            
            # Convert ObjectId to string for each window
            for w in windows:
                if "_id" in w:
                    w["_id"] = str(w["_id"])
            
            return {
                "status": "ok",
                "windows": windows
            }
            
        except Exception as e:
            logger.error(f"Error fetching availability: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
