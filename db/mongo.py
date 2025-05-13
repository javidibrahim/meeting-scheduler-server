from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import logging
import certifi
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Log basic info
logger.info(f"Python version: {sys.version}")
logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
logger.info(f"MongoDB URI exists: {MONGO_URI is not None}")

# Initialize MongoDB client
try:
    if not MONGO_URI:
        logger.error("MONGO_URI environment variable is not set")
        client = None
        db = None
    else:
        logger.info("Connecting to MongoDB...")
        client = AsyncIOMotorClient(
            MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),  # Use system CA certificates
            connectTimeoutMS=30000,
            serverSelectionTimeoutMS=30000,
            retryWrites=True,
            retryReads=True
        )
        db = client.get_database("meeting-scheduler")
        logger.info("MongoDB connected successfully")
except Exception as e:
    logger.error(f"MongoDB connection error: {str(e)}")
    client = None
    db = None

async def verify_connection():
    """Verify MongoDB connection"""
    if not client:
        logger.error("MongoDB client not initialized")
        raise ValueError("MongoDB client not initialized")

    try:
        await client.admin.command('ping')
        logger.info("MongoDB connection verified")
        return True
    except Exception as e:
        logger.error(f"MongoDB connection verification failed: {str(e)}")
        raise

def get_db():
    """Get database instance"""
    if not db:
        logger.error("Database not initialized")
    return db

async def init_db():
    """Initialize database collections and indexes"""
    if client is None or db is None:
        logger.error("Database not initialized")
        raise ValueError("Database not initialized")
        
    try:
        await verify_connection()
        logger.info("Creating database indexes...")
        await db.schedule_links.create_index(
            [("slug", 1), ("userId", 1)], 
            unique=True
        )
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise

# Initialize database if run directly
if __name__ == "__main__":
    import asyncio
    if client and db:
        asyncio.run(init_db())
    else:
        logger.error("Cannot initialize database - client or db not initialized")
