from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import asyncio
import logging
import certifi

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure MongoDB client with SSL
client = AsyncIOMotorClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    tlsAllowInvalidCertificates=False,
    tlsAllowInvalidHostnames=False,
    serverSelectionTimeoutMS=30000,
    connectTimeoutMS=30000,
    socketTimeoutMS=30000,
    maxPoolSize=50,
    minPoolSize=10,
    retryWrites=True,
    retryReads=True
)

# Add connection error handling
async def verify_connection():
    """Verify MongoDB connection and log detailed error if it fails"""
    try:
        await client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        return True
    except Exception as e:
        logger.error(f"MongoDB connection error: {str(e)}")
        logger.error(f"MongoDB URI (masked): {MONGO_URI.replace('mongodb+srv://', 'mongodb+srv://***:***@')}")
        logger.error(f"SSL/TLS settings: tls={client.options.tls}, tlsCAFile={client.options.tls_ca_file}")
        raise

db = client["meeting-scheduler"]

def get_db():
    """Get the database instance"""
    return db

async def init_db():
    """Initialize database collections and indexes"""
    try:
        # Test the connection with detailed error logging
        await verify_connection()
        
        # Create a unique index on slug+userId for schedule_links collection
        await db.schedule_links.create_index(
            [("slug", 1), ("userId", 1)], 
            unique=True
        )
        logger.info("Created index on schedule_links collection")
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {str(e)}")
        raise

# Run initialization in a new event loop if this file is executed directly
if __name__ == "__main__":
    asyncio.run(init_db())
