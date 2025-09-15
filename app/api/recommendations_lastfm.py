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
    track_data: Optional[List[dict]] = []  # Full track data with name, artist, id

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


@router.get("/search-based-discovery-stream")
async def get_search_based_recommendations_stream(
    token: str = Query(..., description="Spotify access token"),
    n_recommendations: int = Query(30, ge=1, le=50, description="Number of songs to recommend"),
    popularity: Optional[int] = Query(None, ge=0, le=100, description="Popularity preference (0=niche, 100=mainstream)"),
    analysis_track_count: int = Query(1000, ge=50, le=5000, description="Number of recent tracks to analyze"),
    generation_seed: int = Query(0, ge=0, description="Generation seed for variation (0=first generation, 1+=subsequent)"),
    exclude_track_ids: Optional[str] = Query(None, description="Comma-separated list of track IDs to exclude"),
    exclude_saved_tracks: bool = Query(False, description="Whether to exclude user's saved tracks"),
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
        
        # Check if token is expired
        if spotify_service.is_token_expired(sp):
            raise HTTPException(status_code=401, detail="Spotify access token has expired. Please reconnect your Spotify account.")
        
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
                
                # Start recommendation generation in a separate thread
                def generate_recommendations():
                    try:
                        # OPTIMIZED: Single fetch that handles both analysis and exclusion correctly
                        from app.services.spotify_service import SpotifyService
                        spotify_service = SpotifyService()
                        
                        # Add timing for performance profiling
                        import time
                        fetch_start_time = time.time()
                        
                        # Use parallel method for faster fetching (10-15s instead of 84s)
                        # - Fetches up to analysis_track_count tracks for analysis
                        # - If exclude_saved_tracks=True, fetches ALL tracks for exclusion
                        analysis_tracks, excluded_ids, excluded_track_data = spotify_service.get_user_saved_tracks_parallel(
                            sp_client=sp,
                            max_tracks=analysis_track_count,
                            exclude_tracks=exclude_saved_tracks
                        )
                        
                        progress_callback(f"Fetched {len(analysis_tracks)} recent tracks...")
                        
                        fetch_end_time = time.time()
                        fetch_duration = round(fetch_end_time - fetch_start_time, 2)
                        
                        if exclude_saved_tracks:
                            print(f"total duration of fetching {len(excluded_ids)} saved tracks: {fetch_duration}")
                            print(f"DEBUG: excluded_track_ids set size: {len(excluded_ids)}")
                            print(f"DEBUG: analysis tracks: {len(analysis_tracks)}, exclusion tracks: {len(excluded_ids)}")
                        else:
                            print(f"Duration to fetch {len(analysis_tracks)} saved tracks: {fetch_duration}")
                            print(f"DEBUG: exclude_saved_tracks is False, excluded_track_ids size: {len(excluded_ids)}")
                        
                        
                        # Apply random sampling to reduce analysis tracks to ~150 for performance
                        target_analysis_count = 150
                        if len(analysis_tracks) > target_analysis_count:
                            progress_callback(f"Randomly sampling {target_analysis_count} tracks from {len(analysis_tracks)} for analysis...")
                            
                            # Use generation_seed for reproducible random sampling
                            import random
                            random.seed(generation_seed)
                            analysis_tracks = random.sample(analysis_tracks, target_analysis_count)
                            
                            print(f"Selected {len(analysis_tracks)} tracks for analysis")
                            
                        else:
                            progress_callback(f"Using all {len(analysis_tracks)} tracks for analysis...")
                        
                        progress_callback("Calling Last.fm recommendation API with your music...")
                        
                        # Add timing for recommendation generation
                        rec_start_time = time.time()
                        
                        # Use Last.fm recommendation method with progress callback
                        print(f"DEBUG: About to call get_auto_discovery_recommendations with:")
                        print(f"  - analysis_tracks: {len(analysis_tracks)} tracks")
                        print(f"  - excluded_ids: {len(excluded_ids)} IDs")
                        print(f"  - excluded_track_data: {len(excluded_track_data)} track data entries")
                        print(f"  - n_recommendations: {n_recommendations}")
                        print(f"  - depth: {depth}")
                        print(f"  - popularity: {popularity}")
                        
                        try:
                            result = lastfm_recommendation_service.get_auto_discovery_recommendations(
                                analysis_tracks=analysis_tracks,
                                n_recommendations=n_recommendations,
                                excluded_track_ids=excluded_ids,
                                access_token=token,
                                depth=depth,
                                popularity=popularity,
                                excluded_track_data=excluded_track_data,
                                progress_callback=progress_callback
                            )
                            print(f"DEBUG: get_auto_discovery_recommendations completed successfully")
                            print(f"  - Result keys: {list(result.keys()) if result else 'None'}")
                        except Exception as e:
                            print(f"ERROR in get_auto_discovery_recommendations: {e}")
                            import traceback
                            traceback.print_exc()
                            raise
                        
                        # Add timing for recommendation generation
                        rec_end_time = time.time()
                        rec_duration = rec_end_time - rec_start_time

                        print(f"total duration of recommendation generation: {rec_duration}")
                        print(f"total recommendations generated: {len(result.get('recommendations', []))}")

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
                        print(f"ERROR in generate_recommendations: {e}")
                        import traceback
                        traceback.print_exc()
                        progress_queue.put({"type": "error", "message": str(e)})
                
                
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


@router.post("/manual-discovery-stream")
async def get_manual_recommendations_stream(
    request: ManualRecommendationRequest
):
    """
    Get Last.fm-based recommendations for manually selected seed tracks with streaming progress
    """
    try:
        print(f"🔍 BACKEND DEBUG: Manual discovery request received")
        print(f"  - seed_tracks: {request.seed_tracks}")
        print(f"  - seed_artists: {request.seed_artists}")
        print(f"  - seed_playlists: {request.seed_playlists}")
        print(f"  - n_recommendations: {request.n_recommendations}")
        print(f"  - popularity: {request.popularity}")
        print(f"  - excluded_track_ids: {request.excluded_track_ids}")
        print(f"  - exclude_saved_tracks: {request.exclude_saved_tracks}")
        print(f"  - token length: {len(request.token) if request.token else 0}")
        
        if not request.token or len(request.token) < 10:
            print("❌ ERROR: Invalid or missing access token")
            raise HTTPException(status_code=400, detail="Invalid or missing access token")
        
        # Check if we have any seed data (tracks, artists, or playlists)
        total_seeds = len(request.seed_tracks) + len(request.seed_artists) + len(request.seed_playlists)
        print(f"  - Total seed items: {total_seeds} (tracks: {len(request.seed_tracks)}, artists: {len(request.seed_artists)}, playlists: {len(request.seed_playlists)})")
        
        if total_seeds == 0:
            print("❌ ERROR: No seed data provided")
            raise HTTPException(status_code=400, detail="At least one seed track, artist, or playlist must be provided for recommendations")
        
        sp = spotify_service.create_spotify_client(request.token)
        
        # Check if token is expired
        if spotify_service.is_token_expired(sp):
            raise HTTPException(status_code=401, detail="Spotify access token has expired. Please reconnect your Spotify account.")
        
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
        
        
        # Convert excluded track IDs to set and get user's saved tracks for filtering
        excluded_ids = set(request.excluded_track_ids) if request.excluded_track_ids else set()
        excluded_track_data = []
        if request.exclude_saved_tracks:
            try:
                # Use parallel method to fetch saved tracks
                _, excluded_ids, excluded_track_data = spotify_service.get_user_saved_tracks_parallel(
                    sp_client=sp,
                    max_tracks=None,  # Don't need analysis tracks for manual discovery
                    exclude_tracks=True
                )
                print(f"Found {len(excluded_ids)} saved tracks to exclude")
                        
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
                    excluded_tracks=excluded_track_data,
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
        print(f"🔍 PLAYLIST CREATION DEBUG: Creating playlist '{request.name}' with {len(request.track_ids)} tracks")
        print(f"📋 Track IDs received: {request.track_ids[:5]}...")  # Show first 5 track IDs for debugging
        print(f"📋 All track IDs: {request.track_ids}")  # Show all track IDs for debugging
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
            # Separate Spotify track IDs from Last.fm track names
            # Normalize case to handle both 'lastfm_' and 'Lastfm_' prefixes
            spotify_track_ids = [track_id for track_id in request.track_ids if not track_id.lower().startswith('lastfm_')]
            lastfm_track_names = [track_id for track_id in request.track_ids if track_id.lower().startswith('lastfm_')]
            
            print(f"📝 Processing {len(spotify_track_ids)} Spotify tracks and {len(lastfm_track_names)} Last.fm tracks")
            print(f"🔍 DEBUG: Case normalization - Original track IDs: {request.track_ids[:3]}...")
            print(f"🔍 DEBUG: Spotify track IDs: {spotify_track_ids[:3]}...")
            print(f"🔍 DEBUG: Last.fm track IDs: {lastfm_track_names[:3]}...")
            
            # Validate existing Spotify track IDs
            valid_spotify_ids = []
            for track_id in spotify_track_ids:
                if len(track_id) == 22 and track_id.replace('-', '').replace('_', '').isalnum():
                    valid_spotify_ids.append(track_id)
                else:
                    print(f"⚠️ Invalid Spotify track ID format: {track_id}")
            
            # Search Spotify for Last.fm tracks using track_data
            found_spotify_ids = []
            if lastfm_track_names and request.track_data:
                print(f"🔍 Searching Spotify for {len(lastfm_track_names)} Last.fm tracks using track_data...")
                
                # Create a lookup map from track ID to track data
                track_data_map = {track['id']: track for track in request.track_data}
                
                for lastfm_track_id in lastfm_track_names:
                    try:
                        # Get track data from the lookup map
                        track_info = track_data_map.get(lastfm_track_id)
                        if not track_info:
                            print(f"⚠️ No track data found for ID: {lastfm_track_id}")
                            continue
                        
                        track_name = track_info.get('name', '')
                        artist_name = track_info.get('artist', '')
                        
                        if not track_name or not artist_name:
                            print(f"⚠️ Missing track name or artist for ID: {lastfm_track_id}")
                            continue
                        
                        # Create search query
                        search_query = f"track:\"{track_name}\" artist:\"{artist_name}\""
                        print(f"🔍 Searching Spotify for: '{search_query}'")
                        
                        # Search Spotify for this track
                        search_results = sp.search(q=search_query, type='track', limit=1)
                        
                        if search_results and search_results.get('tracks', {}).get('items'):
                            spotify_track = search_results['tracks']['items'][0]
                            spotify_track_id = spotify_track['id']
                            found_spotify_ids.append(spotify_track_id)
                            print(f"✅ Found Spotify track: '{spotify_track['name']}' by {spotify_track['artists'][0]['name']} (ID: {spotify_track_id})")
                        else:
                            print(f"❌ Could not find Spotify track for: {search_query}")
                            print(f"   Search results: {search_results}")
                            
                    except Exception as search_error:
                        print(f"❌ Error searching for track {lastfm_track_id}: {search_error}")
                        continue
            
            # Combine all valid Spotify track IDs
            all_spotify_ids = valid_spotify_ids + found_spotify_ids
            
            if not all_spotify_ids:
                print("❌ No Spotify tracks found to add to playlist")
                return PlaylistCreationResponse(
                    success=False,
                    playlist_id=playlist_id,
                    playlist_url=playlist_url,
                    message="Playlist created but no Spotify tracks found to add",
                    tracks_added=0
                )
            
            print(f"📝 Adding {len(all_spotify_ids)} total Spotify tracks to playlist ({len(valid_spotify_ids)} direct + {len(found_spotify_ids)} from Last.fm search)")
            print(f"🎵 Spotify track IDs to add: {all_spotify_ids[:5]}...")  # Show first 5 Spotify track IDs
            
            # Debug: Show what tracks we're actually adding by fetching their details
            if all_spotify_ids:
                print("🔍 DEBUG: Fetching details of tracks being added to playlist:")
                for i, track_id in enumerate(all_spotify_ids[:5]):  # Show first 5 tracks
                    try:
                        track_details = sp.track(track_id)
                        print(f"   {i+1}. '{track_details['name']}' by {track_details['artists'][0]['name']} (ID: {track_id})")
                    except Exception as e:
                        print(f"   {i+1}. Could not fetch details for track ID {track_id}: {e}")
                if len(all_spotify_ids) > 5:
                    print(f"   ... and {len(all_spotify_ids) - 5} more tracks")
                
                # Debug: Show the mapping from original track IDs to final Spotify IDs
                print("🔍 DEBUG: Track ID mapping:")
                print(f"   Original track IDs: {request.track_ids[:5]}...")
                print(f"   Final Spotify IDs: {all_spotify_ids[:5]}...")
            
            # Convert track IDs to URIs
            track_uris = [f"spotify:track:{track_id}" for track_id in all_spotify_ids]
            
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
