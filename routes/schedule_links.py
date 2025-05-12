from fastapi import APIRouter, Depends, HTTPException, Request
from models.schedule_links import ScheduleLink, DateEncoder
from db.mongo import db
from typing import List
from datetime import datetime, date
import logging
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule-links", tags=["schedule-links"])

def init_schedule_links_routes():
    """
    Initialize schedule links routes.
    Returns the router with all schedule links endpoints configured.
    """
    
    @router.get("")
    async def get_schedule_links(request: Request):
        """Get all schedule links for the current user"""
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            logger.info(f"Fetching schedule links for user {user_email}")
            
            links = await db["schedule_links"].find(
                {"userId": user_email}
            ).to_list(length=None)
            
            # Convert ObjectId to string for each link
            for link in links:
                if "_id" in link:
                    link["_id"] = str(link["_id"])
            
            return {
                "status": "ok",
                "links": links
            }
            
        except Exception as e:
            logger.error(f"Error fetching schedule links: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("")
    async def create_schedule_link(request: Request, link: ScheduleLink):
        """Create a new schedule link"""
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            logger.info(f"Creating schedule link for user {user_email}")
            
            # Check if slug already exists for this user
            existing_link = await db["schedule_links"].find_one({
                "userId": user_email,
                "slug": link.slug
            })
            
            if existing_link:
                raise HTTPException(
                    status_code=400, 
                    detail=f"A link with slug '{link.slug}' already exists"
                )
            
            # Convert to database format
            now = datetime.utcnow()
            link_data = link.dict()
            
            # Convert date objects to ISO format strings for MongoDB
            if link_data.get('expirationDate'):
                if isinstance(link_data['expirationDate'], date):
                    link_data['expirationDate'] = link_data['expirationDate'].isoformat()
            
            link_data.update({
                "userId": user_email,
                "createdAt": now,
                "updatedAt": now,
                "uses": 0
            })
            
            result = await db["schedule_links"].insert_one(link_data)
            link_data["_id"] = str(result.inserted_id)
            
            return link_data
            
        except HTTPException as he:
            # Re-raise HTTP exceptions directly
            raise
        except DuplicateKeyError:
            raise HTTPException(
                status_code=400, 
                detail=f"A link with slug '{link.slug}' already exists"
            )
        except Exception as e:
            logger.error(f"Error creating schedule link: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.put("/{link_id}")
    async def update_schedule_link(request: Request, link_id: str, link: ScheduleLink):
        """Update an existing schedule link"""
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            logger.info(f"Updating schedule link for user {user_email}")
            
            # Check if the link exists and belongs to the user
            existing_link = await db["schedule_links"].find_one({
                "_id": ObjectId(link_id),
                "userId": user_email
            })
            
            if not existing_link:
                raise HTTPException(status_code=404, detail="Schedule link not found")
            
            # Check if updated slug conflicts with another link
            if link.slug != existing_link["slug"]:
                slug_check = await db["schedule_links"].find_one({
                    "userId": user_email,
                    "slug": link.slug,
                    "_id": {"$ne": ObjectId(link_id)}
                })
                
                if slug_check:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"A link with slug '{link.slug}' already exists"
                    )
            
            # Update link data
            now = datetime.utcnow()
            link_data = link.dict()
            
            # Convert date objects to ISO format strings for MongoDB
            if link_data.get('expirationDate'):
                if isinstance(link_data['expirationDate'], date):
                    link_data['expirationDate'] = link_data['expirationDate'].isoformat()
                    
            link_data["updatedAt"] = now
            
            # Preserve created date and uses count
            link_data["createdAt"] = existing_link.get("createdAt", now)
            link_data["uses"] = existing_link.get("uses", 0)
            
            await db["schedule_links"].update_one(
                {"_id": ObjectId(link_id)},
                {"$set": link_data}
            )
            
            # Return updated link
            link_data["_id"] = link_id
            link_data["userId"] = user_email
            
            return link_data
            
        except HTTPException as he:
            # Re-raise HTTP exceptions directly
            raise
        except Exception as e:
            logger.error(f"Error updating schedule link: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.delete("/{link_id}")
    async def delete_schedule_link(request: Request, link_id: str):
        """Delete a schedule link"""
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            
            result = await db["schedule_links"].delete_one({
                "_id": ObjectId(link_id),
                "userId": user_email
            })
            
            if result.deleted_count == 0:
                raise HTTPException(status_code=404, detail="Schedule link not found")
            
            return {"status": "ok", "message": "Schedule link deleted successfully"}
            
        except HTTPException as he:
            # Re-raise HTTP exceptions directly
            raise
        except Exception as e:
            logger.error(f"Error deleting schedule link: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/{link_id}")
    async def get_schedule_link(request: Request, link_id: str):
        """Get a specific schedule link by ID"""
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_email = user['email']
            
            link = await db["schedule_links"].find_one({
                "_id": ObjectId(link_id),
                "userId": user_email
            })
            
            if not link:
                raise HTTPException(status_code=404, detail="Schedule link not found")
            
            # Convert ObjectId to string
            link["_id"] = str(link["_id"])
            
            return link
            
        except HTTPException as he:
            # Re-raise HTTP exceptions directly
            raise
        except Exception as e:
            logger.error(f"Error fetching schedule link: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/public/{slug}")
    async def get_public_schedule_link(request: Request, slug: str):
        """Get a public schedule link by slug and increment visit counter"""
        try:
            # Find the link by slug
            link = await db["schedule_links"].find_one({"slug": slug})
            
            if not link:
                raise HTTPException(status_code=404, detail="Schedule link not found")
            
            # Check if link has expired
            if link.get("expirationDate"):
                expiration_date = datetime.fromisoformat(link["expirationDate"]) if isinstance(link["expirationDate"], str) else link["expirationDate"]
                if expiration_date.date() < datetime.now().date():
                    raise HTTPException(status_code=400, detail="This link has expired")
            
            # Check if link has reached maximum uses
            if link.get("maxUses") and link.get("uses", 0) >= link["maxUses"]:
                raise HTTPException(status_code=400, detail="This link has reached its maximum number of uses")
            
            # Increment the visit counter
            await db["schedule_links"].update_one(
                {"_id": link["_id"]},
                {"$inc": {"uses": 1}}
            )
            
            # Prepare the response - only include necessary fields for public usage
            public_link = {
                "slug": link["slug"],
                "meetingLength": link["meetingLength"],
                "maxDaysInAdvance": link.get("maxDaysInAdvance", 30),
                "customQuestions": link.get("customQuestions", [])
            }
            
            return public_link
            
        except HTTPException as he:
            # Re-raise HTTP exceptions directly
            raise
        except Exception as e:
            logger.error(f"Error fetching public schedule link: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("/increment-use/{slug}")
    async def increment_link_usage(request: Request, slug: str):
        """Increment the use counter for a schedule link"""
        try:
            # Find the link by slug
            link = await db["schedule_links"].find_one({"slug": slug})
            
            if not link:
                raise HTTPException(status_code=404, detail="Schedule link not found")
            
            # Check if link has expired
            if link.get("expirationDate"):
                expiration_date = datetime.fromisoformat(link["expirationDate"]) if isinstance(link["expirationDate"], str) else link["expirationDate"]
                if expiration_date.date() < datetime.now().date():
                    raise HTTPException(status_code=400, detail="This link has expired")
            
            # Check if link has reached maximum uses
            if link.get("maxUses") and link.get("uses", 0) >= link["maxUses"]:
                raise HTTPException(status_code=400, detail="This link has reached its maximum number of uses")
            
            # Increment the use counter
            result = await db["schedule_links"].update_one(
                {"_id": link["_id"]},
                {"$inc": {"uses": 1}}
            )
            
            if result.modified_count == 0:
                raise HTTPException(status_code=500, detail="Failed to increment link usage")
            
            return {"status": "ok", "message": "Link usage incremented"}
            
        except HTTPException as he:
            # Re-raise HTTP exceptions directly
            raise
        except Exception as e:
            logger.error(f"Error incrementing link usage: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return router 