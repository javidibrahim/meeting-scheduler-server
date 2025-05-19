from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import httpx
import os
import logging
from services.user_db import UserService
from urllib.parse import urljoin
from datetime import datetime
import secrets

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
FRONTEND_URL = os.getenv("FRONTEND_URL")
BACKEND_URL = os.getenv("BACKEND_URL")
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
            state = secrets.token_urlsafe(16)
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
            return RedirectResponse(url=f'{FRONTEND_URL}/?error=auth_failed')

    @router.get("/google/callback")
    async def google_callback(request: Request):
        try:
            token = await oauth_client.google.authorize_access_token(request)

            async with httpx.AsyncClient() as client:
                userinfo_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {token['access_token']}"}
                )
                if not userinfo_response.is_success:
                    raise Exception("Failed to get user info")

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

                request.session["user"] = {
                    "email": user["email"],
                    "name": userinfo.get("name"),
                    "picture": userinfo.get("picture")
                }

                return RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
        except Exception as e:
            logger.error(f"Callback error: {str(e)}")
            return RedirectResponse(url=f'{FRONTEND_URL}/?error=auth_failed')

    @router.get("/me")
    async def get_current_user(request: Request):
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

    @router.post("/logout")
    async def logout(request: Request):
        request.session.pop("user", None)
        return {"message": "Logged out successfully"}

    # Optional: Keep HubSpot if you're using it
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
    async def hubspot_connection(request: Request):
        user = request.session.get("user")
        if not user:
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?error=not_authenticated")

        return await user_service.get_hubspot_connection(user["email"])

    return router
