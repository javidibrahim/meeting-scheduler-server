from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
import os
import sys
import platform
from dotenv import load_dotenv
from routes import init_routes
from db.mongo import init_db, get_db, client
import logging
import traceback
from urllib.parse import urlparse


app = FastAPI(
    title="Meeting Scheduler API",
    description="API for scheduling meetings",
    version="1.0.0",
)

# Load environment variables based on ENVIRONMENT
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
env_file = f".env.{ENVIRONMENT}"
load_dotenv(env_file)

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG if ENVIRONMENT == "development" else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Log system information for debugging
logger.info(f"Loading environment from: {env_file}")
logger.info(f"Environment: {ENVIRONMENT}")
logger.info(f"Python version: {sys.version}")
logger.info(f"Platform: {platform.platform()}")

# Get environment variables
FRONTEND_URL = os.getenv("FRONTEND_URL")
BACKEND_URL = os.getenv("BACKEND_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

# Extract domain from BACKEND_URL for cookie settings
backend_domain = urlparse(BACKEND_URL).netloc if BACKEND_URL else None
logger.info(f"Backend domain for cookies: {backend_domain}")

# Validate required environment variables
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")
if not FRONTEND_URL:
    raise ValueError("FRONTEND_URL environment variable is required")
if not BACKEND_URL:
    raise ValueError("BACKEND_URL environment variable is required")

logger.info(f"Frontend URL: {FRONTEND_URL}")
logger.info(f"Backend URL: {BACKEND_URL}")
logger.info(f"MongoDB URI set: {bool(os.getenv('MONGO_URI'))}")

# Configure session middleware with proper domain settings
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="session",
    max_age=14 * 24 * 60 * 60,  # 14 days
    same_site="none" if ENVIRONMENT == "production" else "lax",
    https_only=ENVIRONMENT == "production",
    path="/",
    domain=backend_domain if ENVIRONMENT == "production" else None  # Use exact backend domain
)

# Configure CORS with proper settings for cross-domain requests
origins = [FRONTEND_URL]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600
)

# Configure OAuth
oauth = OAuth()

google_client_id = os.getenv("GOOGLE_CLIENT_ID")
google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

if google_client_id and google_client_secret:
    oauth.register(
        name='google',
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile https://www.googleapis.com/auth/calendar.readonly',
            'token_endpoint_auth_method': 'client_secret_post'
        }
    )
else:
    logger.warning("Google OAuth credentials not found - OAuth functionality will be limited")

# Add exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors and log detailed information"""
    logger.error(f"Validation error: {exc}")
    try:
        body = await request.body()
        body_str = body.decode()
        logger.error(f"Request body: {body_str}")
    except:
        body_str = "Could not decode request body"
        logger.error("Failed to decode request body")
    
    # Return validation error with details
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body_str}
    )

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    global db_connected
    logger.info("Application startup event triggered")
    
    try:
        # First check if the MongoDB client was initialized
        if client is None:
            logger.error("MongoDB client not initialized - check your MONGO_URI environment variable")
            logger.warning("Application starting without database connection")
            return

        # Try to initialize the database, but don't let failures stop the app
        logger.info("Initializing database")
        await init_db()
        db_connected = True
        logger.info("Database initialized successfully")
        
        # Only initialize routes that require DB connection if DB is connected
        logger.info("Initializing routes...")
        init_routes(app, oauth)
        logger.info("Routes initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        logger.error(f"Exception traceback: {traceback.format_exc()}")
        # Continue running even if DB connection fails, but only initialize basic routes
        logger.warning("Application starting without database connection")
        
        # Initialize only basic routes
        logger.info("Initializing only basic routes due to DB connection failure")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on application shutdown"""
    logger.info("Application shutting down")
    # Add any cleanup code here

# Dependency to check if database is connected
def require_db():
    if not db_connected:
        logger.warning("API request rejected due to missing database connection")
        raise HTTPException(
            status_code=503, 
            detail="Database is not available. Please try again later."
        )
    return True

@app.get("/")
async def root():
    """Root endpoint for health checks"""
    logger.info("Health check endpoint (root) accessed")
    response = {
        "status": "ok", 
        "message": "API is running", 
        "db_connected": db_connected,
        "env": os.getenv("ENVIRONMENT", "development"),
        "mongo_uri_set": bool(os.getenv("MONGO_URI"))
    }
    logger.info(f"Health check response: {response}")
    return response

@app.get("/health")
async def health_check():
    """Health check endpoint for Render"""
    logger.info("Health check endpoint accessed")
    return {"status": "ok", "db_connected": db_connected}

@app.get("/db-status")
async def db_status():
    """Detailed database status endpoint"""
    logger.info("Database status endpoint accessed")
    
    # Get detailed status info
    status_info = {
        "connected": db_connected,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "mongo_uri_set": bool(os.getenv("MONGO_URI")),
        "client_initialized": client is not None,
        "python_version": sys.version,
        "platform": platform.platform()
    }
    
    # Try to get more info from the client if available
    if client:
        try:
            status_info["client_address"] = str(client.address)
        except:
            status_info["client_address"] = "Unable to retrieve"
    
    logger.info(f"Database status: {status_info}")
    return status_info

@app.get("/me")
async def get_user(request: Request, _=Depends(require_db)):
    """Get current user info from session"""
    logger.info("User info endpoint accessed")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Request cookies: {request.cookies}")
    logger.info(f"Session data: {request.session}")
    
    user = request.session.get('user')
    if not user:
        logger.warning("User not authenticated - no user in session")
        logger.warning(f"Session ID: {request.session.get('id', 'no session id')}")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    logger.info(f"Returning user info for user: {user.get('email', 'unknown')}")
    return user

@app.post("/logout")
async def logout(request: Request, _=Depends(require_db)):
    """Clear session and logout user"""
    logger.info("Logout endpoint accessed")
    request.session.clear()
    logger.info("User session cleared")
    return {"message": "Successfully logged out"}

# This line ensures the app variable is accessible by both uvicorn when run directly
# and when imported by other modules
app = app
