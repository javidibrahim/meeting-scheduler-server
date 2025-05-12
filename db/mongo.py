from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import asyncio
import logging

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

client = AsyncIOMotorClient(MONGO_URI)
db = client["meeting-scheduler"]

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db():
    """Initialize database collections and indexes"""
    try:
        # Create a unique index on slug+userId for schedule_links collection
        # This ensures that a user cannot have duplicate slugs
        await db.schedule_links.create_index(
            [("slug", 1), ("userId", 1)], 
            unique=True
        )
        logger.info("Created index on schedule_links collection")
    except Exception as e:
        logger.error(f"Error creating database indexes: {str(e)}")

# Run initialization in a new event loop if this file is executed directly
if __name__ == "__main__":
    asyncio.run(init_db())
