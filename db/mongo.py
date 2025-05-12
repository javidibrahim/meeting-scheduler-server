from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import asyncio
import logging
import certifi
import ssl
from pymongo.errors import ServerSelectionTimeoutError
from contextlib import asynccontextmanager

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure SSL context
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3
ssl_context.verify_mode = ssl.CERT_REQUIRED

# Global connection pool
client = None
db = None

async def init_db():
    """Initialize database connection and indexes"""
    global client, db
    try:
        # Create a new client with connection pooling
        client = AsyncIOMotorClient(
            MONGO_URI,
            tls=True,
            tlsInsecure=False,
            tlsAllowInvalidCertificates=False,
            tlsCAFile=certifi.where(),
            ssl_cert_reqs=ssl.CERT_REQUIRED,
            ssl_ca_certs=certifi.where(),
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=30000,
            socketTimeoutMS=30000,
            maxPoolSize=50,
            minPoolSize=10,
            retryWrites=True,
            retryReads=True,
            ssl_context=ssl_context
        )
        
        # Test the connection
        await client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        
        # Set up database
        db = client["meeting-scheduler"]
        
        # Create indexes
        await db.schedule_links.create_index(
            [("slug", 1), ("userId", 1)], 
            unique=True
        )
        logger.info("Created index on schedule_links collection")
        
        # Create email index on users collection
        await db.users.create_index("email", unique=True)
        logger.info("Created index on users collection")
        
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

@asynccontextmanager
async def get_db():
    """Get a database connection from the pool"""
    global client, db
    if not client or not db:
        await init_db()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database operation error: {str(e)}")
        raise

# Run initialization in a new event loop if this file is executed directly
if __name__ == "__main__":
    asyncio.run(init_db())
