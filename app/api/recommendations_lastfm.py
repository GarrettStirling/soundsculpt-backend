from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import os
import json
import asyncio
import time
import queue
import threading
from app.services.spotify_service import SpotifyService
from app.services.lastfm_recommendation_service import LastFMRecommendationService
from typing import List, Optional, Dict
from pydantic import BaseModel

router = APIRouter(prefix="/recommendations", tags=["Music Recommendations"])

# Pydantic models for request/response
class ManualRecommendationRequest(BaseModel):
    seed_tracks: Optional[List[str]] = []  # Track IDs
    seed_artists: Optional[List[str]] = []  # Artist IDs 
    seed_playlists: Optional[List[str]] = []  # Playlist IDs 
    popularity: Optional[int] = 50  # 0-100 (used for filtering)
    n_recommendations: Optional[int] = 20
    excluded_track_ids: Optional[List[str]] = []  # Previously generated track IDs to exclude
    token: Optional[str] = None  # Spotify access token - make optional to avoid validation issues
    depth: Optional[int] = 3  # Analysis depth for Last.fm method
    exclude_saved_tracks: Optional[bool] = False  # Whether to exclude user's saved tracks

class PlaylistCreationRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    track_ids: List[str]

class PlaylistCreationResponse(BaseModel):
    success: bool
    playlist_id: Optional[str] = None
    playlist_url: Optional[str] = None
    message: str
    tracks_added: Optional[int] = None

# Initialize services
spotify_service = SpotifyService()
lastfm_recommendation_service = LastFMRecommendationService()

@router.get("/collection-size")
async def get_collection_size(token: str = Query(..., description="Spotify access token")):
    """Get user's collection size for optimization warnings"""
    try:
        print(f"Collection size endpoint called")
        
        if not token or len(token) < 10:
            raise HTTPException(status_code=400, detail="Invalid or missing access token")
        
        sp = spotify_service.create_spotify_client(token)
        
        # Test authentication
        try:
            user_info = sp.me()
            print(f"Getting collection size for user: {user_info.get('display_name', 'Unknown')}")
        except Exception as auth_error:
            print(f"Authentication failed: {auth_error}")
            raise HTTPException(status_code=401, detail="Invalid or expired access token")
        
        # Get user's saved tracks count
        try:
            saved_tracks = sp.current_user_saved_tracks(limit=1)
            total_saved = saved_tracks.get('total', 0)
            print(f"User has {total_saved} saved tracks")
            
            # Determine if this is a large collection
            is_large_collection = total_saved >= 2000
            estimated_time = None
            
            if is_large_collection:
                if total_saved >= 5000:
                    estimated_time = "15-25 seconds"
                elif total_saved >= 3000:
                    estimated_time = "10-20 seconds"
                else:
                    estimated_time = "8-15 seconds"
            
            return {
                "total_saved_tracks": total_saved,
                "is_large_collection": is_large_collection,
                "estimated_analysis_time": estimated_time,
                "warning": f"Large collection detected ({total_saved:,} songs)! This may take {estimated_time}." if is_large_collection else None
            }
            
        except Exception as e:
            print(f"Error getting saved tracks: {e}")
            return {
                "total_saved_tracks": 0,
                "is_large_collection": False,
                "estimated_analysis_time": None,
                "warning": None
            }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Collection size error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# @router.get("/search-based-discovery")
# async def get_search_based_recommendations(
#     token: str = Query(..., description="Spotify access token"),
#     n_recommendations: int = Query(30, ge=1, le=50, description="Number of songs to recommend"),
#     popularity: Optional[int] = Query(None, ge=0, le=100, description="Popularity preference (0=niche, 100=mainstream)"),
#     analysis_track_count: int = Query(1000, ge=50, le=5000, description="Number of recent tracks to analyze"),
#     generation_seed: int = Query(0, ge=0, description="Generation seed for variation (0=first generation, 1+=subsequent)"),
#     exclude_track_ids: Optional[str] = Query(None, description="Comma-separated list of track IDs to exclude from recommendations"),
#     depth: int = Query(3, ge=1, le=10, description="Depth of analysis (number of top artists to consider)"),
#     exclude_saved_tracks: bool = Query(False, description="Whether to exclude user's saved tracks from recommendations")
# ):

#     try:
#         print(f"Auto discovery endpoint called with generation seed: {generation_seed}")
        
#         # Progress tracking
#         progress_messages = []
        
#         def add_progress(message):
#             progress_messages.append(message)
#             print(f"📡 PROGRESS: {message}")
        
#         add_progress("Fetching your recent tracks from Spotify...")
        
#         # Parse excluded track IDs
#         excluded_ids = set()
#         if exclude_track_ids:
#             excluded_ids = set(exclude_track_ids.split(','))
#             print(f"Excluding {len(excluded_ids)} previously shown tracks")
#             print(f"Excluded track IDs: {list(excluded_ids)[:10]}...")  # Show first 10 for debugging
        
#         # Build user preferences if provided
#         user_preferences = {}
#         if popularity is not None:
#             user_preferences['popularity'] = popularity
        
#         if user_preferences:
#             print(f"User preferences: {user_preferences}")
        
#         # Calculate actual user request vs total request (including pool extras)
#         actual_user_request = n_recommendations - 30 if n_recommendations > 30 else n_recommendations
#         pool_extras = n_recommendations - actual_user_request
#         print(f"Requesting {n_recommendations} total recommendations ({actual_user_request} for user + {pool_extras} for pool) (gen #{generation_seed + 1})")

#         if not token or len(token) < 10:
#             raise HTTPException(status_code=400, detail="Invalid or missing access token")

#         # Use method-specific auto discovery
#         sp = spotify_service.create_spotify_client(token)
        
#             # Get user's recent tracks for analysis - use the actual analysis_track_count
#         try:
#             user_tracks = []
            
#             # Get recently played tracks - fetch multiple pages to reach analysis_track_count
#             limit = 50  # Spotify API max per request
#             after_timestamp = None  # Use timestamp for pagination
#             while len(user_tracks) < analysis_track_count:
#                 recent_tracks = sp.current_user_recently_played(limit=limit, after=after_timestamp)
#                 items = recent_tracks.get('items', [])
#                 if not items:
#                     break
                
#                 for item in items:
#                     if item.get('track') and len(user_tracks) < analysis_track_count:
#                         user_tracks.append(item['track'])
                
#                 # Use the timestamp of the last item for pagination
#                 if items:
#                     after_timestamp = items[-1].get('played_at')
#                     if not after_timestamp:
#                         break
#                 else:
#                     break
                
#                 if len(user_tracks) >= 2000:  # Safety limit
#                     break
            
#             # Get user's saved tracks if we need more data to reach analysis_track_count
#             if len(user_tracks) < analysis_track_count:
#                 offset = 0
#                 while len(user_tracks) < analysis_track_count:
#                     saved_tracks = sp.current_user_saved_tracks(limit=limit, offset=offset)
#                     items = saved_tracks.get('items', [])
#                     if not items:
#                         break
                    
#                     for item in items:
#                         if item.get('track') and len(user_tracks) < analysis_track_count:
#                             user_tracks.append(item['track'])
                    
#                     offset += limit
#                     if offset >= 2000:  # Safety limit
#                         break
            
#             # Analyzing user tracks for Last.fm-based recommendations
            
#             # Get user's saved tracks to filter them out - only if requested
#             user_saved_tracks = set()
#             if exclude_saved_tracks:
#                 try:
#                     # Fetching user's saved tracks for filtering
#                     # Fetch ALL saved tracks (Spotify API max limit is 50)
#                     offset = 0
#                     limit = 50  # Spotify API maximum limit for saved tracks
#                     batch_count = 0
#                     while True:
#                         saved_tracks_response = sp.current_user_saved_tracks(limit=limit, offset=offset)
#                         items = saved_tracks_response.get('items', [])
#                         if not items:
#                             break
                        
#                         for item in items:
#                             if item.get('track') and item['track'].get('id'):
#                                 user_saved_tracks.add(item['track']['id'])
                        
#                         offset += limit
#                         batch_count += 1
                        
#                         # Progress update every 10 batches
#                         if batch_count % 10 == 0:
#                             pass  # Removed verbose progress message
                        
#                         # Safety check to prevent infinite loops
#                         if offset > 10000:  # Max 10,000 tracks
#                             break
                            
#                     # Found saved tracks to filter out
#                 except Exception as e:
#                     print(f"Warning: Could not fetch saved tracks: {e}")
#             else:
#                 # Skipping saved tracks filtering for faster processing
#                 pass
            
#             # Use Last.fm recommendation method only
#             add_progress("Processing your music library and extracting artists...")
            
#             # Apply seed selection logic for beginning/middle/end track selection
#             if generation_seed > 0 and len(user_tracks) > 100:
#                 add_progress("Selecting diverse seed tracks from your library...")
                
#                 # Calculate offsets for beginning, middle, and end
#                 total_tracks = len(user_tracks)
#                 library_offset = (generation_seed * 200) % (total_tracks - 100)  # Vary starting point
#                 artist_offset = (generation_seed * 50) % 20  # Vary artist selection
                
#                 # Select tracks from beginning, middle, and end
#                 beginning_tracks = user_tracks[library_offset:library_offset + 50]
#                 middle_start = total_tracks // 2 + (generation_seed % 100) - 50
#                 middle_tracks = user_tracks[max(0, middle_start):max(0, middle_start) + 50]
#                 end_start = max(0, total_tracks - 100 - (generation_seed % 50))
#                 end_tracks = user_tracks[end_start:end_start + 50]
                
#                 # Combine and shuffle for variety
#                 import random
#                 random.seed(generation_seed)
#                 selected_tracks = beginning_tracks + middle_tracks + end_tracks
#                 random.shuffle(selected_tracks)
                
#                 # Use selected tracks instead of all tracks
#                 user_tracks = selected_tracks[:analysis_track_count]
                
#                 print(f"SEED SELECTION: Using {len(user_tracks)} tracks from generation seed {generation_seed}")
#                 print(f"SEED SELECTION: Library offset: {library_offset}, Artist offset: {artist_offset}")
            
#             add_progress("Calling Last.fm recommendation API with your music...")
            
#             result = lastfm_recommendation_service.get_auto_discovery_recommendations(
#                 user_tracks=user_tracks,
#                 n_recommendations=n_recommendations,
#                 excluded_track_ids=excluded_ids,
#                 access_token=token,
#                 depth=depth,
#                 popularity=popularity,
#                 user_saved_tracks=user_saved_tracks
#             )
            
#             add_progress("Sorting and filtering recommendations...")
            
#         except Exception as e:
#             print(f"Error getting user tracks for Last.fm analysis: {e}")
#             raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")

#         if "error" in result:
#             print(f"Error from recommendation service: {result['error']}")
#             raise HTTPException(status_code=400, detail=result["error"])

#         # Get the recommendations from result
#         recommendations = result.get('recommendations', [])
#         print(f"Successfully generated {len(recommendations)} recommendations")
#         print(f"BACKEND SUMMARY: Found {len(recommendations)} songs after all recommendation calls")
        
#         # Store extra recommendations for future batches
#         extra_recommendations = []
#         print(f"BACKEND DEBUG: Total recommendations: {len(recommendations)}, Requested: {n_recommendations}")
#         if len(recommendations) > n_recommendations:
#             extra_recommendations = recommendations[n_recommendations:]
            
#             # Randomize the pool for variety in each batch
#             import random
#             random.seed(generation_seed + 42)  # Different seed for pool randomization
#             random.shuffle(extra_recommendations)
            
#             print(f"BACKEND POOL: Adding {len(extra_recommendations)} randomized songs to recommendation pool")
#             add_progress(f"Caching {len(extra_recommendations)} extra recommendations for instant batches...")
#         else:
#             print(f"BACKEND POOL: No extra recommendations to cache (only {len(recommendations)} total, requested {n_recommendations})")
        
#         add_progress("Complete! Recommendations ready for delivery...")
        
#         # Update result with pool information
#         result["extra_recommendations"] = extra_recommendations
#         result["progress_messages"] = progress_messages
        
#         return result
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"Music discovery error: {e}")
#         import traceback
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/search-based-discovery-stream")
async def get_search_based_recommendations_stream(
    token: str = Query(..., description="Spotify access token"),
    n_recommendations: int = Query(30, ge=1, le=50, description="Number of songs to recommend"),
    popularity: Optional[int] = Query(None, ge=0, le=100, description="Popularity preference (0=niche, 100=mainstream)"),
    analysis_track_count: int = Query(1000, ge=50, le=5000, description="Number of recent tracks to analyze"),
    generation_seed: int = Query(0, ge=0, description="Generation seed for variation (0=first generation, 1+=subsequent)"),
    exclude_track_ids: Optional[str] = Query(None, description="Comma-separated list of track IDs to exclude"),
    exclude_saved_tracks: bool = Query(False, description="Whether to exclude user's saved tracks"),
    user_preferences: Optional[str] = Query(None, description="User preferences as JSON string")
):
    """Streaming version of auto discovery with real-time progress updates"""
    try:
        print(f"=== STREAMING AUTO DISCOVERY ENDPOINT ===")
        
        if not token or len(token) < 10:
            raise HTTPException(status_code=400, detail="Valid Spotify access token required")
        
        # Initialize Spotify service
        from app.services.spotify_service import SpotifyService
        spotify_service = SpotifyService()
        sp = spotify_service.create_spotify_client(token)
        
        # Parse excluded track IDs
        excluded_ids = set()
        if exclude_track_ids:
            excluded_ids = set(exclude_track_ids.split(','))
        
        # Build user preferences
        depth = analysis_track_count
        if not popularity:
            popularity = 50  # Default to balanced
        
        # Create a queue for progress messages
        progress_queue = queue.Queue()
        
        def progress_callback(message: str) -> None:
            progress_queue.put({"type": "progress", "message": message})
        
        def stream_generator():
            try:
                # Send initial progress message
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Starting music discovery process...'})}\n\n"
                
                # Start recommendation generation in a separate thread
                def generate_recommendations():
                    try:
                        # Get user tracks for analysis - using saved tracks instead of recently played
                        user_tracks = []
                        seen_track_ids = set()  # Prevent duplicates
                        limit = 50
                        offset = 0
                        
                        # Add timing for performance profiling
                        import time
                        fetch_start_time = time.time()
                        
                        while len(user_tracks) < analysis_track_count:
                            try:
                                # Get saved tracks with proper offset pagination
                                saved_tracks = sp.current_user_saved_tracks(limit=limit, offset=offset)
                                if not saved_tracks or not saved_tracks.get('items'):
                                    break
                                
                                for item in saved_tracks['items']:
                                    if len(user_tracks) >= analysis_track_count:
                                        break
                                    track = item['track']
                                    if track and track.get('id') and track['id'] not in seen_track_ids:
                                        seen_track_ids.add(track['id'])
                                        user_tracks.append({
                                            'id': track['id'],
                                            'name': track['name'],
                                            'artists': [{'name': artist['name']} for artist in track.get('artists', [])],
                                            'added_at': item.get('added_at')  # Use added_at instead of played_at
                                        })
                                
                                offset += limit
                                if len(user_tracks) >= 2000:  # Safety limit
                                    break
                                    
                            except Exception as e:
                                break
                        
                        fetch_end_time = time.time()
                        fetch_duration = fetch_end_time - fetch_start_time
                        
                        # Update progress with track count
                        progress_callback(f"Found {len(user_tracks)} saved tracks in your library")
                        
                        # Get user's saved tracks to filter them out - only if requested
                        user_saved_tracks = set()
                        if exclude_saved_tracks:
                            try:
                                # Fetch ALL saved tracks (Spotify API max limit is 50)
                                offset = 0
                                limit = 50  # Spotify API maximum limit for saved tracks
                                batch_count = 0
                                while True:
                                    saved_tracks = sp.current_user_saved_tracks(limit=limit, offset=offset)
                                    if not saved_tracks or not saved_tracks.get('items'):
                                        break
                                    
                                    for item in saved_tracks['items']:
                                        if item.get('track', {}).get('id'):
                                            user_saved_tracks.add(item['track']['id'])
                                    
                                    offset += limit
                                    batch_count += 1
                                    
                                    # Safety check to prevent infinite loops
                                    if offset > 10000:  # Max 10,000 tracks
                                        break
                                        
                            except Exception as e:
                                pass
                        else:
                            pass
                        
                        
                        # Apply seed selection logic for beginning/middle/end track selection
                        if generation_seed > 0 and len(user_tracks) > 100:
                            progress_callback(f"Analyzing {len(user_tracks)} tracks...")
                            
                            # Calculate offsets for beginning, middle, and end
                            total_tracks = len(user_tracks)
                            library_offset = (generation_seed * 200) % (total_tracks - 100)  # Vary starting point
                            artist_offset = (generation_seed * 50) % 20  # Vary artist selection
                            
                            
                            # Select tracks from beginning, middle, and end
                            beginning_tracks = user_tracks[library_offset:library_offset + 50]
                            middle_start = total_tracks // 2 + (generation_seed % 100) - 50
                            middle_tracks = user_tracks[max(0, middle_start):max(0, middle_start) + 50]
                            end_start = max(0, total_tracks - 100 - (generation_seed % 50))
                            end_tracks = user_tracks[end_start:end_start + 50]
                            
                            
                            
                            # Combine and shuffle for variety
                            import random
                            random.seed(generation_seed)
                            selected_tracks = beginning_tracks + middle_tracks + end_tracks
                            random.shuffle(selected_tracks)
                            
                            # Use selected tracks instead of all tracks
                            user_tracks = selected_tracks[:analysis_track_count]
                            
                        else:
                            progress_callback(f"Using all {len(user_tracks)} tracks for analysis...")
                        
                        progress_callback("Calling Last.fm recommendation API with your music...")
                        
                        
                        # Add timing for recommendation generation
                        rec_start_time = time.time()
                        
                        # Use Last.fm recommendation method with progress callback
                        result = lastfm_recommendation_service.get_auto_discovery_recommendations(
                            user_tracks=user_tracks,
                            n_recommendations=n_recommendations,
                            excluded_track_ids=excluded_ids,
                            access_token=token,
                            depth=depth,
                            popularity=popularity,
                            user_saved_tracks=user_saved_tracks,
                            progress_callback=progress_callback
                        )
                        
                        # Add timing for recommendation generation
                        rec_end_time = time.time()
                        rec_duration = rec_end_time - rec_start_time
                        
                        progress_callback("Analyzing and filtering recommendations...")
                        
                        # Add pool logic and final progress message
                        recommendations = result.get('recommendations', [])
                        progress_callback(f"Found {len(recommendations)} recommendations!")
                        
                        if len(recommendations) > n_recommendations:
                            extra_recommendations = recommendations[n_recommendations:]
                            progress_callback(f"Caching {len(extra_recommendations)} extra recommendations for instant batches...")
                        else:
                            progress_callback("No extra recommendations to cache for pool")
                        
                        progress_callback("Complete! Recommendations ready for delivery...")
                        
                        progress_queue.put({"type": "result", "data": result})
                        
                    except Exception as e:
                        progress_queue.put({"type": "error", "message": str(e)})
                
                # Send key progress messages immediately (before thread starts)
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Starting music discovery process...'})}\n\n"
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Fetching your saved tracks from Spotify...'})}\n\n"
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Analyzing your music library...'})}\n\n"
                
                # Start the recommendation generation in a separate thread
                import threading
                thread = threading.Thread(target=generate_recommendations)
                thread.daemon = True
                thread.start()
                
                # Stream progress messages and results
                while True:
                    try:
                        # Get message from queue with timeout
                        message = progress_queue.get(timeout=1)
                        
                        if message["type"] == "progress":
                            yield f"data: {json.dumps(message)}\n\n"
                        elif message["type"] == "result":
                            yield f"data: {json.dumps(message)}\n\n"
                            break
                        elif message["type"] == "error":
                            yield f"data: {json.dumps(message)}\n\n"
                            break
                            
                    except queue.Empty:
                        # Send heartbeat to keep connection alive
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                        continue
                        
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/manual-discovery")
async def get_manual_recommendations(
    request: ManualRecommendationRequest
):

    try:
        
        if not request.token or len(request.token) < 10:
            raise HTTPException(status_code=400, detail="Invalid or missing access token")
        
        # Validate at least one seed track is provided
        if not request.seed_tracks:
            raise HTTPException(status_code=400, detail="At least one seed track must be provided for recommendations")
        
        sp = spotify_service.create_spotify_client(request.token)
        
        # Test authentication
        try:
            user_info = sp.me()
        except Exception as auth_error:
            raise HTTPException(status_code=401, detail="Invalid or expired access token")
        
        # Get track information for all seed tracks
        seed_tracks_info = []
        for i, seed_track_id in enumerate(request.seed_tracks):
            try:
                seed_track_info = sp.track(seed_track_id)
                if not seed_track_info:
                    continue
                
                seed_track_name = seed_track_info.get('name', '')
                seed_artist_name = seed_track_info.get('artists', [{}])[0].get('name', '') if seed_track_info.get('artists') else ''
                
                if seed_track_name and seed_artist_name:
                    seed_tracks_info.append({
                        'name': seed_track_name,
                        'artist': seed_artist_name,
                        'id': seed_track_id,
                        'source': 'direct_track'
                    })
                
            except Exception as e:
                continue
        
        # Process seed artists - get top tracks from each artist
        seed_artists_info = []
        for i, seed_artist_id in enumerate(request.seed_artists):
            try:
                seed_artist_info = sp.artist(seed_artist_id)
                if not seed_artist_info:
                    continue
                
                artist_name = seed_artist_info.get('name', '')
                if artist_name:
                    # Get top tracks from this artist
                    top_tracks = sp.artist_top_tracks(seed_artist_id, country='US')
                    if top_tracks and top_tracks.get('tracks'):
                        # Take the first few top tracks as seeds
                        for track in top_tracks['tracks'][:3]:  # Take top 3 tracks
                            track_name = track.get('name', '')
                            if track_name:
                                seed_tracks_info.append({
                                    'name': track_name,
                                    'artist': artist_name,
                                    'id': track['id'],
                                    'source': 'artist_top_track'
                                })
                        seed_artists_info.append({
                            'name': artist_name,
                            'id': seed_artist_id,
                            'tracks_added': min(3, len(top_tracks.get('tracks', [])))
                        })
                
            except Exception as e:
                print(f"Error processing seed artist {seed_artist_id}: {e}")
                continue
        
        # Process seed playlists - get tracks from each playlist
        seed_playlists_info = []
        for i, seed_playlist_id in enumerate(request.seed_playlists):
            try:
                seed_playlist_info = sp.playlist(seed_playlist_id)
                if not seed_playlist_info:
                    continue
                
                playlist_name = seed_playlist_info.get('name', '')
                if playlist_name:
                    # Get tracks from this playlist
                    playlist_tracks = sp.playlist_tracks(seed_playlist_id, limit=50)
                    if playlist_tracks and playlist_tracks.get('items'):
                        # Take tracks from the playlist as seeds
                        for item in playlist_tracks['items'][:5]:  # Take first 5 tracks
                            track = item.get('track')
                            if track and track.get('name') and track.get('artists'):
                                track_name = track.get('name', '')
                                artist_name = track['artists'][0].get('name', '') if track['artists'] else ''
                                if track_name and artist_name:
                                    seed_tracks_info.append({
                                        'name': track_name,
                                        'artist': artist_name,
                                        'id': track['id'],
                                        'source': 'playlist_track'
                                    })
                        seed_playlists_info.append({
                            'name': playlist_name,
                            'id': seed_playlist_id,
                            'tracks_added': min(5, len(playlist_tracks.get('items', [])))
                        })
                
            except Exception as e:
                print(f"Error processing seed playlist {seed_playlist_id}: {e}")
                continue
        
        if not seed_tracks_info:
            raise HTTPException(status_code=400, detail="Could not retrieve any valid seed information from tracks, artists, or playlists")
        
        print(f"📊 Manual discovery seeds processed:")
        print(f"   🎵 Direct tracks: {len(request.seed_tracks)}")
        print(f"   🎤 Artists: {len(seed_artists_info)} (added {sum(a['tracks_added'] for a in seed_artists_info)} tracks)")
        print(f"   📋 Playlists: {len(seed_playlists_info)} (added {sum(p['tracks_added'] for p in seed_playlists_info)} tracks)")
        print(f"   📝 Total seed tracks for recommendations: {len(seed_tracks_info)}")
        
        
        # Convert excluded track IDs to set
        excluded_ids = set(request.excluded_track_ids) if request.excluded_track_ids else set()
        
        # Get user's saved tracks for filtering - only if requested
        user_saved_tracks = set()
        if request.exclude_saved_tracks:
            try:
                # Fetching user's saved tracks for filtering
                # Fetch ALL saved tracks (Spotify API max limit is 50)
                offset = 0
                limit = 50  # Spotify API maximum limit for saved tracks
                batch_count = 0
                while True:
                    saved_tracks_response = sp.current_user_saved_tracks(limit=limit, offset=offset)
                    items = saved_tracks_response.get('items', [])
                    if not items:
                        break
                    
                    for item in items:
                        if item.get('track', {}).get('id'):
                            user_saved_tracks.add(item['track']['id'])
                    
                    offset += limit
                    batch_count += 1
                    
                    # Progress update every 10 batches
                    if batch_count % 10 == 0:
                        pass  # Removed verbose progress message
                    
                    # Safety check to prevent infinite loops
                    if offset > 10000:  # Max 10,000 tracks
                        break
                        
                # Found saved tracks to filter out
            except Exception as e:
                print(f"Could not get user's saved tracks: {e}")
        else:
            # Skipping saved tracks filtering for faster processing
            pass
        
        # Use Last.fm recommendation service with multiple seed tracks
        result = lastfm_recommendation_service.get_multiple_seed_recommendations(
            seed_tracks=seed_tracks_info,
            n_recommendations=request.n_recommendations,
            excluded_track_ids=excluded_ids,
            user_saved_tracks=user_saved_tracks,
            access_token=request.token,
            popularity=request.popularity,
            depth=request.depth
        )
        
        if "error" in result:
            print(f"Last.fm recommendation error: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Get the recommendations from result
        recommendations = result.get('recommendations', [])
        print(f"Successfully generated {len(recommendations)} Last.fm-based recommendations")
        print(f"🎯 BACKEND SUMMARY: Found {len(recommendations)} songs after all recommendation calls")
        
        # Store extra recommendations for future batches (manual discovery pool)
        extra_recommendations = []
        if len(recommendations) > request.n_recommendations:
            extra_recommendations = recommendations[request.n_recommendations:]
            
            # Randomize the pool for variety in each batch
            import random
            random.seed(42)  # Fixed seed for manual discovery pool randomization
            random.shuffle(extra_recommendations)
            
            print(f"🎯 BACKEND POOL: Adding {len(extra_recommendations)} randomized songs to manual discovery pool")
            print(f"💾 Caching {len(extra_recommendations)} extra recommendations for instant batches")
        else:
            print(f"🎯 BACKEND POOL: No extra recommendations to cache (only {len(recommendations)} total, requested {request.n_recommendations})")
        
        # Update result with pool information
        result["extra_recommendations"] = extra_recommendations
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"{request.recommendation_method.upper()}-based manual discovery error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/manual-discovery-stream")
async def get_manual_recommendations_stream(
    request: ManualRecommendationRequest
):
    """
    Get Last.fm-based recommendations for manually selected seed tracks with streaming progress
    """
    try:
        print(f"Streaming manual discovery request received with {len(request.seed_tracks)} seed tracks")
        
        if not request.token or len(request.token) < 10:
            raise HTTPException(status_code=400, detail="Invalid or missing access token")
        
        # Validate at least one seed track is provided
        if not request.seed_tracks:
            raise HTTPException(status_code=400, detail="At least one seed track must be provided for recommendations")
        
        sp = spotify_service.create_spotify_client(request.token)
        
        # Test authentication
        try:
            user_info = sp.me()
            print(f"Creating streaming Last.fm-based recommendations for user: {user_info.get('display_name', 'Unknown')}")
        except Exception as auth_error:
            print(f"Authentication failed: {auth_error}")
            raise HTTPException(status_code=401, detail="Invalid or expired access token")
        
        # Get track information for all seed tracks
        seed_tracks_info = []
        for i, seed_track_id in enumerate(request.seed_tracks):
            try:
                seed_track_info = sp.track(seed_track_id)
                if not seed_track_info:
                    continue
                
                seed_track_name = seed_track_info.get('name', '')
                seed_artist_name = seed_track_info.get('artists', [{}])[0].get('name', '') if seed_track_info.get('artists') else ''
                
                if seed_track_name and seed_artist_name:
                    seed_tracks_info.append({
                        'name': seed_track_name,
                        'artist': seed_artist_name,
                        'id': seed_track_id,
                        'source': 'direct_track'
                    })
                
            except Exception as e:
                continue
        
        # Process seed artists - get top tracks from each artist
        seed_artists_info = []
        for i, seed_artist_id in enumerate(request.seed_artists):
            try:
                seed_artist_info = sp.artist(seed_artist_id)
                if not seed_artist_info:
                    continue
                
                artist_name = seed_artist_info.get('name', '')
                if artist_name:
                    # Get top tracks from this artist
                    top_tracks = sp.artist_top_tracks(seed_artist_id, country='US')
                    if top_tracks and top_tracks.get('tracks'):
                        # Take the first few top tracks as seeds
                        for track in top_tracks['tracks'][:3]:  # Take top 3 tracks
                            track_name = track.get('name', '')
                            if track_name:
                                seed_tracks_info.append({
                                    'name': track_name,
                                    'artist': artist_name,
                                    'id': track['id'],
                                    'source': 'artist_top_track'
                                })
                        seed_artists_info.append({
                            'name': artist_name,
                            'id': seed_artist_id,
                            'tracks_added': min(3, len(top_tracks.get('tracks', [])))
                        })
                
            except Exception as e:
                print(f"Error processing seed artist {seed_artist_id}: {e}")
                continue
        
        # Process seed playlists - get tracks from each playlist
        seed_playlists_info = []
        for i, seed_playlist_id in enumerate(request.seed_playlists):
            try:
                seed_playlist_info = sp.playlist(seed_playlist_id)
                if not seed_playlist_info:
                    continue
                
                playlist_name = seed_playlist_info.get('name', '')
                if playlist_name:
                    # Get tracks from this playlist
                    playlist_tracks = sp.playlist_tracks(seed_playlist_id, limit=50)
                    if playlist_tracks and playlist_tracks.get('items'):
                        # Take tracks from the playlist as seeds
                        for item in playlist_tracks['items'][:5]:  # Take first 5 tracks
                            track = item.get('track')
                            if track and track.get('name') and track.get('artists'):
                                track_name = track.get('name', '')
                                artist_name = track['artists'][0].get('name', '') if track['artists'] else ''
                                if track_name and artist_name:
                                    seed_tracks_info.append({
                                        'name': track_name,
                                        'artist': artist_name,
                                        'id': track['id'],
                                        'source': 'playlist_track'
                                    })
                        seed_playlists_info.append({
                            'name': playlist_name,
                            'id': seed_playlist_id,
                            'tracks_added': min(5, len(playlist_tracks.get('items', [])))
                        })
                
            except Exception as e:
                print(f"Error processing seed playlist {seed_playlist_id}: {e}")
                continue
        
        if not seed_tracks_info:
            raise HTTPException(status_code=400, detail="Could not retrieve any valid seed information from tracks, artists, or playlists")
        
        print(f"📊 Manual discovery seeds processed:")
        print(f"   🎵 Direct tracks: {len(request.seed_tracks)}")
        print(f"   🎤 Artists: {len(seed_artists_info)} (added {sum(a['tracks_added'] for a in seed_artists_info)} tracks)")
        print(f"   📋 Playlists: {len(seed_playlists_info)} (added {sum(p['tracks_added'] for p in seed_playlists_info)} tracks)")
        print(f"   📝 Total seed tracks for recommendations: {len(seed_tracks_info)}")
        
        
        # Convert excluded track IDs to set
        excluded_ids = set(request.excluded_track_ids) if request.excluded_track_ids else set()
        
        # Get user's saved tracks for filtering - only if requested
        user_saved_tracks = set()
        if request.exclude_saved_tracks:
            try:
                # Fetching user's saved tracks for filtering
                offset = 0
                limit = 50  # Spotify API limit
                batch_count = 0
                
                while True:
                    batch = sp.current_user_saved_tracks(limit=limit, offset=offset)
                    if not batch or not batch.get('items'):
                        break
                    
                    for item in batch['items']:
                        if item.get('track', {}).get('id'):
                            user_saved_tracks.add(item['track']['id'])
                    
                    offset += limit
                    batch_count += 1
                    
                    # Progress update every 10 batches
                    if batch_count % 10 == 0:
                        pass  # Removed verbose progress message
                    
                    # Safety check to prevent infinite loops
                    if offset > 10000:  # Max 10,000 tracks
                        break
                        
                # Found saved tracks to filter out
            except Exception as e:
                print(f"Could not get user's saved tracks: {e}")
        else:
            # Skipping saved tracks filtering for faster processing
            pass
        
        # Create a queue for progress messages
        progress_queue = queue.Queue()
        
        def progress_callback(message):
            """Callback function to send progress messages to the queue"""
            progress_queue.put({
                'type': 'progress',
                'message': message,
                'timestamp': time.strftime("%H:%M:%S")
            })
        
        def generate_recommendations():
            """Generate recommendations in a separate thread"""
            try:
                # Send initial progress messages
                progress_callback("Processing your selected seed tracks...")
                progress_callback("Calling Last.fm recommendation API...")
                
                # Use Last.fm recommendation service with progress callback
                result = lastfm_recommendation_service.get_multiple_seed_recommendations(
                    seed_tracks=seed_tracks_info,
                    n_recommendations=request.n_recommendations,
                    excluded_track_ids=excluded_ids,
                    user_saved_tracks=user_saved_tracks,
                    access_token=request.token,
                    popularity=request.popularity,
                    depth=request.depth,
                    progress_callback=progress_callback
                )
                
                # Send final progress messages
                progress_callback("Analyzing and filtering recommendations...")
                recommendations = result.get('recommendations', [])
                if len(recommendations) > request.n_recommendations:
                    extra_recommendations = recommendations[request.n_recommendations:]
                    progress_callback(f"Caching {len(extra_recommendations)} extra recommendations for instant batches...")
                else:
                    progress_callback("No extra recommendations to cache for pool")
                
                progress_callback("Complete! Recommendations ready for delivery...")
                
                # Send final result
                progress_queue.put({
                    'type': 'result',
                    'data': result
                })
                
            except Exception as e:
                progress_queue.put({
                    'type': 'error',
                    'error': str(e)
                })
        
        # Start recommendation generation in a separate thread
        thread = threading.Thread(target=generate_recommendations)
        thread.start()
        
        def stream_generator():
            """Generator function for streaming responses"""
            try:
                while True:
                    try:
                        # Get message from queue with timeout
                        message = progress_queue.get(timeout=1)
                        
                        if message['type'] == 'progress':
                            # Send progress message
                            yield f"data: {json.dumps(message)}\n\n"
                        elif message['type'] == 'result':
                            # Send final result
                            yield f"data: {json.dumps(message)}\n\n"
                            break
                        elif message['type'] == 'error':
                            # Send error
                            yield f"data: {json.dumps(message)}\n\n"
                            break
                            
                    except queue.Empty:
                        # Send heartbeat to keep connection alive
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                        continue
                        
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Streaming manual discovery error: {e}")
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
        
        # Create the playlist
        try:
            playlist = sp.user_playlist_create(
                user=user_info['id'],
                name=request.name,
                public=False,
                description=request.description or f"Generated playlist with {len(request.track_ids)} tracks"
            )
            
            playlist_id = playlist['id']
            playlist_url = playlist['external_urls']['spotify']
            
            print(f"✅ Created playlist: {playlist_id}")
            
        except Exception as playlist_error:
            print(f"Error creating playlist: {playlist_error}")
            raise HTTPException(status_code=500, detail=f"Failed to create playlist: {str(playlist_error)}")
        
        # Add tracks to the playlist
        try:
            # Filter out Last.fm tracks and only keep Spotify track IDs
            spotify_track_ids = [track_id for track_id in request.track_ids if not track_id.startswith('lastfm_')]
            
            if not spotify_track_ids:
                print("⚠️ No Spotify tracks found to add to playlist (all tracks are Last.fm recommendations)")
                return PlaylistCreationResponse(
                    success=False,
                    playlist_id=playlist_id,
                    playlist_url=playlist_url,
                    message="Playlist created but no Spotify tracks available to add (all recommendations are from Last.fm)",
                    tracks_added=0
                )
            
            print(f"📝 Adding {len(spotify_track_ids)} Spotify tracks to playlist (filtered out {len(request.track_ids) - len(spotify_track_ids)} Last.fm tracks)")
            
            # Validate Spotify track IDs (should be 22 characters, alphanumeric)
            valid_spotify_ids = []
            for track_id in spotify_track_ids:
                if len(track_id) == 22 and track_id.replace('-', '').replace('_', '').isalnum():
                    valid_spotify_ids.append(track_id)
                else:
                    print(f"⚠️ Invalid Spotify track ID format: {track_id}")
            
            if not valid_spotify_ids:
                print("❌ No valid Spotify track IDs found")
                return PlaylistCreationResponse(
                    success=False,
                    playlist_id=playlist_id,
                    playlist_url=playlist_url,
                    message="Playlist created but no valid Spotify tracks found to add",
                    tracks_added=0
                )
            
            print(f"📝 Adding {len(valid_spotify_ids)} valid Spotify tracks to playlist")
            
            # Convert track IDs to URIs
            track_uris = [f"spotify:track:{track_id}" for track_id in valid_spotify_ids]
            
            # Add tracks in batches (Spotify allows max 100 tracks per request)
            tracks_added = 0
            for i in range(0, len(track_uris), 100):
                batch = track_uris[i:i+100]
                try:
                    sp.playlist_add_items(playlist_id, batch)
                    tracks_added += len(batch)
                    print(f"✅ Added batch {i//100 + 1}: {len(batch)} tracks")
                except Exception as batch_error:
                    print(f"❌ Error adding batch {i//100 + 1}: {batch_error}")
                    # Continue with next batch instead of failing completely
                    continue
            
            print(f"✅ Successfully added {tracks_added} tracks to playlist")
            
            return PlaylistCreationResponse(
                success=True,
                playlist_id=playlist_id,
                playlist_url=playlist_url,
                message=f"Successfully created playlist '{request.name}' with {tracks_added} tracks",
                tracks_added=tracks_added
            )
            
        except Exception as tracks_error:
            print(f"Error adding tracks to playlist: {tracks_error}")
            # Playlist was created but tracks couldn't be added
            error_message = "Playlist created but failed to add tracks"
            if "Unsupported URL" in str(tracks_error) or "400" in str(tracks_error):
                error_message = "Playlist created but some tracks couldn't be added (may contain Last.fm recommendations)"
            elif "401" in str(tracks_error):
                error_message = "Playlist created but failed to add tracks (authentication issue)"
            elif "403" in str(tracks_error):
                error_message = "Playlist created but failed to add tracks (permission denied)"
            
            return PlaylistCreationResponse(
                success=False,
                playlist_id=playlist_id,
                playlist_url=playlist_url,
                message=error_message,
                tracks_added=0
            )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating playlist: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
