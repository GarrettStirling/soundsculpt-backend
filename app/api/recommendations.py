"""
Recommendation API endpoints - Advanced and Discovery recommendations
"""

from fastapi import APIRouter, HTTPException, Query, Body
import os
from app.services.advanced_recommendation_service import AdvancedRecommendationService
from app.services.discovery_recommendation_service import DiscoveryRecommendationService
from typing import List, Optional, Dict

router = APIRouter(prefix="/recommendations", tags=["Music Recommendations"])


# Toggle between advanced and discovery recommendations
RECOMMENDATION_MODE = os.getenv('RECOMMENDATION_MODE', 'discovery')
advanced_recommendation_service = AdvancedRecommendationService()
discovery_recommendation_service = DiscoveryRecommendationService()

@router.get("/test-token")
async def test_token(token: str = Query(..., description="Spotify access token")):
    """Test if a Spotify access token is valid"""
    try:
        from app.services.spotify_service import SpotifyService
        spotify_service = SpotifyService()
        sp = spotify_service.create_spotify_client(token)
        user_info = sp.me()
        return {
            "valid": True,
            "user": user_info.get('display_name', 'Unknown'),
            "user_id": user_info.get('id', 'Unknown')
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }

@router.get("/collection-size")
async def get_collection_size(token: str = Query(..., description="Spotify access token")):
    """Get user's collection size for optimization warnings"""
    try:
        from app.services.spotify_service import SpotifyService
        spotify_service = SpotifyService()
        sp = spotify_service.create_spotify_client(token)
        
        # Quick scan to get collection size
        saved_tracks = sp.current_user_saved_tracks(limit=1)
        total_saved = saved_tracks.get('total', 0)
        
        playlists = sp.current_user_playlists(limit=1)
        total_playlists = playlists.get('total', 0)
        
        # Determine collection category
        if total_saved > 5000:
            category = "power_user"
            estimated_time = "15-25 seconds"
            warning = f"Large collection detected ({total_saved:,} songs)! This may take {estimated_time}."
        elif total_saved > 2000:
            category = "heavy_user" 
            estimated_time = "8-15 seconds"
            warning = f"Medium collection size ({total_saved:,} songs). Estimated time: {estimated_time}."
        else:
            category = "standard_user"
            estimated_time = "3-8 seconds"
            warning = None
        
        return {
            "total_saved_tracks": total_saved,
            "total_playlists": total_playlists,
            "category": category,
            "estimated_time": estimated_time,
            "warning": warning,
            "optimization_note": "We'll use smart sampling for faster processing" if total_saved > 3000 else None
        }
    except Exception as e:
        return {
            "error": str(e),
            "total_saved_tracks": 0,
            "category": "unknown"
        }


@router.post("/ml-recommendations")
async def get_ml_recommendations(
    token: str,
    n_recommendations: int = Query(30, ge=1, le=50, description="Number of songs to recommend"),
    user_controls: Optional[Dict] = Body(None, description="User preference controls")
):
    """
    Get personalized AI recommendations using user's listening history and preferences
    """
    try:
        print(f"=== ML RECOMMENDATIONS ENDPOINT ===")
        print(f"User controls: {user_controls}")
        recommender_type = 'Discovery' if RECOMMENDATION_MODE == 'discovery' else 'Advanced'
        print(f"Requesting {n_recommendations} {recommender_type} recommendations")
        if RECOMMENDATION_MODE == 'discovery':
            result = discovery_recommendation_service.get_recommendations(
                access_token=token,
                n_recommendations=n_recommendations
            )
        else:
            result = advanced_recommendation_service.get_recommendations(
                access_token=token,
                n_recommendations=n_recommendations
            )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        result["user_controls"] = user_controls
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"AI recommendations error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/search-based-discovery")
async def get_search_based_recommendations(
    token: str = Query(..., description="Spotify access token"),
    n_recommendations: int = Query(30, ge=1, le=50, description="Number of songs to recommend"),
    energy: Optional[int] = Query(None, ge=0, le=100, description="Energy preference (0=chill, 100=energetic)"),
    instrumentalness: Optional[int] = Query(None, ge=0, le=100, description="Instrumentalness preference (0=vocal, 100=instrumental)"),
    generation_seed: int = Query(0, ge=0, description="Generation seed for variation (0=first generation, 1+=subsequent)"),
    exclude_track_ids: Optional[str] = Query(None, description="Comma-separated list of track IDs to exclude from recommendations")
):
    """
    Get music discovery recommendations focused on new artists and underground tracks
    """
    try:
        print(f"=== MUSIC DISCOVERY ENDPOINT ===")
        print(f"Token provided: {'Yes' if token else 'No'}")
        print(f"Token length: {len(token) if token else 0}")
        print(f"Token starts with: {token[:10] if token else 'None'}...")
        print(f"Generation seed: {generation_seed}")
        
        # Parse excluded track IDs
        excluded_ids = set()
        if exclude_track_ids:
            excluded_ids = set(exclude_track_ids.split(','))
            print(f"Excluding {len(excluded_ids)} previously shown tracks")
        
        # Build user preferences if provided
        user_preferences = {}
        if energy is not None:
            user_preferences['energy'] = energy
        if instrumentalness is not None:
            user_preferences['instrumentalness'] = instrumentalness
        
        if user_preferences:
            print(f"User preferences: {user_preferences}")
        
        recommender_type = 'Discovery' if RECOMMENDATION_MODE == 'discovery' else 'Advanced'
        print(f"Requesting {n_recommendations} {recommender_type} recommendations (gen #{generation_seed + 1})")

        if not token or len(token) < 10:
            raise HTTPException(status_code=400, detail="Invalid or missing access token")

        # Use the selected recommendation service
        if RECOMMENDATION_MODE == 'discovery':
            result = discovery_recommendation_service.get_recommendations(
                access_token=token,
                n_recommendations=n_recommendations,
                user_preferences=user_preferences if user_preferences else None,
                generation_seed=generation_seed,
                excluded_track_ids=excluded_ids
            )
        else:
            result = advanced_recommendation_service.get_recommendations(
                access_token=token,
                n_recommendations=n_recommendations,
                user_preferences=user_preferences if user_preferences else None,
                generation_seed=generation_seed,
                excluded_track_ids=excluded_ids
            )

        if "error" in result:
            print(f"Error from recommendation service: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])

        print(f"Successfully generated {len(result.get('recommendations', []))} {recommender_type} recommendations")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Music discovery error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
