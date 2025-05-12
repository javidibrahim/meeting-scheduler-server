from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
from routes import init_routes
from db.mongo import init_db, get_db
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track database connection status
db_connected = False

app = FastAPI()
FRONTEND_URL = os.getenv("FRONTEND_URL")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "your-secret-key-here"),
    session_cookie="google_oauth_session",
    max_age=14 * 24 * 60 * 60,
    same_site="lax",
    https_only=os.getenv("ENVIRONMENT", "development") == "production",   
    path="/"   
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600
)

oauth = OAuth()

oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile https://www.googleapis.com/auth/calendar.readonly',
        'token_endpoint_auth_method': 'client_secret_post'
    }
)

# Add exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors and log detailed information"""
    try:
        body = await request.body()
        body_str = body.decode()
    except:
        body_str = "Could not decode request body"
    
    # Return validation error with details
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body_str}
    )

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    global db_connected
    try:
        # Try to initialize the database, but don't let failures stop the app
        await init_db()
        db_connected = True
        logger.info("Database initialized successfully")
        
        # Only initialize routes that require DB connection if DB is connected
        logger.info("Initializing routes...")
        init_routes(app, oauth)
        logger.info("Routes initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        # Continue running even if DB connection fails, but only initialize basic routes
        logger.warning("Application starting without database connection")
        
        # Initialize only basic routes
        logger.info("Initializing only basic routes due to DB connection failure")

# Dependency to check if database is connected
def require_db():
    if not db_connected:
        raise HTTPException(
            status_code=503, 
            detail="Database is not available. Please try again later."
        )
    return True

@app.get("/")
async def root():
    """Root endpoint for health checks"""
    logger.info("Health check endpoint accessed")
    return {
        "status": "ok", 
        "message": "API is running", 
        "db_connected": db_connected,
        "env": os.getenv("ENVIRONMENT", "development")
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for Render"""
    logger.info("Health check endpoint accessed")
    return {"status": "ok", "db_connected": db_connected}

@app.get("/db-status")
async def db_status():
    """Detailed database status endpoint"""
    return {
        "connected": db_connected,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "mongo_uri_set": bool(os.getenv("MONGO_URI"))
    }

@app.get("/me")
async def get_user(request: Request, _=Depends(require_db)):
    """Get current user info from session"""
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@app.post("/logout")
async def logout(request: Request, _=Depends(require_db)):
    """Clear session and logout user"""
    request.session.clear()
    return {"message": "Successfully logged out"}

app = app
