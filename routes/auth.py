from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import httpx
import os
import logging
from services.user_db import UserService
from google_auth_oauthlib.flow import Flow
from datetime import datetime
from urllib.parse import quote, urljoin
import secrets

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://meeting-scheduler-client-delta.vercel.app").rstrip('/')
BACKEND_URL = os.getenv("BACKEND_URL", "https://meeting-scheduler-server.fly.dev").rstrip('/')

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
HUBSPOT_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID")
HUBSPOT_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET")
HUBSPOT_SCOPES = "crm.objects.contacts.read crm.objects.contacts.write"

def init_auth_routes(oauth_client):
    user_service = UserService()

    @router.get("/google")
    async def google_auth(request: Request):
        try:
            redirect_uri = f"{BACKEND_URL}/auth/google/callback"
            # Generate a random state parameter
            state = secrets.token_urlsafe(32)
            request.session['oauth_state'] = state
            
            return await oauth_client.google.authorize_redirect(
                request,
                redirect_uri,
                access_type='offline',
                prompt='consent',
                state=state
            )
        except Exception as e:
            logger.error(f"Google auth error: {str(e)}")
            return RedirectResponse(url=f'{FRONTEND_URL}/?error=auth_failed&message={str(e)}')

    @router.get("/google/callback")
    async def google_callback(request: Request):
        try:
            # Verify state parameter
            state = request.session.pop('oauth_state', None)
            if not state:
                logger.error("No state parameter found in session")
                return RedirectResponse(url=urljoin(FRONTEND_URL, "/?error=auth_failed&message=Invalid state parameter"))
            
            # Get the state from the callback
            callback_state = request.query_params.get('state')
            if not callback_state or callback_state != state:
                logger.error(f"State mismatch: session={state}, callback={callback_state}")
                return RedirectResponse(url=urljoin(FRONTEND_URL, "/?error=auth_failed&message=State parameter mismatch"))
            
            token = await oauth_client.google.authorize_access_token(request)
            async with httpx.AsyncClient() as client:
                userinfo_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {token['access_token']}"}
                )
                if not userinfo_response.is_success:
                    raise Exception(f"Failed to get user info: {userinfo_response.text}")
                userinfo = userinfo_response.json()

                user = await user_service.create_or_update_google_user(
                    email=userinfo["email"],
                    google_id=userinfo["id"],
                    tokens={
                        "access_token": token['access_token'],
                        "refresh_token": token.get('refresh_token'),
                        "expires_in": token.get('expires_in', 3600)
                    }
                )

                if not user:
                    raise Exception("Failed to create/update user")

                request.session["user"] = {
                    "email": user["email"],
                    "name": userinfo.get("name"),
                    "picture": userinfo.get("picture")
                }

                # Fix: Use the frontend URL directly for the dashboard redirect
                logger.info(f"Redirecting to dashboard at: {FRONTEND_URL}/dashboard")
                return RedirectResponse(url=f"{FRONTEND_URL}/dashboard", status_code=302)

        except Exception as e:
            logger.error(f"Google callback error: {str(e)}")
            # Fix: Use the frontend URL directly for error redirects
            error_url = f"{FRONTEND_URL}/?error=auth_failed&message={quote(str(e))}"
            logger.info(f"Redirecting to error page: {error_url}")
            return RedirectResponse(url=error_url, status_code=302)

    @router.get("/hubspot")
    async def hubspot_auth(request: Request):
        user = request.session.get("user")
        if not user:
            return RedirectResponse(url=f'{FRONTEND_URL}/dashboard?error=not_authenticated')

        redirect_uri = f"{BACKEND_URL}/auth/hubspot/callback"
        auth_url = (
            f"https://app.hubspot.com/oauth/authorize"
            f"?client_id={HUBSPOT_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={HUBSPOT_SCOPES}"
        )

        return RedirectResponse(url=auth_url)

    @router.get("/hubspot/callback")
    async def hubspot_callback(request: Request, code: str):
        user = request.session.get("user")
        if not user:
            return RedirectResponse(url=f'{FRONTEND_URL}/dashboard?error=not_authenticated')

        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://api.hubapi.com/oauth/v1/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": HUBSPOT_CLIENT_ID,
                    "client_secret": HUBSPOT_CLIENT_SECRET,
                    "redirect_uri": f"{BACKEND_URL}/auth/hubspot/callback",
                    "code": code
                }
            )

            if not token_response.is_success:
                return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?error=token_exchange_failed")

            token_data = token_response.json()

            portal_response = await client.get(
                f"https://api.hubapi.com/oauth/v1/access-tokens/{token_data['access_token']}"
            )

            if not portal_response.is_success:
                return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?error=portal_fetch_failed")

            portal_data = portal_response.json()

            await user_service.update_hubspot_tokens(
                email=user["email"],
                tokens={
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_in": token_data.get("expires_in"),
                    "portal_id": portal_data["hub_id"],
                    "portal_name": portal_data["hub_domain"]
                }
            )

        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?success=hubspot_connected")

    @router.get("/hubspot/connection")
    async def get_hubspot_connection(request: Request):
        """Get HubSpot connection status for the current user"""
        try:
            user = request.session.get("user")
            if not user:
                logger.warning("No user in session for HubSpot connection check")
                raise HTTPException(status_code=401, detail="Not authenticated")

            logger.info(f"Checking HubSpot connection status for user {user['email']}")
            user_data = await user_service.get_user_tokens(user["email"])
            
            if not user_data:
                logger.info(f"No user data found for {user['email']}")
                return {"connected": False}
            
            if not user_data.get("hubspot"):
                logger.info(f"No HubSpot data found for {user['email']}")
                return {"connected": False}

            # Check if token is expired
            hubspot_data = user_data["hubspot"]
            expires_at = hubspot_data.get("expires_at", 0)
            current_time = datetime.utcnow().timestamp()
            
            logger.info(f"HubSpot token expires at {expires_at}, current time {current_time}")
            
            if expires_at < current_time:
                logger.info(f"HubSpot token expired for {user['email']}, removing connection")
                # Token is expired, remove it
                await user_service.update_hubspot_tokens(user["email"], {})
                return {"connected": False}

            logger.info(f"HubSpot connection active for {user['email']} with portal {hubspot_data.get('portal_name')}")
            return {
                "connected": True,
                "portal_name": hubspot_data.get("portal_name", "Unknown Portal")
            }

        except Exception as e:
            logger.error(f"Error getting HubSpot connection status: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/hubspot/connection")
    async def disconnect_hubspot(request: Request):
        """Disconnect HubSpot for the current user"""
        try:
            user = request.session.get("user")
            if not user:
                logger.warning("No user in session for HubSpot disconnect")
                raise HTTPException(status_code=401, detail="Not authenticated")

            logger.info(f"Disconnecting HubSpot for user {user['email']}")
            
            # Update user document to remove HubSpot data
            updated_user = await user_service.update_hubspot_tokens(user["email"], {})
            
            if not updated_user:
                logger.warning(f"No user found to disconnect HubSpot for {user['email']}")
                raise HTTPException(status_code=404, detail="User not found")
            
            logger.info(f"Successfully disconnected HubSpot for {user['email']}")
            return {"message": "Successfully disconnected from HubSpot"}

        except Exception as e:
            logger.error(f"Error disconnecting HubSpot: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/me")
    async def get_current_user(request: Request):
        try:
            user = request.session.get("user")
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            user_data = await user_service.get_user_by_email(user['email'])
            if not user_data:
                raise HTTPException(status_code=404, detail="User not found")

            return {
                **user_data,
                "name": user.get('name'),
                "picture": user.get('picture')
            }

        except Exception as e:
            logger.error(f"Error getting current user: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/logout")
    async def logout(request: Request):
        try:
            request.session.pop("user", None)
            return {"message": "Logged out successfully"}
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
