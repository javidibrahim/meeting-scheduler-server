from fastapi import FastAPI
from routes.auth import init_auth_routes
from routes.calendar import init_calendar_routes
from routes.events import init_events_routes
from routes.availability import init_availability_routes
from routes.schedule_links import init_schedule_links_routes
from routes.public import init_public_routes
from routes.meetings import init_meetings_routes

def init_routes(app: FastAPI, oauth_client):
    """Initialize all application routes"""
    # Initialize auth routes
    auth_router = init_auth_routes(oauth_client)
    app.include_router(auth_router)
    
    # Initialize calendar routes
    calendar_router = init_calendar_routes(oauth_client)
    app.include_router(calendar_router)
    
    # Initialize events routes
    events_router = init_events_routes(oauth_client)
    app.include_router(events_router)
    
    # Initialize availability routes
    availability_router = init_availability_routes()
    app.include_router(availability_router)
    
    # Initialize schedule links routes
    schedule_links_router = init_schedule_links_routes()
    app.include_router(schedule_links_router)
    
    # Initialize meetings routes
    meetings_router = init_meetings_routes()
    app.include_router(meetings_router)
    
    # Initialize public routes (no authentication required)
    public_router = init_public_routes()
    app.include_router(public_router)

    
    return app