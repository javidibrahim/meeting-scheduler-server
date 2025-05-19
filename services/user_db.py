from datetime import datetime
from typing import Optional, Dict, Any
from db.mongo import db
import logging

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self):
        self.collection_name = "users"
        self.collection = db[self.collection_name]

    async def create_or_update_google_user(
        self,
        email: str,
        google_id: str,
        tokens: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create or update a user with Google OAuth information.
        Returns the user document without sensitive data.
        """
        now = datetime.utcnow()
        
        # Prepare the update document
        update_doc = {
            "email": email,
            "google": {
                "id": google_id,
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"),
                "expires_at": datetime.utcnow().timestamp() + tokens.get("expires_in", 3600)
            },
            "updated_at": now
        }

        try:
            # Try to find existing user
            existing_user = await self.collection.find_one({"email": email})
            
            if existing_user:
                # Update existing user
                await self.collection.update_one(
                    {"email": email},
                    {"$set": update_doc}
                )
                logger.info(f"Updated Google tokens for user {email}")
            else:
                # Create new user
                new_user = {
                    **update_doc,
                    "created_at": now
                }
                await self.collection.insert_one(new_user)
                logger.info(f"Created new user {email}")

            # Get the updated/created document
            user = await self.collection.find_one({"email": email})
            
            # Remove sensitive data before returning
            if user:
                user.pop("google", None)
                user.pop("hubspot", None)
                # Convert ObjectId to string for JSON serialization
                user["_id"] = str(user["_id"])
            
            return user

        except Exception as e:
            logger.error(f"Error in create_or_update_google_user: {str(e)}")
            raise

    async def update_hubspot_tokens(
        self,
        email: str,
        tokens: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update HubSpot tokens for a user.
        Returns the updated user document without sensitive data.
        """
        try:
            now = datetime.utcnow()
            
            if not tokens:
                # If tokens is empty, remove hubspot data
                update_doc = {
                    "$unset": {"hubspot": ""},
                    "$set": {"updated_at": now}
                }
            else:
                # If tokens provided, update hubspot data
                expires_at = now.timestamp() + tokens.get("expires_in", 3600)
                update_doc = {
                    "$set": {
                        "hubspot": {
                            "access_token": tokens.get("access_token"),
                            "refresh_token": tokens.get("refresh_token"),
                            "expires_at": expires_at,
                            "portal_id": tokens.get("portal_id"),
                            "portal_name": tokens.get("portal_name")
                        },
                        "updated_at": now
                    }
                }

            result = await self.collection.update_one(
                {"email": email},
                update_doc
            )

            if result.modified_count > 0 or result.matched_count > 0:
                user = await self.collection.find_one({"email": email})
                if user:
                    # Remove sensitive data
                    user.pop("google", None)
                    user.pop("hubspot", None)
                    user["_id"] = str(user["_id"])
                return user
            
            logger.warning(f"No user found to update HubSpot tokens for {email}")
            return None

        except Exception as e:
            logger.error(f"Error updating HubSpot tokens: {str(e)}")
            raise

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email, excluding sensitive data"""
        try:
            user = await self.collection.find_one({"email": email})
            if user:
                # Remove sensitive data
                user.pop("google", None)
                user.pop("hubspot", None)
                user["_id"] = str(user["_id"])
            return user
        except Exception as e:
            logger.error(f"Error getting user by email: {str(e)}")
            raise

    async def get_user_tokens(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user's OAuth tokens (for internal use only)"""
        try:
            user = await self.collection.find_one(
                {"email": email},
                {"google": 1, "hubspot": 1}
            )
            return user
        except Exception as e:
            logger.error(f"Error getting user tokens: {str(e)}")
            raise

    async def delete_user(self, email: str) -> bool:
        """Delete a user by email"""
        try:
            result = await self.collection.delete_one({"email": email})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting user: {str(e)}")
            raise