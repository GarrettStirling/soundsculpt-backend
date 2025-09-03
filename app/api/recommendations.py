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
from app.services.recommendation_utils import RecommendationUtils
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
    excluded_track_ids: Optional[List[str]] = []  # Previously generated track IDs to exclude

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
        
        # Non-deprecated API strategy - avoid Related Artists & Recommendations endpoints
        try:
            print(f"🎵 Using ARTIST-DIVERSE strategy (one song per artist, maximum variety)")
            all_recommendations = []
            seen_track_ids = set(valid_track_ids)  # Don't recommend the seed tracks
            
            # Add excluded track IDs to prevent cross-generation duplicates
            if request.excluded_track_ids:
                seen_track_ids.update(request.excluded_track_ids)
                print(f"🚫 Excluding {len(request.excluded_track_ids)} previously recommended tracks")
            
            seen_artists = set()  # Track artists we've already recommended
            current_seed_tracks = valid_track_ids.copy()
            iteration = 0
            max_iterations = 4
            
            # Get artists from seed tracks to avoid recommending them again
            for track_id in valid_track_ids:
                try:
                    track_info = sp.track(track_id)
                    for artist in track_info['artists']:
                        seen_artists.add(artist['id'])
                        print(f"Excluding seed artist: {artist['name']} ({artist['id']})")
                except Exception as e:
                    continue
            
            while len(all_recommendations) < request.n_recommendations and iteration < max_iterations:
                iteration += 1
                print(f"🔄 Iteration {iteration}: Current recommendations: {len(all_recommendations)}/{request.n_recommendations}")
                print(f"Artists already used: {len(seen_artists)}")
                
                # Get artists from current seed tracks for exploration
                seed_artists = set()
                tracks_to_analyze = current_seed_tracks[:8]
                
                for track_id in tracks_to_analyze:
                    try:
                        track_info = sp.track(track_id)
                        for artist in track_info['artists']:
                            seed_artists.add(artist['id'])
                    except Exception as e:
                        print(f"Error getting track info for {track_id}: {e}")
                        continue
                
                print(f"Found {len(seed_artists)} seed artists to explore for related content")
                
                # Collect new recommendations from this iteration
                iteration_recommendations = []
                artists_to_explore = list(seed_artists)[:6]
                
                # Strategy 1: Search for tracks by genre/style keywords from seed tracks
                if len(all_recommendations) + len(iteration_recommendations) < request.n_recommendations:
                    print(f"🔍 Strategy 1: Genre/style-based search for diverse artists")
                    
                    # Get genres from seed artists
                    search_genres = set()
                    for artist_id in artists_to_explore[:3]:  # Top 3 seed artists
                        try:
                            artist_info = sp.artist(artist_id)
                            genres = artist_info.get('genres', [])
                            search_genres.update(genres[:2])  # Top 2 genres per artist
                            print(f"Artist {artist_info['name']} genres: {genres[:2]}")
                        except Exception as e:
                            continue
                    
                    # Search by each genre to find different artists
                    for genre in list(search_genres)[:4]:  # Use up to 4 genres
                        if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                            break
                        try:
                            search_results = sp.search(q=f'genre:"{genre}"', type='track', limit=30)
                            genre_tracks = search_results.get('tracks', {}).get('items', [])
                            
                            tracks_added_from_genre = 0
                            for track in genre_tracks:
                                if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                                    break
                                
                                # Check if this artist is new (not in seen_artists)
                                track_artist_id = track['artists'][0]['id'] if track.get('artists') else None
                                if (track_artist_id and track_artist_id not in seen_artists and 
                                    track['id'] not in seen_track_ids):
                                    iteration_recommendations.append(track)
                                    seen_track_ids.add(track['id'])
                                    seen_artists.add(track_artist_id)
                                    tracks_added_from_genre += 1
                                    print(f"  ✅ Added from genre '{genre}': {track['name']} by {track['artists'][0]['name']}")
                            
                            print(f"Added {tracks_added_from_genre} tracks from genre: {genre}")
                            
                        except Exception as e:
                            print(f"Error searching for genre {genre}: {e}")
                            continue
                
                # Strategy 2: Year-based discovery (find tracks from same era)
                if len(all_recommendations) + len(iteration_recommendations) < request.n_recommendations:
                    print(f"📅 Strategy 2: Year-based discovery for diverse artists")
                    
                    # Get release years from seed tracks
                    seed_years = set()
                    for track_id in tracks_to_analyze[:3]:
                        try:
                            track_info = sp.track(track_id)
                            album_info = sp.album(track_info['album']['id'])
                            release_date = album_info.get('release_date', '')
                            if release_date:
                                year = release_date[:4]
                                seed_years.add(year)
                                print(f"Seed track year: {year}")
                        except Exception as e:
                            continue
                    
                    # Search for tracks from the same years
                    for year in list(seed_years):
                        if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                            break
                        try:
                            search_results = sp.search(q=f'year:{year}', type='track', limit=25)
                            year_tracks = search_results.get('tracks', {}).get('items', [])
                            
                            tracks_added_from_year = 0
                            for track in year_tracks:
                                if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                                    break
                                
                                track_artist_id = track['artists'][0]['id'] if track.get('artists') else None
                                if (track_artist_id and track_artist_id not in seen_artists and 
                                    track['id'] not in seen_track_ids):
                                    iteration_recommendations.append(track)
                                    seen_track_ids.add(track['id'])
                                    seen_artists.add(track_artist_id)
                                    tracks_added_from_year += 1
                                    print(f"  ✅ Added from year {year}: {track['name']} by {track['artists'][0]['name']}")
                            
                            print(f"Added {tracks_added_from_year} tracks from year: {year}")
                            
                        except Exception as e:
                            print(f"Error searching for year {year}: {e}")
                            continue
                
                # Strategy 3: Broad search using track name keywords from seeds
                if len(all_recommendations) + len(iteration_recommendations) < request.n_recommendations:
                    print(f"🔤 Strategy 3: Keyword-based search for diverse artists")
                    
                    for seed_track_id in current_seed_tracks[:2]:
                        if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                            break
                        try:
                            seed_track_info = sp.track(seed_track_id)
                            track_name = seed_track_info['name']
                            
                            # Extract keywords (take first word from track name)
                            keywords = track_name.split()[:2]  # First 2 words
                            
                            for keyword in keywords:
                                if len(keyword) > 3:  # Only meaningful words
                                    try:
                                        search_results = sp.search(q=keyword, type='track', limit=20)
                                        keyword_tracks = search_results.get('tracks', {}).get('items', [])
                                        
                                        tracks_added_from_keyword = 0
                                        for track in keyword_tracks:
                                            if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                                                break
                                            
                                            track_artist_id = track['artists'][0]['id'] if track.get('artists') else None
                                            if (track_artist_id and track_artist_id not in seen_artists and 
                                                track['id'] not in seen_track_ids):
                                                iteration_recommendations.append(track)
                                                seen_track_ids.add(track['id'])
                                                seen_artists.add(track_artist_id)
                                                tracks_added_from_keyword += 1
                                                print(f"  ✅ Added from keyword '{keyword}': {track['name']} by {track['artists'][0]['name']}")
                                        
                                        print(f"Added {tracks_added_from_keyword} tracks from keyword: {keyword}")
                                        
                                    except Exception as e:
                                        continue
                        except Exception as e:
                            continue
                
                # Add this iteration's recommendations to the main list
                all_recommendations.extend(iteration_recommendations)
                print(f"Added {len(iteration_recommendations)} recommendations in iteration {iteration}")
                print(f"Total unique artists found: {len(seen_artists)}")
                
                # Prepare seeds for next iteration (use newly found tracks as seeds)
                if iteration_recommendations and iteration < max_iterations:
                    # Use tracks from different artists as seeds for next iteration
                    current_seed_tracks = [track['id'] for track in iteration_recommendations[:4]]
                    print(f"Using {len(current_seed_tracks)} new tracks as seeds for next iteration")
                else:
                    print("No new tracks found for next iteration or max iterations reached")
                    break
                for artist_id in artists_to_explore:
                    if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                        break
                    try:
                        print(f"🎼 Deep diving into discography for artist: {artist_id}")
                        # Get ALL types of releases
                        albums = sp.artist_albums(artist_id, album_type='album,single,compilation', limit=15)
                        albums_to_check = albums['items'][:10]  # Check more albums
                        
                        albums_processed = 0
                        for album in albums_to_check:
                            if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                                break
                            try:
                                album_tracks = sp.album_tracks(album['id'], limit=20)
                                tracks_to_add = min(5, len(album_tracks['items']))  # Up to 5 tracks per album
                                tracks_added_from_album = 0
                                
                                for track in album_tracks['items'][:tracks_to_add]:
                                    if (track['id'] and track['id'] not in seen_track_ids and 
                                        len(all_recommendations) + len(iteration_recommendations) < request.n_recommendations):
                                        try:
                                            # Get full track info (album_tracks doesn't include full album info)
                                            full_track = sp.track(track['id'])
                                            if full_track and full_track.get('is_playable', True) and not full_track.get('is_local', False):
                                                iteration_recommendations.append(full_track)
                                                seen_track_ids.add(track['id'])
                                                tracks_added_from_album += 1
                                                print(f"  ✅ Added: {full_track['name']} from {album['name']}")
                                        except Exception as e:
                                            print(f"Error getting full track info for {track['id']}: {e}")
                                            continue
                                
                                if tracks_added_from_album > 0:
                                    albums_processed += 1
                                    print(f"  📀 Album '{album['name']}': Added {tracks_added_from_album} tracks")
                                    
                            except Exception as e:
                                print(f"Error getting tracks from album {album['id']}: {e}")
                                continue
                        
                        print(f"Processed {albums_processed} albums for artist {artist_id}")
                                
                    except Exception as e:
                        print(f"Error getting albums for artist {artist_id}: {e}")
                        continue
                
                # Strategy 2: If still need more, get artist's top tracks and featured tracks
                if len(all_recommendations) + len(iteration_recommendations) < request.n_recommendations:
                    print(f"� Strategy 2: Getting top tracks from {len(artists_to_explore)} artists")
                    for artist_id in artists_to_explore:
                        if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                            break
                        try:
                            top_tracks = sp.artist_top_tracks(artist_id)
                            tracks_added = 0
                            for track in top_tracks['tracks']:
                                if (track['id'] not in seen_track_ids and 
                                    len(all_recommendations) + len(iteration_recommendations) < request.n_recommendations):
                                    iteration_recommendations.append(track)
                                    seen_track_ids.add(track['id'])
                                    tracks_added += 1
                                    print(f"  ✅ Top track: {track['name']}")
                            print(f"Added {tracks_added} top tracks from artist {artist_id}")
                        except Exception as e:
                            print(f"Error getting top tracks for artist {artist_id}: {e}")
                            continue
                
                # Strategy 3: Search for tracks with similar names/keywords from our seeds
                if len(all_recommendations) + len(iteration_recommendations) < request.n_recommendations:
                    print(f"🔍 Strategy 3: Keyword-based search from seed tracks")
                    for seed_track_id in current_seed_tracks[:3]:  # Use first 3 seed tracks for search
                        if len(all_recommendations) + len(iteration_recommendations) >= request.n_recommendations:
                            break
                        try:
                            seed_track_info = sp.track(seed_track_id)
                            # Extract keywords from track name for search
                            track_name = seed_track_info['name']
                            artist_name = seed_track_info['artists'][0]['name']
                            
                            # Search using artist name to find similar artists' tracks
                            search_results = sp.search(q=f'artist:"{artist_name}"', type='track', limit=20)
                            tracks_added = 0
                            
                            for track in search_results['tracks']['items']:
                                if (track['id'] not in seen_track_ids and 
                                    len(all_recommendations) + len(iteration_recommendations) < request.n_recommendations and
                                    track['artists'][0]['id'] != seed_track_info['artists'][0]['id']):  # Different artist
                                    iteration_recommendations.append(track)
                                    seen_track_ids.add(track['id'])
                                    tracks_added += 1
                                    print(f"  🔍 Search result: {track['name']} by {track['artists'][0]['name']}")
                            
                            print(f"Added {tracks_added} tracks from search based on '{artist_name}'")
                            
                        except Exception as e:
                            print(f"Error in search strategy for seed {seed_track_id}: {e}")
                            continue
                
                # Add this iteration's recommendations to the main list
                all_recommendations.extend(iteration_recommendations)
                print(f"Added {len(iteration_recommendations)} recommendations in iteration {iteration}")
                
                # Prepare seeds for next iteration (use newly found tracks as seeds)
                if iteration_recommendations and iteration < max_iterations:
                    # Use tracks from different artists as seeds for next iteration
                    next_seeds = []
                    artists_used = set()
                    for track in iteration_recommendations[:8]:  # More seeds for next iteration
                        track_artist = track.get('artists', [{}])[0].get('id')
                        if track_artist and track_artist not in artists_used:
                            next_seeds.append(track['id'])
                            artists_used.add(track_artist)
                    
                    current_seed_tracks = next_seeds if next_seeds else current_seed_tracks
                    print(f"Using {len(current_seed_tracks)} tracks from different artists as seeds for next iteration")
                else:
                    print("No new tracks found for next iteration or max iterations reached")
                    break  # No new recommendations found, stop iterating
            
            print(f"✅ Generated {len(all_recommendations)} recommendations using ARTIST-DIVERSE strategy")
            print(f"Total unique artists: {len(seen_artists)}")
            
        except Exception as e:
            print(f"Error in ARTIST-DIVERSE strategy: {e}")
            raise HTTPException(status_code=500, detail=f"Unable to generate recommendations: {str(e)}")
        
        # Format recommendations using standardized format
        recommendations = []
        for track in all_recommendations:
            recommendations.append(RecommendationUtils.format_track_recommendation(track, "Manual Discovery"))
        
        print(f"✅ Generated {len(recommendations)} manual recommendations")
        
        return {
            "recommendations": recommendations,
            "algorithm": "Artist-Diverse Discovery (Genre + Year + Keyword Search)",
            "seeds_used": {
                "track_count": len(request.seed_tracks),
                "artist_count": len(request.seed_artists),
                "playlist_count": len(request.seed_playlists),
                "total_seed_tracks": len(unique_seed_tracks),
                "selected_for_analysis": len(valid_track_ids)
            },
            "user_preferences": {
                "popularity": request.popularity
            },
            "generation_stats": {
                "requested": request.n_recommendations,
                "generated": len(recommendations),
                "iterations_used": iteration
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Manual discovery error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
