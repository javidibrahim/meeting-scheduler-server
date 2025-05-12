from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
import httpx
from routes import init_routes
import logging
from db.mongo import init_db

# Load environment variables
load_dotenv()

app = FastAPI()
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5179")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "your-secret-key-here"),
    session_cookie="google_oauth_session",
    max_age=14 * 24 * 60 * 60,
    same_site="lax",
    https_only=False,   
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
        
    # Log detailed error information
    logger.error(f"[VALIDATION ERROR] Path: {request.url.path}")
    logger.error(f"[VALIDATION ERROR] Body: {body_str}")
    logger.error(f"[VALIDATION ERROR] Details: {exc.errors()}")
    
    # Return validation error with details
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body_str}
    )

# Initialize all routes
init_routes(app, oauth)

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await init_db()

@app.get("/me")
async def get_user(request: Request):
    """Get current user info from session"""
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@app.post("/logout")
async def logout(request: Request):
    """Clear session and logout user"""
    request.session.clear()
    return {"message": "Successfully logged out"}
