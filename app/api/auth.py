from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from app.services.spotify_service import SpotifyService
from typing import Dict
import os

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Note: We'll create fresh Spotify service instances per request to avoid cross-user contamination


@router.get("/login")
async def login():
    """Initiate Spotify OAuth login and redirect to Spotify"""
    try:
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
        auth_url = spotify_service.get_auth_url()
        return RedirectResponse(url=auth_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

@router.get("/redirect")
async def login_redirect():
    """Redirect to Spotify OAuth login"""
    try:
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
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
        
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
        # Exchange code for access token
        token_info = spotify_service.get_access_token(code)
        print(f"AUTH CALLBACK: Token info result: {token_info}")
        
        if not token_info:
            print("AUTH ERROR: Token exchange failed - token_info is None")
            return RedirectResponse(url="http://127.0.0.1:5173/?error=auth_failed")  # Will be updated when you deploy frontend
        
        # Redirect to frontend with success and access token
        access_token = token_info['access_token']
        print(f"AUTH SUCCESS: Redirecting with token: {access_token[:20]}...")
        
        # Clear any existing caches for this user to ensure fresh data
        try:
            user_id = spotify_service.get_user_id_from_token(access_token)
            spotify_service.clear_user_cache(user_id)
            print(f"Cleared Spotify service cache for new user: {user_id}")
            
            # Also clear recommendation caches
            from app.api.recommendations_lastfm import clear_all_user_caches
            clear_all_user_caches(user_id)
            print(f"Cleared recommendation caches for new user: {user_id}")
        except Exception as cache_error:
            print(f"Warning: Could not clear caches: {cache_error}")
        
        # Try multiple possible frontend URLs
        frontend_urls = [
            "http://127.0.0.1:5173",  # Local development
            "https://soundsculpt-frontend.vercel.app"  # Production Vercel URL
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
    # Create fresh Spotify service instance
    spotify_service = SpotifyService()
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
        
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
        # Use the new validation method with better error handling
        validation_result = spotify_service.validate_token_and_user(access_token)
        
        if not validation_result["valid"]:
            raise HTTPException(status_code=401, detail=validation_result["error"])
        
        user_profile = validation_result["user_profile"]
        return {
            "valid": True,
            "user": {
                "id": user_profile.get("id"),
                "display_name": user_profile.get("display_name"),
                "email": user_profile.get("email"),
                "followers": user_profile.get("followers", {}).get("total", 0)
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")

@router.get("/debug-token")
async def debug_token(token: str = Query(..., description="Spotify access token")):
    """Debug endpoint to check token and provide detailed error information"""
    try:
        print(f"=== TOKEN DEBUG ENDPOINT ===")
        print(f"Token received: {token[:20]}...")
        
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
        # Validate token and get detailed info
        validation_result = spotify_service.validate_token_and_user(token)
        
        if validation_result["valid"]:
            user_profile = validation_result["user_profile"]
            return {
                "status": "success",
                "message": "Token is valid",
                "user": {
                    "id": user_profile.get("id"),
                    "display_name": user_profile.get("display_name"),
                    "email": user_profile.get("email"),
                    "country": user_profile.get("country"),
                    "product": user_profile.get("product")
                },
                "app_config": {
                    "client_id": spotify_service.client_id,
                    "redirect_uri": spotify_service.redirect_uri,
                    "scopes": spotify_service.scope
                }
            }
        else:
            return {
                "status": "error",
                "message": validation_result["error"],
                "user": None,
                "app_config": {
                    "client_id": spotify_service.client_id,
                    "redirect_uri": spotify_service.redirect_uri,
                    "scopes": spotify_service.scope
                },
                "troubleshooting": {
                    "check_spotify_dashboard": "Go to https://developer.spotify.com/dashboard and verify your app settings",
                    "check_user_registration": "Make sure the user is registered in your Spotify app",
                    "check_redirect_uri": f"Verify redirect URI matches: {spotify_service.redirect_uri}",
                    "check_scopes": f"Verify required scopes are granted: {spotify_service.scope}"
                }
            }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Debug failed: {str(e)}",
            "user": None,
            "app_config": {
                "client_id": spotify_service.client_id,
                "redirect_uri": spotify_service.redirect_uri,
                "scopes": spotify_service.scope
            }
        }