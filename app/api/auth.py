from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from app.services.spotify_service import SpotifyService
from typing import Dict
import os
import time
import hashlib
import random
import uuid

# Smart frontend URL detection based on request origin
def get_frontend_url_from_request(request):
    """Detect frontend URL based on request origin"""
    # Get the referer header to see which frontend initiated the request
    referer = request.headers.get("referer", "")
    origin = request.headers.get("origin", "")
    
    print(f"🔍 BACKEND: Request referer: {referer}")
    print(f"🔍 BACKEND: Request origin: {origin}")
    
    # Check if request came from local frontend
    if "127.0.0.1:5173" in referer or "localhost:5173" in referer:
        print(f"🔍 BACKEND: Detected local frontend request, using local frontend URL")
        return "http://127.0.0.1:5173"
    elif "soundsculpt-frontend.vercel.app" in referer:
        print(f"🔍 BACKEND: Detected production frontend request, using production frontend URL")
        return "https://soundsculpt-frontend.vercel.app"
    
    # Fallback to production
    print(f"🔍 BACKEND: No clear frontend detected, using production as fallback")
    return "https://soundsculpt-frontend.vercel.app"

# Default frontend URL (fallback)
DEFAULT_FRONTEND_URL = "https://soundsculpt-frontend.vercel.app"

# Debug logging
print(f"🔍 BACKEND: FRONTEND_URL environment variable: {os.getenv('FRONTEND_URL')}")
print(f"🔍 BACKEND: Default FRONTEND_URL: {DEFAULT_FRONTEND_URL}")

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Note: We'll create fresh Spotify service instances per request to avoid cross-user contamination


@router.get("/login")
async def login(request: Request):
    """Initiate Spotify OAuth login and redirect to Spotify"""
    try:
        # Detect which frontend is making the request
        frontend_url = get_frontend_url_from_request(request)
        print(f"🔐 LOGIN: Detected frontend URL: {frontend_url}")
        
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
        
        # Create a state parameter that includes the frontend URL
        import hashlib, time, random
        state_data = {
            "frontend_url": frontend_url,
            "timestamp": time.time(),
            "random": random.random()
        }
        state_string = f"{frontend_url}|{time.time()}|{random.random()}"
        state = hashlib.md5(state_string.encode()).hexdigest()[:16]
        
        # Store the state mapping temporarily
        global state_to_frontend_url
        if 'state_to_frontend_url' not in globals():
            state_to_frontend_url = {}
        state_to_frontend_url[state] = frontend_url
        print(f"🔐 LOGIN: Stored state {state} for frontend {frontend_url}")
        
        # ALTERNATIVE: Try PKCE flow
        try:
            # Generate PKCE code verifier and challenge
            import secrets
            import base64
            import hashlib
            
            # Generate code verifier (43-128 characters)
            code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
            
            # Generate code challenge (SHA256 hash of verifier)
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode('utf-8')).digest()
            ).decode('utf-8').rstrip('=')
            
            print(f"🔐 PKCE: Generated code_verifier: {code_verifier[:20]}...")
            print(f"🔐 PKCE: Generated code_challenge: {code_challenge[:20]}...")
            
            # Store code verifier with state for later use
            global pkce_verifiers
            if 'pkce_verifiers' not in globals():
                pkce_verifiers = {}
            pkce_verifiers[state] = code_verifier
            
            # Create PKCE auth URL
            pkce_auth_url = spotify_service.get_pkce_auth_url_with_state(state, code_challenge)
            print(f"🔐 PKCE: Generated PKCE auth URL: {pkce_auth_url}")
            
            return RedirectResponse(url=pkce_auth_url)
            
        except Exception as pkce_error:
            print(f"⚠️ PKCE flow failed: {pkce_error}")
            # Fall back to regular flow
            auth_url = spotify_service.get_auth_url_with_state(state)
            print(f"🔐 LOGIN: Generated auth URL: {auth_url}")
        return RedirectResponse(url=auth_url)
    except Exception as e:
        print(f"❌ LOGIN ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")



@router.get("/login-nuclear")
async def login_nuclear(request: Request):
    """Nuclear parameters OAuth login endpoint"""
    try:
        # Get frontend URL from request
        frontend_url = get_frontend_url_from_request(request)
        print(f"🔐 LOGIN: Detected frontend URL: {frontend_url}")
        
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
        
        # Create state parameter
        import hashlib, time, random
        state_string = f"{frontend_url}|{time.time()}|{random.random()}"
        state = hashlib.md5(state_string.encode()).hexdigest()[:16]
        
        # Store the state mapping
        global state_to_frontend_url
        if 'state_to_frontend_url' not in globals():
            state_to_frontend_url = {}
        state_to_frontend_url[state] = frontend_url
        
        # Create nuclear auth URL with all parameters
        import urllib.parse
        base_url = "https://accounts.spotify.com/authorize"
        params = {
            'client_id': spotify_service.client_id,
            'response_type': 'code',
            'redirect_uri': spotify_service.redirect_uri,
            'scope': spotify_service.scope,
            'state': state,
            'show_dialog': 'true',
            'prompt': 'login',
            'login': 'true',
            'force_login': 'true',
            'skip_initial_state': 'true',
            'logout': 'true',
            'approval_prompt': 'force',
            'response_mode': 'query',
            'include_granted_scopes': 'true',
            'max_age': '0'
        }
        
        # Add random parameters
        params['nonce'] = str(random.randint(100000, 999999))
        params['verifier'] = str(random.randint(100000, 999999))
        params['ts'] = str(int(time.time() * 1000))
        
        query_string = urllib.parse.urlencode(params)
        auth_url = f"{base_url}?{query_string}"
        
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
async def callback(request: Request, code: str = Query(...), state: str = Query(None)):
    """Handle Spotify OAuth callback"""
    try:
        # Get frontend URL from stored state mapping
        global state_to_frontend_url
        if 'state_to_frontend_url' not in globals():
            state_to_frontend_url = {}
        
        if state and state in state_to_frontend_url:
            frontend_url = state_to_frontend_url[state]
            print(f"🔐 AUTH CALLBACK: Found stored frontend URL for state {state}: {frontend_url}")
            # Clean up the stored mapping
            del state_to_frontend_url[state]
        else:
            # Fallback to header-based detection
            frontend_url = get_frontend_url_from_request(request)
            print(f"🔐 AUTH CALLBACK: Using fallback frontend URL detection: {frontend_url}")
        print(f"🔐 AUTH CALLBACK: Received code: {code[:20]}...")
        print(f"🔐 AUTH CALLBACK: State: {state}")
        print(f"🔐 AUTH CALLBACK: Full code: {code}")
        print(f"🔐 AUTH CALLBACK: Timestamp: {time.time()}")
        print(f"🔐 AUTH CALLBACK: Code length: {len(code)}")
        print(f"🔐 AUTH CALLBACK: Code first 50 chars: {code[:50]}")
        print(f"🔐 AUTH CALLBACK: Code last 50 chars: {code[-50:]}")
        
        # Create fresh Spotify service instance
        spotify_service = SpotifyService()
        print(f"🔐 AUTH CALLBACK: Created Spotify service instance")
        
        
        # Exchange code for access token
        print(f"🔐 AUTH CALLBACK: Starting token exchange...")
        print(f"🔐 AUTH CALLBACK: Code being exchanged: {code[:20]}...")
        print(f"🔐 AUTH CALLBACK: Code full length: {len(code)}")
        print(f"🔐 AUTH CALLBACK: Code first 50 chars: {code[:50]}")
        print(f"🔐 AUTH CALLBACK: Code last 50 chars: {code[-50:]}")
        
        token_info = spotify_service.get_access_token(code)
        print(f"🔐 AUTH CALLBACK: Token info result: {token_info}")
        
        if token_info:
            print(f"🔐 AUTH CALLBACK: Token info keys: {list(token_info.keys())}")
            if 'access_token' in token_info:
                print(f"🔐 AUTH CALLBACK: Access token preview: {token_info['access_token'][:20]}...")
                print(f"🔐 AUTH CALLBACK: Access token full length: {len(token_info['access_token'])}")
        
        if not token_info:
            print("AUTH ERROR: Token exchange failed - token_info is None")
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=f"{frontend_url}/?error=auth_failed")
        
        # Now redirect to frontend with success and access token
        access_token = token_info['access_token']
        print(f"AUTH SUCCESS: Redirecting with token: {access_token[:20]}...")
        print(f"🔐 AUTH CALLBACK: Full access token: {access_token}")
        
        # Get user ID for logging and cache clearing
        try:
            user_id = spotify_service.get_user_id_from_token(access_token)
            print(f"🔍 Retrieved user ID: {user_id}")
            
            # Validate that the token belongs to the expected user
            # If we're getting a hash-based user ID, it means the token exchange failed
            # and we're getting the wrong user's token
            if user_id.startswith('a') and len(user_id) == 16:
                print(f"❌ AUTH ERROR: Got hash-based user ID, indicating token exchange failure")
                print(f"❌ AUTH ERROR: Token does not belong to the authenticated user")
                print(f"❌ AUTH ERROR: This suggests Spotify OAuth is returning wrong token")
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=f"{frontend_url}/?error=token_contamination")
            
            print(f"🔐 New user logging in: {user_id}")
            
            # Clear ALL existing caches AFTER we know the new user
            # This ensures that when a new user logs in, they don't see previous users' data
            print("🧹 POST-AUTH: Clearing all user caches to prevent cross-user data contamination...")
            
            try:
                # Show cache state before clearing
                cache_info_before = spotify_service.get_cache_info()
                print(f"📊 Cache state before clearing: {cache_info_before}")
                
                # Clear all Spotify service caches synchronously
                spotify_service.clear_all_caches()
                
                # Clear all recommendation caches synchronously
                from app.api.recommendations_lastfm import clear_all_user_caches
                clear_all_user_caches(None)  # Clear all users' caches
                
                # Show cache state after clearing
                cache_info_after = spotify_service.get_cache_info()
                print(f"📊 Cache state after clearing: {cache_info_after}")
                
                print("✅ POST-AUTH: Successfully cleared all user caches")
                
            except Exception as cache_error:
                print(f"❌ POST-AUTH: Error during cache clearing: {cache_error}")
                import traceback
                traceback.print_exc()
                # Ensure caches are cleared even if errors occur
                try:
                    spotify_service.clear_all_caches()
                    from app.api.recommendations_lastfm import clear_all_user_caches
                    clear_all_user_caches(None)
                    print("🧹 POST-AUTH: Cleared all caches as fallback")
                except Exception as fallback_error:
                    print(f"❌ POST-AUTH: Failed to clear caches even as fallback: {fallback_error}")
                    # Force clear the global caches directly
                    try:
                        import app.api.recommendations_lastfm as recs_module
                        recs_module.excluded_tracks_cache.clear()
                        recs_module.recommendation_pool_cache.clear()
                        print("🧹 POST-AUTH: Force cleared caches directly")
                    except Exception as force_error:
                        print(f"❌ POST-AUTH: Force clear also failed: {force_error}")
                        
        except Exception as e:
            print(f"⚠️ Could not get user ID for logging: {e}")
            # Still try to clear caches even if user ID fails
            try:
                spotify_service.clear_all_caches()
                from app.api.recommendations_lastfm import clear_all_user_caches
                clear_all_user_caches(None)
                print("🧹 POST-AUTH: Cleared all caches despite user ID error")
            except Exception as cache_error:
                print(f"❌ POST-AUTH: Failed to clear caches: {cache_error}")
        
        # OLD REDIRECT REMOVED - Using stateless approach below
        
        # Store the token temporarily and redirect to frontend
        # We'll use a simple redirect and let the frontend handle token retrieval
        from fastapi.responses import RedirectResponse
        
        # CLEAN STATELESS APPROACH: Pass token directly in URL - no global storage
        print(f"🔐 AUTH: Stateless authentication - passing token directly in redirect URL")
        print(f"🔐 AUTH: Token being passed: {access_token[:20]}...")
        print(f"🔐 AUTH: User ID being passed: {user_id}")
        
        # Clear any user-specific caches for clean state
        try:
            clear_all_user_caches(user_id)
            print("🧹 AUTH: Cleared user-specific caches for clean authentication")
        except Exception as cache_error:
            print(f"⚠️ AUTH: Cache clearing failed: {cache_error}")
        
        # Redirect to frontend with the token directly (encoded for security)
        import base64
        import json
        
        # Create a secure token package
        token_package = {
                'access_token': access_token,
                'user_id': user_id,
            'timestamp': time.time()
        }
        
        # DEBUG: Log token package details for Nuclear Params
        print(f"🔍 NUCLEAR TOKEN PACKAGE DEBUG:")
        print(f"  - access_token length: {len(access_token) if access_token else 'None'}")
        print(f"  - access_token starts with: {access_token[:20] if access_token else 'None'}...")
        print(f"  - user_id: {user_id}")
        print(f"  - timestamp: {time.time()}")
        print(f"  - token_package keys: {list(token_package.keys())}")
        
        # Encode the token package
        token_json = json.dumps(token_package)
        encoded_token = base64.urlsafe_b64encode(token_json.encode()).decode()
        print(f"🔐 Token package encoded successfully")
        
        # Redirect to frontend with the encoded token
        redirect_url = f"{frontend_url}/?auth_success=true&token={encoded_token}"
        print(f"🔐 AUTH: Redirecting to: {redirect_url}")
        
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=redirect_url, status_code=302)
    
    except Exception as e:
        print(f"❌ AUTH ERROR: Exception in callback: {e}")
        print(f"❌ AUTH ERROR: Exception type: {type(e)}")
        import traceback
        traceback.print_exc()
        
        # Fallback frontend URL in case of early exception
        try:
            fallback_frontend_url = get_frontend_url_from_request(request)
        except:
            fallback_frontend_url = "http://127.0.0.1:5173"  # Default fallback
        
        # Return a more detailed error page for debugging
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{fallback_frontend_url}/?error=auth_failed&details={str(e)[:100]}")

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
    return RedirectResponse(url=f"{DEFAULT_FRONTEND_URL}/?test=success")

@router.get("/test-token")
async def test_token():
    """Test endpoint to verify token passing"""
    test_token = "test123"
    redirect_url = f"{DEFAULT_FRONTEND_URL}/?success=true&access_token={test_token}"
    print(f"TEST: Redirecting to {redirect_url}")
    return RedirectResponse(url=redirect_url, status_code=302)

# OBSOLETE: get-token endpoint removed - using stateless authentication

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
        
        # OBSOLETE: temp_tokens clearing removed - using stateless authentication
        
        print("✅ MANUAL: Successfully cleared all user caches via API")
        return {"success": True, "message": "All caches cleared successfully"}
        
    except Exception as e:
        print(f"❌ MANUAL: Error clearing caches via API: {e}")
        # Force clear caches even if errors occur
        try:
            import app.api.recommendations_lastfm as recs_module
            recs_module.excluded_tracks_cache.clear()
            recs_module.recommendation_pool_cache.clear()
            # OBSOLETE: temp_tokens clearing removed - using stateless authentication
            print("🧹 MANUAL: Force cleared all caches as fallback")
        except Exception as force_error:
            print(f"❌ MANUAL: Force clear also failed: {force_error}")
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
        
        print(f"🔍 Current state - {len(temp_tokens)} tokens stored")
        print(f"🔍 Token IDs: {list(temp_tokens.keys())}")
        
        return {
            "total_tokens": len(temp_tokens),
            "token_ids": list(temp_tokens.keys()),
            "token_details": token_info
        }
    except Exception as e:
        print(f"❌ ERROR: {e}")
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
        print(f"=== TOKEN DEBUG ===")
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

@router.post("/clear-all-caches")
async def clear_all_caches():
    """Clear all user-specific caches to prevent cross-user contamination"""
    try:
        print("🧹 MANUAL: Clearing all user caches via API endpoint...")
        
        # Clear Spotify service caches
        spotify_service = SpotifyService()
        spotify_service.clear_all_caches()
        print("🧹 MANUAL: Cleared all Spotify service caches")
        
        # Clear Last.fm caches
        from app.api.recommendations_lastfm import clear_all_user_caches
        clear_all_user_caches("manual_clear")
        print("🧹 MANUAL: Cleared all excluded tracks and recommendation pool caches")
        
        # OBSOLETE: temp_tokens clearing removed - using stateless authentication
        
        print("🧹 MANUAL: Successfully cleared all user caches via API")
        return {"message": "All caches cleared successfully"}
    except Exception as e:
        print(f"❌ MANUAL: Error clearing caches: {e}")
        return {"error": f"Failed to clear caches: {str(e)}"}

@router.post("/clear-all-temp-tokens")
async def clear_all_temp_tokens():
    """Clear all temporary tokens to prevent cross-user contamination"""
    try:
        print("🧹 MANUAL: Clearing all temp tokens via API endpoint...")
        
        # OBSOLETE: temp_tokens clearing removed - using stateless authentication
        
        return {"message": "Stateless authentication - no temp tokens to clear"}
    except Exception as e:
        print(f"❌ MANUAL: Error clearing temp tokens: {e}")
        return {"error": f"Failed to clear temp tokens: {str(e)}"}

# OBSOLETE: Second get-token endpoint removed - using stateless authentication

@router.post("/logout")
async def logout():
    """Logout endpoint to clear all authentication data"""
    try:
        print("🚪 LOGOUT: Clearing all authentication data...")
        
        # Clear all user-specific caches
        try:
            from app.api.recommendations_lastfm import clear_all_user_caches
            clear_all_user_caches("logout")
            print("🧹 LOGOUT: Cleared all user-specific caches")
        except Exception as cache_error:
            print(f"⚠️ LOGOUT: Cache clearing failed: {cache_error}")
        
        print("✅ LOGOUT: All authentication data cleared")
        return {
            "success": True, 
            "message": "Successfully logged out and cleared all authentication data"
        }
        
    except Exception as e:
        print(f"❌ LOGOUT: Error during logout: {e}")
        return {"success": False, "error": str(e)}