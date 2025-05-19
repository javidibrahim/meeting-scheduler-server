from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
from routes import init_routes
from db.mongo import init_db, client


app = FastAPI()

# Load environment variables
load_dotenv()
FRONTEND_URL = os.getenv("FRONTEND_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

if not FRONTEND_URL:
    raise RuntimeError("FRONTEND_URL is not set in .env")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set in .env")

# Simple session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=14 * 24 * 60 * 60,
    same_site="none",
    https_only=True,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

db_connected = False

@app.on_event("startup")
async def startup():
    global db_connected
    if client:
        await init_db()
        db_connected = True
        init_routes(app, oauth)

def require_db():
    if not db_connected:
        raise HTTPException(status_code=503, detail="Database not available")
    return True

@app.get("/")
async def root():
    return {"status": "ok", "db_connected": db_connected}

@app.get("/me")
async def get_user(request: Request, _=Depends(require_db)):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@app.post("/logout")
async def logout(request: Request, _=Depends(require_db)):
    request.session.clear()
    return {"message": "Successfully logged out"}

# This ensures the app variable is accessible
app = app
