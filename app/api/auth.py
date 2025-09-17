from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from app.services.spotify_service import SpotifyService
from typing import Dict
import os
import time
import hashlib
import random
import uuid

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Note: We'll create fresh Spotify service instances per request to avoid cross-user contamination


@router.get("/login")
async def login():
    """Initiate Spotify OAuth login and redirect to Spotify"""
    try:
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
        
        # Validate configuration before proceeding
        if not spotify_service.client_id:
            raise HTTPException(status_code=500, detail="SPOTIFY_CLIENT_ID not configured")
        if not spotify_service.client_secret:
            raise HTTPException(status_code=500, detail="SPOTIFY_CLIENT_SECRET not configured")
        if not spotify_service.redirect_uri:
            raise HTTPException(status_code=500, detail="SPOTIFY_REDIRECT_URI not configured")
            
        print(f"🔐 LOGIN: Using redirect URI: {spotify_service.redirect_uri}")
        
        auth_url = spotify_service.get_auth_url()
        print(f"🔐 LOGIN: Generated auth URL: {auth_url}")
        
        return RedirectResponse(url=auth_url)
    except Exception as e:
        print(f"❌ LOGIN ERROR: {e}")
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
        print(f"🔐 AUTH CALLBACK: Received code: {code[:20]}...")
        print(f"🔐 AUTH CALLBACK: State: {state}")
        print(f"🔐 AUTH CALLBACK: Full code: {code}")
        print(f"🔐 AUTH CALLBACK: Timestamp: {time.time()}")
        
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
        print(f"🔐 AUTH CALLBACK: Created Spotify service instance")
        
        # Exchange code for access token
        print(f"🔐 AUTH CALLBACK: Starting token exchange...")
        token_info = spotify_service.get_access_token(code)
        print(f"AUTH CALLBACK: Token info result: {token_info}")
        
        if not token_info:
            print("AUTH ERROR: Token exchange failed - token_info is None")
            return RedirectResponse(url="http://127.0.0.1:5173/?error=auth_failed")  # Will be updated when you deploy frontend
        
        # Clear ALL existing caches BEFORE redirecting to prevent cross-user contamination
        # This ensures that when a new user logs in, they don't see previous users' data
        print("🧹 PRE-AUTH: Clearing all user caches to prevent cross-user data contamination...")
        
        try:
            # Show cache state before clearing
            cache_info_before = spotify_service.get_cache_info()
            print(f"📊 Cache state before clearing: {cache_info_before}")
            
            # Clear all Spotify service caches
            spotify_service.clear_all_caches()
            
            # Also clear all recommendation caches
            from app.api.recommendations_lastfm import clear_all_user_caches
            clear_all_user_caches(None)  # Clear all users' caches
            
            # Show cache state after clearing
            cache_info_after = spotify_service.get_cache_info()
            print(f"📊 Cache state after clearing: {cache_info_after}")
            
            print("✅ PRE-AUTH: Successfully cleared all user caches")
            
        except Exception as cache_error:
            print(f"❌ PRE-AUTH: Error during cache clearing: {cache_error}")
            import traceback
            traceback.print_exc()
            # As a last resort, clear all caches
            try:
                spotify_service.clear_all_caches()
                from app.api.recommendations_lastfm import clear_all_user_caches
                clear_all_user_caches(None)
                print("🧹 PRE-AUTH: Cleared all caches as fallback")
            except Exception as fallback_error:
                print(f"❌ PRE-AUTH: Failed to clear caches even as fallback: {fallback_error}")
        
        # Now redirect to frontend with success and access token
        access_token = token_info['access_token']
        print(f"AUTH SUCCESS: Redirecting with token: {access_token[:20]}...")
        
        # Get user ID for logging
        try:
            user_id = spotify_service.get_user_id_from_token(access_token)
            print(f"🔐 New user logging in: {user_id}")
        except Exception as e:
            print(f"⚠️ Could not get user ID for logging: {e}")
        
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
        
        # Generate a unique token ID with better randomness
        try:
            import hashlib
            import random
            import uuid
            
            print(f"🔐 AUTH: Generating unique token ID...")
            # Use UUID + timestamp + random for better uniqueness
            unique_string = f"{access_token}{time.time()}{random.random()}{uuid.uuid4()}"
            token_id = hashlib.md5(unique_string.encode()).hexdigest()[:16]
            print(f"🔐 AUTH: Generated token_id: {token_id}")
            
            # Store the full token temporarily with user ID for debugging
            global temp_tokens
            if 'temp_tokens' not in globals():
                temp_tokens = {}
            
            # Store token with metadata for debugging
            temp_tokens[token_id] = {
                'access_token': access_token,
                'user_id': user_id,
                'timestamp': time.time(),
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            print(f"🔐 AUTH: Stored token {token_id} for user {user_id}")
            print(f"🔐 AUTH: Total tokens in storage: {len(temp_tokens)}")
            
            # Schedule cleanup of the token after 30 seconds
            import asyncio
            async def cleanup_token():
                await asyncio.sleep(30)
                if 'temp_tokens' in globals() and token_id in temp_tokens:
                    del temp_tokens[token_id]
                    print(f"🧹 AUTH: Cleaned up token {token_id}")
            
            # Start cleanup task
            asyncio.create_task(cleanup_token())
            
        except Exception as token_error:
            print(f"❌ AUTH: Error in token storage: {token_error}")
            import traceback
            traceback.print_exc()
            # Continue with redirect even if token storage fails
        
        redirect_url = f"http://127.0.0.1:5173/?auth_success=true&token_id={token_id}"
        print(f"AUTH: Redirecting to {redirect_url}")
        
        return RedirectResponse(url=redirect_url, status_code=302)
    
    except Exception as e:
        print(f"❌ AUTH ERROR: Exception in callback: {e}")
        print(f"❌ AUTH ERROR: Exception type: {type(e)}")
        import traceback
        traceback.print_exc()
        
        # Return a more detailed error page for debugging
        return RedirectResponse(url=f"http://127.0.0.1:5173/?error=auth_failed&details={str(e)[:100]}")

@router.get("/debug")
async def debug_auth():
    """Debug endpoint to check authentication configuration"""
    # Create fresh Spotify service instance
    spotify_service = SpotifyService()
    return {
        "client_id": spotify_service.client_id,
        "client_secret": "***" if spotify_service.client_secret else None,
        "redirect_uri": spotify_service.redirect_uri,
        "scope": spotify_service.scope,
        "has_client_id": bool(spotify_service.client_id),
        "has_client_secret": bool(spotify_service.client_secret),
        "has_redirect_uri": bool(spotify_service.redirect_uri)
    }

@router.get("/debug-auth-url")
async def debug_auth_url():
    """Debug endpoint to check the generated authorization URL"""
    try:
        spotify_service = SpotifyService()
        auth_url = spotify_service.get_auth_url()
        return {
            "auth_url": auth_url,
            "redirect_uri": spotify_service.redirect_uri,
            "client_id": spotify_service.client_id,
            "scope": spotify_service.scope
        }
    except Exception as e:
        return {"error": str(e)}

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
    
    print(f"🔍 GET-TOKEN: Looking for token_id: {token_id}")
    print(f"🔍 GET-TOKEN: Available tokens: {list(temp_tokens.keys())}")
    
    if token_id in temp_tokens:
        token_data = temp_tokens[token_id]
        
        # Handle both old format (just string) and new format (dict with metadata)
        if isinstance(token_data, dict):
            access_token = token_data['access_token']
            user_id = token_data.get('user_id', 'unknown')
            print(f"🔐 GET-TOKEN: Retrieved token for user {user_id}")
        else:
            # Backward compatibility for old format
            access_token = token_data
            print(f"🔐 GET-TOKEN: Retrieved token (old format)")
        
        # Don't delete immediately - keep for a short time to handle race conditions
        # The token will be cleaned up by the callback endpoint after a delay
        return {"access_token": access_token}
    else:
        print(f"❌ GET-TOKEN: Token {token_id} not found")
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

@router.post("/clear-all-caches")
async def clear_all_caches():
    """Force clear all user caches - can be called by frontend when new user logs in"""
    try:
        print("🧹 MANUAL: Clearing all user caches via API endpoint...")
        
        # Clear all Spotify service caches
        spotify_service = SpotifyService()
        spotify_service.clear_all_caches()
        
        # Clear all recommendation caches
        from app.api.recommendations_lastfm import clear_all_user_caches
        clear_all_user_caches(None)
        
        print("✅ MANUAL: Successfully cleared all user caches via API")
        return {"success": True, "message": "All caches cleared successfully"}
        
    except Exception as e:
        print(f"❌ MANUAL: Error clearing caches via API: {e}")
        return {"success": False, "error": str(e)}

@router.get("/debug-token-user")
async def debug_token_user(token: str = Query(..., description="Spotify access token")):
    """Debug endpoint to check which user a token belongs to"""
    try:
        spotify_service = SpotifyService()
        sp = spotify_service.create_spotify_client(token)
        user_profile = sp.current_user()
        
        return {
            "token_preview": token[:20] + "...",
            "user": {
                "id": user_profile.get("id"),
                "display_name": user_profile.get("display_name"),
                "email": user_profile.get("email"),
                "country": user_profile.get("country"),
                "product": user_profile.get("product")
            },
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        return {"error": str(e), "token_preview": token[:20] + "...", "timestamp": int(time.time() * 1000)}

@router.get("/debug-tokens")
async def debug_tokens():
    """Debug endpoint to check current token storage state"""
    try:
        global temp_tokens
        if 'temp_tokens' not in globals():
            temp_tokens = {}
        
        # Show token metadata without exposing actual tokens
        token_info = {}
        for token_id, token_data in temp_tokens.items():
            if isinstance(token_data, dict):
                token_info[token_id] = {
                    "user_id": token_data.get('user_id', 'unknown'),
                    "timestamp": token_data.get('timestamp', 0),
                    "created_at": token_data.get('created_at', 'unknown'),
                    "token_preview": token_data.get('access_token', '')[:20] + '...' if token_data.get('access_token') else 'none'
                }
            else:
                # Old format
                token_info[token_id] = {
                    "user_id": "unknown (old format)",
                    "token_preview": str(token_data)[:20] + '...' if token_data else 'none'
                }
        
        return {
            "total_tokens": len(temp_tokens),
            "token_ids": list(temp_tokens.keys()),
            "token_details": token_info
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/debug-cache")
async def debug_cache():
    """Debug endpoint to check current cache state"""
    try:
        from app.api.recommendations_lastfm import excluded_tracks_cache, recommendation_pool_cache
        
        spotify_service = SpotifyService()
        spotify_cache_info = spotify_service.get_cache_info()
        
        return {
            "spotify_service_cache": spotify_cache_info,
            "recommendation_caches": {
                "excluded_tracks_users": list(excluded_tracks_cache.keys()),
                "recommendation_pool_users": list(recommendation_pool_cache.keys()),
                "total_excluded_tracks": sum(len(tracks) for tracks in excluded_tracks_cache.values()),
                "total_recommendation_pools": sum(len(pools) for pools in recommendation_pool_cache.values())
            }
        }
    except Exception as e:
        return {"error": str(e)}

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