from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import asyncio
import logging
import certifi
import ssl
import re
import urllib.parse
import sys
import json

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Log environment info
logger.info(f"Python version: {sys.version}")
logger.info(f"Running in environment: {os.getenv('ENVIRONMENT', 'development')}")
logger.info(f"Certifi CA file path: {certifi.where()}")
logger.info(f"MongoDB URI exists: {bool(MONGO_URI)}")

if MONGO_URI:
    # Log masked version of the URI for debugging
    masked_uri = re.sub(r'://([^:]+):([^@]+)@', r'://***:***@', MONGO_URI)
    logger.info(f"MongoDB URI (masked): {masked_uri}")
    
    # Check URI format
    if "mongodb+srv://" in MONGO_URI:
        logger.info("Using MongoDB SRV connection string format")
    elif "mongodb://" in MONGO_URI:
        logger.info("Using MongoDB standard connection string format")
    else:
        logger.error("MongoDB URI is not in a recognized format")

# Configure MongoDB client
try:
    # Check if we have a valid MongoDB URI
    if not MONGO_URI:
        logger.error("MONGO_URI environment variable is not set")
        client = None
        db = None
    else:
        # Log connection attempt
        logger.info("Attempting to create MongoDB client")
        
        # Create MongoDB client with minimal options
        client_params = {
            "tlsCAFile": certifi.where(),
            "tlsAllowInvalidCertificates": False,
            "tlsAllowInvalidHostnames": False,
            "tlsInsecure": False,
            "connectTimeoutMS": 30000,
            "serverSelectionTimeoutMS": 30000,
            "ssl": True,
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
            "ssl_ca_certs": certifi.where()
        }
        logger.info(f"MongoDB connection params: {json.dumps({k: v for k, v in client_params.items() if k != 'ssl_ca_certs'}, default=str)}")
        
        # Create the client
        client = AsyncIOMotorClient(
            MONGO_URI,
            **client_params
        )
        
        # Get database instance
        logger.info("Getting database instance")
        db = client.get_database("meeting-scheduler")
        logger.info("MongoDB client and database initialized")
except Exception as e:
    logger.exception(f"Error initializing MongoDB client: {str(e)}")
    client = None
    db = None

async def verify_connection():
    """Verify MongoDB connection and log detailed error if it fails"""
    if not client:
        logger.error("MongoDB client is not initialized")
        raise ValueError("MongoDB client is not initialized")

    logger.info("Verifying MongoDB connection...")    
    try:
        # Try a simple ping command with timeout
        logger.debug("Sending ping command to MongoDB")
        start_time = asyncio.get_event_loop().time()
        await asyncio.wait_for(client.admin.command('ping'), timeout=10.0)
        end_time = asyncio.get_event_loop().time()
        logger.info(f"Successfully connected to MongoDB (ping took {end_time - start_time:.2f}s)")
        return True
    except asyncio.TimeoutError:
        logger.error("MongoDB ping command timed out after 10 seconds")
        raise
    except Exception as e:
        logger.exception(f"MongoDB connection error: {str(e)}")
        # Log detailed connection info for debugging
        if client:
            try:
                logger.debug(f"MongoDB client: {client}")
                logger.debug(f"MongoDB nodes: {client.nodes}")
            except:
                pass
        raise

def get_db():
    """Get the database instance"""
    if not db:
        logger.error("Database not initialized")
    return db

async def init_db():
    """Initialize database collections and indexes"""
    if client is None or db is None:
        msg = "MongoDB client or database is not initialized"
        logger.error(msg)
        raise ValueError(msg)
        
    try:
        # Test the connection
        logger.info("Verifying connection before initializing database")
        await verify_connection()
        
        # Create a unique index on slug+userId for schedule_links collection
        logger.info("Creating index on schedule_links collection")
        await db.schedule_links.create_index(
            [("slug", 1), ("userId", 1)], 
            unique=True
        )
        logger.info("Created index on schedule_links collection")
    except Exception as e:
        logger.exception(f"Database initialization error: {str(e)}")
        raise

# Run initialization in a new event loop if this file is executed directly
if __name__ == "__main__":
    if client and db:
        logger.info("Running database initialization from main")
        asyncio.run(init_db())
    else:
        logger.error("Cannot initialize database - client or db not initialized")
