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
    """Initiate Spotify OAuth login and redirect to Spotify"""
    try:
        auth_url = spotify_service.get_auth_url()
        return RedirectResponse(url=auth_url)
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
        print(f"AUTH CALLBACK: Received code: {code[:20]}...")
        print(f"AUTH CALLBACK: State: {state}")
        
        # Exchange code for access token
        token_info = spotify_service.get_access_token(code)
        print(f"AUTH CALLBACK: Token info result: {token_info}")
        
        if not token_info:
            print("AUTH ERROR: Token exchange failed - token_info is None")
            return RedirectResponse(url="http://127.0.0.1:5173/?error=auth_failed")
        
        # Redirect to frontend with success and access token
        access_token = token_info['access_token']
        print(f"AUTH SUCCESS: Redirecting with token: {access_token[:20]}...")
        
        # Try multiple possible frontend URLs
        frontend_urls = [
            "image.png"
        ]
        
        # Use the first URL for now, but log all options
        redirect_url = f"{frontend_urls[0]}/?success=true&access_token={access_token}"
        print(f"AUTH SUCCESS: Redirecting to: {redirect_url}")
        
        # Store the token temporarily and redirect to frontend
        # We'll use a simple redirect and let the frontend handle token retrieval
        from fastapi.responses import RedirectResponse
        
        # Generate a simple token ID to pass in URL
        import hashlib
        import time
        token_id = hashlib.md5(f"{access_token}{time.time()}".encode()).hexdigest()[:16]
        
        # Store the full token temporarily (in a real app, use Redis or database)
        global temp_tokens
        if 'temp_tokens' not in globals():
            temp_tokens = {}
        temp_tokens[token_id] = access_token
        
        # Schedule cleanup of the token after 30 seconds
        import asyncio
        async def cleanup_token():
            await asyncio.sleep(30)
            if 'temp_tokens' in globals() and token_id in temp_tokens:
                del temp_tokens[token_id]
                print(f"AUTH: Cleaned up token {token_id}")
        
        # Start cleanup task
        asyncio.create_task(cleanup_token())
        
        redirect_url = f"http://127.0.0.1:5173/?auth_success=true&token_id={token_id}"
        print(f"AUTH: Redirecting to {redirect_url}")
        
        return RedirectResponse(url=redirect_url, status_code=302)
    
    except Exception as e:
        print(f"AUTH ERROR: Exception in callback: {e}")
        import traceback
        traceback.print_exc()
        return RedirectResponse(url=f"http://127.0.0.1:5173/?error=auth_failed")

@router.get("/debug")
async def debug_auth():
    """Debug endpoint to check authentication configuration"""
    return {
        "client_id": spotify_service.client_id,
        "client_secret": "***" if spotify_service.client_secret else None,
        "redirect_uri": spotify_service.redirect_uri,
        "has_client_id": bool(spotify_service.client_id),
        "has_client_secret": bool(spotify_service.client_secret),
        "has_redirect_uri": bool(spotify_service.redirect_uri)
    }

@router.get("/test-redirect")
async def test_redirect():
    """Test endpoint to verify redirect functionality"""
    return RedirectResponse(url="http://127.0.0.1:5173/?test=success")

@router.get("/test-token")
async def test_token():
    """Test endpoint to verify token passing"""
    test_token = "test123"
    redirect_url = f"http://127.0.0.1:5173/?success=true&access_token={test_token}"
    print(f"TEST: Redirecting to {redirect_url}")
    return RedirectResponse(url=redirect_url, status_code=302)

@router.get("/get-token/{token_id}")
async def get_token(token_id: str):
    """Get the full token using the token ID"""
    global temp_tokens
    if 'temp_tokens' not in globals():
        temp_tokens = {}
    
    if token_id in temp_tokens:
        token = temp_tokens[token_id]
        # Don't delete immediately - keep for a short time to handle race conditions
        # The token will be cleaned up by the callback endpoint after a delay
        return {"access_token": token}
    else:
        raise HTTPException(status_code=404, detail="Token not found or expired")

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