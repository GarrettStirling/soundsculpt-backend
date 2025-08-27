from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from app.services.spotify_service import SpotifyService
from typing import Dict
import os

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Initialize Spotify service
spotify_service = SpotifyService()

@router.get("/login")
async def login():
    """Initiate Spotify OAuth login"""
    try:
        auth_url = spotify_service.get_auth_url()
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

@router.get("/redirect")
async def login_redirect():
    """Redirect to Spotify OAuth login"""
    try:
        auth_url = spotify_service.get_auth_url()
        return RedirectResponse(url=auth_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

@router.get("/callback")
async def callback(code: str = Query(...), state: str = Query(None)):
    """Handle Spotify OAuth callback"""
    try:
        # Exchange code for access token
        token_info = spotify_service.get_access_token(code)
        
        if not token_info:
            raise HTTPException(status_code=400, detail="Failed to get access token")
        
        # In a real app, you'd store this token securely (database, session, etc.)
        # For now, we'll return it to the client
        return {
            "access_token": token_info['access_token'],
            "refresh_token": token_info['refresh_token'],
            "expires_in": token_info['expires_in'],
            "message": "Authentication successful!"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Callback error: {str(e)}")

@router.post("/validate-token")
async def validate_token(token_data: Dict[str, str]):
    """Validate and test an access token"""
    try:
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Access token required")
        
        # Create Spotify client and test the token
        sp = spotify_service.create_spotify_client(access_token)
        user_profile = spotify_service.get_user_profile(sp)
        
        if not user_profile:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        return {
            "valid": True,
            "user": {
                "id": user_profile.get("id"),
                "display_name": user_profile.get("display_name"),
                "email": user_profile.get("email"),
                "followers": user_profile.get("followers", {}).get("total", 0)
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")