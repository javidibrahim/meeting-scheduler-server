from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import asyncio
import logging
import certifi
import ssl
import re

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to fix common MongoDB URI issues
def get_fixed_uri(uri):
    if not uri:
        logger.error("MongoDB URI is not set")
        return None
    
    # Create a masked version for logging
    masked_uri = re.sub(r'://([^:]+):([^@]+)@', r'://***:***@', uri)
    logger.info(f"Original URI format (masked): {masked_uri}")
    
    # Check if it's already using the new connection string format
    if "mongodb+srv://" in uri and "retryWrites=true" in uri:
        # Try removing the appName parameter which might cause issues
        if "appName=" in uri:
            new_uri = re.sub(r'&appName=[^&]+', '', uri)
            if new_uri != uri:
                logger.info("Removed appName parameter from connection string")
                uri = new_uri
    
    # Add srv connection options if missing
    if "mongodb+srv://" in uri and "?" not in uri:
        uri += "/?retryWrites=true&w=majority"
        logger.info("Added standard parameters to srv connection string")
    
    # Log the masked modified URI
    masked_uri = re.sub(r'://([^:]+):([^@]+)@', r'://***:***@', uri)
    logger.info(f"Using modified URI format (masked): {masked_uri}")
    
    return uri

# Configure MongoDB client with permissive SSL settings for testing
try:
    # Try to fix common URI issues
    fixed_uri = get_fixed_uri(MONGO_URI)
    
    if fixed_uri:
        # Create a client with very permissive settings for testing
        client = AsyncIOMotorClient(
            fixed_uri,
            tlsAllowInvalidCertificates=True,
            tlsInsecure=True,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            serverSelectionTimeoutMS=10000,
            ssl=True
        )
        logger.info("MongoDB client initialized with permissive SSL settings")
    else:
        # Create a dummy client that will fail gracefully
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        logger.warning("Using fallback MongoDB client due to invalid URI")
except Exception as e:
    logger.error(f"Error initializing MongoDB client: {str(e)}")
    # Create a dummy client that will fail gracefully
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    logger.warning("Using fallback MongoDB client due to exception")

# Initialize the database object
db = client.get_database("meeting-scheduler") if MONGO_URI else None

# Add connection verification function
async def verify_connection():
    """Verify MongoDB connection and log detailed error if it fails"""
    if not MONGO_URI:
        logger.error("MongoDB URI is not set")
        raise ValueError("MongoDB URI is not set")
        
    try:
        # Try a simple ping command
        await client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        return True
    except Exception as e:
        logger.error(f"MongoDB connection error: {str(e)}")
        # Log some details for debugging
        if MONGO_URI:
            masked_uri = re.sub(r'://([^:]+):([^@]+)@', r'://***:***@', MONGO_URI)
            logger.error(f"MongoDB URI (masked): {masked_uri}")
        else:
            logger.error("MongoDB URI is not set")
        raise

def get_db():
    """Get the database instance"""
    if not db:
        logger.error("Database not initialized")
    return db

async def init_db():
    """Initialize database collections and indexes"""
    if not MONGO_URI:
        logger.error("MongoDB URI is not set, skipping database initialization")
        raise ValueError("MongoDB URI is not set")
        
    try:
        # Test the connection
        await verify_connection()
        
        # Create a unique index on slug+userId for schedule_links collection
        await db.schedule_links.create_index(
            [("slug", 1), ("userId", 1)], 
            unique=True
        )
        logger.info("Created index on schedule_links collection")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise

# Run initialization in a new event loop if this file is executed directly
if __name__ == "__main__":
    asyncio.run(init_db())
