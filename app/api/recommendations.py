"""
Recommendation API endpoints - Discovery recommendations
"""

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
import os
import json
import asyncio
import time
from app.services.discovery_recommendation_service import DiscoveryRecommendationService
from app.services.spotify_service import SpotifyService
from typing import List, Optional, Dict
from pydantic import BaseModel

router = APIRouter(prefix="/recommendations", tags=["Music Recommendations"])

# Pydantic models for request/response
class ManualRecommendationRequest(BaseModel):
    seed_tracks: Optional[List[str]] = []  # Track IDs
    seed_artists: Optional[List[str]] = []  # Artist IDs
    seed_playlists: Optional[List[str]] = []  # Playlist IDs
    popularity: Optional[int] = 50  # 0-100
    n_recommendations: Optional[int] = 20

class PlaylistCreationRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    public: Optional[bool] = False
    track_ids: List[str]

class PlaylistCreationResponse(BaseModel):
    success: bool
    playlist_id: Optional[str] = None
    playlist_url: Optional[str] = None
    message: str
    tracks_added: Optional[int] = None


# Initialize services
discovery_recommendation_service = DiscoveryRecommendationService()
spotify_service = SpotifyService()

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


@router.get("/search-based-discovery")
async def get_search_based_recommendations(
    token: str = Query(..., description="Spotify access token"),
    n_recommendations: int = Query(30, ge=1, le=50, description="Number of songs to recommend"),
    popularity: Optional[int] = Query(None, ge=0, le=100, description="Popularity preference (0=niche, 100=mainstream)"),
    analysis_track_count: int = Query(1000, ge=50, le=5000, description="Number of recent tracks to analyze"),
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
        if popularity is not None:
            user_preferences['popularity'] = popularity
        
        if user_preferences:
            print(f"User preferences: {user_preferences}")
        
        print(f"Requesting {n_recommendations} recommendations (gen #{generation_seed + 1})")

        if not token or len(token) < 10:
            raise HTTPException(status_code=400, detail="Invalid or missing access token")

        # Use the discovery recommendation service
        result = discovery_recommendation_service.get_recommendations(
            access_token=token,
            n_recommendations=n_recommendations,
            user_preferences=user_preferences if user_preferences else None,
            generation_seed=generation_seed,
            excluded_track_ids=excluded_ids,
            analysis_track_count=analysis_track_count
        )

        if "error" in result:
            print(f"Error from recommendation service: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])

        print(f"Successfully generated {len(result.get('recommendations', []))} recommendations")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Music discovery error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/create-playlist", response_model=PlaylistCreationResponse)
async def create_playlist_from_recommendations(
    request: PlaylistCreationRequest,
    token: str = Query(..., description="Spotify access token")
):
    """Create a Spotify playlist from recommendation track IDs"""
    try:
        print(f"Creating playlist '{request.name}' with {len(request.track_ids)} tracks")
        
        # Validate access token
        try:
            sp = spotify_service.create_spotify_client(token)
            user_info = sp.me()
            print(f"Creating playlist for user: {user_info.get('display_name', 'Unknown')}")
        except Exception as auth_error:
            print(f"Authentication failed: {auth_error}")
            raise HTTPException(status_code=401, detail="Invalid or expired access token")
        
        # Validate track IDs
        if not request.track_ids:
            raise HTTPException(status_code=400, detail="No track IDs provided")
        
        if len(request.track_ids) > 10000:  # Spotify playlist limit
            raise HTTPException(status_code=400, detail="Too many tracks (max 10,000)")
        
        # Create playlist description
        description = request.description
        if not description:
            description = f"AI-generated playlist with {len(request.track_ids)} recommended tracks"
        
        # Create the playlist
        playlist = spotify_service.create_playlist(
            sp=sp,
            name=request.name,
            description=description,
            public=request.public
        )
        
        if not playlist:
            raise HTTPException(status_code=500, detail="Failed to create playlist")
        
        # Add tracks to the playlist
        success = spotify_service.add_tracks_to_playlist(
            sp=sp,
            playlist_id=playlist['id'],
            track_ids=request.track_ids
        )
        
        if not success:
            # Playlist was created but adding tracks failed
            return PlaylistCreationResponse(
                success=False,
                playlist_id=playlist['id'],
                playlist_url=playlist['external_urls']['spotify'],
                message="Playlist created but failed to add some tracks",
                tracks_added=0
            )
        
        print(f"✅ Successfully created playlist '{request.name}' with {len(request.track_ids)} tracks")
        
        return PlaylistCreationResponse(
            success=True,
            playlist_id=playlist['id'],
            playlist_url=playlist['external_urls']['spotify'],
            message=f"Successfully created playlist '{request.name}'",
            tracks_added=len(request.track_ids)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating playlist: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/manual-discovery")
async def get_manual_recommendations(
    request: ManualRecommendationRequest,
    token: str = Query(..., description="Spotify access token")
):
    """
    Get recommendations based on manually selected seed tracks, artists, and/or playlists
    """
    try:
        print(f"=== MANUAL DISCOVERY ENDPOINT ===")
        print(f"Seed tracks: {len(request.seed_tracks)}")
        print(f"Seed artists: {len(request.seed_artists)}")
        print(f"Seed playlists: {len(request.seed_playlists)}")
        print(f"Popularity preference: {request.popularity}")
        print(f"Requested recommendations: {request.n_recommendations}")
        
        if not token or len(token) < 10:
            raise HTTPException(status_code=400, detail="Invalid or missing access token")
        
        # Validate at least one seed is provided
        if not any([request.seed_tracks, request.seed_artists, request.seed_playlists]):
            raise HTTPException(status_code=400, detail="At least one seed (track, artist, or playlist) must be provided")
        
        sp = spotify_service.create_spotify_client(token)
        
        # Test authentication
        try:
            user_info = sp.me()
            print(f"Creating recommendations for user: {user_info.get('display_name', 'Unknown')}")
        except Exception as auth_error:
            print(f"Authentication failed: {auth_error}")
            raise HTTPException(status_code=401, detail="Invalid or expired access token")
        
        # Collect all track IDs from seeds
        all_seed_track_ids = []
        
        # Add direct track seeds
        if request.seed_tracks:
            all_seed_track_ids.extend(request.seed_tracks)
            print(f"Added {len(request.seed_tracks)} direct track seeds")
        
        # Get tracks from artist seeds (top tracks)
        if request.seed_artists:
            for artist_id in request.seed_artists:
                try:
                    top_tracks = sp.artist_top_tracks(artist_id)
                    artist_track_ids = [track['id'] for track in top_tracks['tracks'][:5]]  # Top 5 tracks
                    all_seed_track_ids.extend(artist_track_ids)
                    print(f"Added {len(artist_track_ids)} tracks from artist {artist_id}")
                except Exception as e:
                    print(f"Error getting tracks for artist {artist_id}: {e}")
        
        # Get tracks from playlist seeds
        if request.seed_playlists:
            for playlist_id in request.seed_playlists:
                try:
                    playlist_tracks = sp.playlist_tracks(playlist_id, limit=50)
                    playlist_track_ids = [item['track']['id'] for item in playlist_tracks['items'] 
                                        if item['track'] and item['track']['id']]
                    all_seed_track_ids.extend(playlist_track_ids)
                    print(f"Added {len(playlist_track_ids)} tracks from playlist {playlist_id}")
                except Exception as e:
                    print(f"Error getting tracks for playlist {playlist_id}: {e}")
        
        if not all_seed_track_ids:
            raise HTTPException(status_code=400, detail="No valid tracks found from provided seeds")
        
        # Remove duplicates
        unique_seed_tracks = list(set(all_seed_track_ids))
        print(f"Total unique seed tracks: {len(unique_seed_tracks)}")
        
        # Use Spotify's recommendation engine with our seeds
        # Spotify allows max 5 seeds, so we'll sample if we have more
        max_seeds = min(5, len(unique_seed_tracks))
        import random
        selected_seeds = random.sample(unique_seed_tracks, max_seeds)
        
        print(f"Using {len(selected_seeds)} seed tracks for recommendations")
        print(f"Seed track IDs: {selected_seeds}")
        
        # Validate track IDs first
        valid_track_ids = []
        for track_id in selected_seeds:
            try:
                # Try to get track info to validate the ID
                print(f"🔍 Validating track ID: {track_id}")
                track_info = sp.track(track_id)
                if track_info and track_info.get('id') == track_id:
                    # Double check the track is available for recommendations
                    if track_info.get('is_playable', True) and not track_info.get('is_local', False):
                        valid_track_ids.append(track_id)
                        print(f"✅ Valid track ID: {track_id} - {track_info.get('name', 'Unknown')} by {track_info.get('artists', [{}])[0].get('name', 'Unknown')}")
                    else:
                        print(f"❌ Track not available for recommendations: {track_id} - playable: {track_info.get('is_playable')}, local: {track_info.get('is_local')}")
                else:
                    print(f"❌ Invalid track ID response: {track_id}")
            except Exception as track_error:
                print(f"❌ Error validating track ID {track_id}: {track_error}")
                continue
        
        if not valid_track_ids:
            raise HTTPException(status_code=400, detail="No valid track IDs found in seeds. The selected tracks may not be available in your region or may have been removed from Spotify.")
        
        print(f"Using {len(valid_track_ids)} validated seed tracks: {valid_track_ids}")
        
        # Since Spotify's recommendations endpoint is deprecated for new apps,
        # we'll use an alternative approach: get related artists and their top tracks
        try:
            print(f"🎵 Using alternative recommendation strategy (Spotify recommendations API is deprecated)")
            all_recommendations = []
            seen_track_ids = set(valid_track_ids)  # Don't recommend the seed tracks
            
            # Get artists from seed tracks
            seed_artists = set()
            for track_id in valid_track_ids[:3]:  # Limit to first 3 tracks to avoid rate limits
                try:
                    track_info = sp.track(track_id)
                    for artist in track_info['artists']:
                        seed_artists.add(artist['id'])
                except Exception as e:
                    print(f"Error getting track info for {track_id}: {e}")
                    continue
            
            print(f"Found {len(seed_artists)} unique artists from seed tracks")
            
            # For each seed artist, get related artists and their top tracks
            for artist_id in list(seed_artists)[:2]:  # Limit to 2 artists to avoid too many API calls
                try:
                    # Get related artists
                    related_response = sp.artist_related_artists(artist_id)
                    related_artists = related_response['artists'][:5]  # Top 5 related artists
                    print(f"Found {len(related_artists)} related artists for {artist_id}")
                    
                    # Get top tracks from related artists
                    for related_artist in related_artists:
                        if len(all_recommendations) >= request.n_recommendations:
                            break
                        try:
                            top_tracks = sp.artist_top_tracks(related_artist['id'])
                            for track in top_tracks['tracks'][:3]:  # Top 3 tracks per related artist
                                if track['id'] not in seen_track_ids and len(all_recommendations) < request.n_recommendations:
                                    all_recommendations.append(track)
                                    seen_track_ids.add(track['id'])
                        except Exception as e:
                            print(f"Error getting top tracks for related artist {related_artist['id']}: {e}")
                            continue
                            
                except Exception as e:
                    print(f"Error getting related artists for {artist_id}: {e}")
                    continue
            
            # If we don't have enough recommendations, add some top tracks from the seed artists themselves
            if len(all_recommendations) < request.n_recommendations:
                for artist_id in seed_artists:
                    if len(all_recommendations) >= request.n_recommendations:
                        break
                    try:
                        top_tracks = sp.artist_top_tracks(artist_id)
                        for track in top_tracks['tracks']:
                            if track['id'] not in seen_track_ids and len(all_recommendations) < request.n_recommendations:
                                all_recommendations.append(track)
                                seen_track_ids.add(track['id'])
                    except Exception as e:
                        print(f"Error getting top tracks for seed artist {artist_id}: {e}")
                        continue
            
            print(f"✅ Generated {len(all_recommendations)} recommendations using related artists approach")
            
        except Exception as e:
            print(f"Error in alternative recommendation strategy: {e}")
            raise HTTPException(status_code=500, detail=f"Unable to generate recommendations: {str(e)}")
        
        # Format recommendations
        recommendations = []
        for track in all_recommendations:
            recommendations.append({
                "id": track['id'],
                "name": track['name'],
                "artist": ", ".join([artist['name'] for artist in track['artists']]),
                "album": track['album']['name'],
                "duration_ms": track['duration_ms'],
                "popularity": track['popularity'],
                "external_urls": track['external_urls'],
                "preview_url": track.get('preview_url'),
                "images": track['album']['images'],
                "audio_features": None  # We could fetch this separately if needed
            })
        
        print(f"✅ Generated {len(recommendations)} manual recommendations")
        
        return {
            "recommendations": recommendations,
            "algorithm": "Related Artists Discovery (Spotify Recommendations API Deprecated)",
            "seeds_used": {
                "track_count": len(request.seed_tracks),
                "artist_count": len(request.seed_artists),
                "playlist_count": len(request.seed_playlists),
                "total_seed_tracks": len(unique_seed_tracks),
                "selected_for_analysis": len(valid_track_ids)
            },
            "user_preferences": {
                "popularity": request.popularity
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Manual discovery error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
