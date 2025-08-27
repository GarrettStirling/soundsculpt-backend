"""
Recommendation API endpoints - Clean version
"""

from fastapi import APIRouter, HTTPException, Query
from app.services.recommendation_service import RecommendationService
from typing import List, Optional
import random

router = APIRouter(prefix="/recommendations", tags=["AI Recommendations"])

# Initialize recommendation service
recommendation_service = RecommendationService()

@router.get("/search-based-discovery")
async def search_based_discovery(
    token: str,
    n_recommendations: int = Query(30, ge=1, le=100, description="Number of songs to recommend")
):
    """
    Discover new music using search-based exploration
    Works around Spotify API limitations by using search and browse
    """
    try:
        from app.services.spotify_service import SpotifyService
        
        spotify_service = SpotifyService()
        sp = spotify_service.create_spotify_client(token)
        
        print(f"🔍 Search-based discovery for {n_recommendations} tracks...")
        
        # Step 1: Get your music profile
        print("📊 Analyzing your music profile...")
        
        # Get your top tracks and artists
        top_tracks = []
        top_artists = []
        
        for time_range in ['medium_term', 'short_term']:
            try:
                tracks = sp.current_user_top_tracks(limit=50, time_range=time_range)
                top_tracks.extend(tracks['items'])
                
                artists = sp.current_user_top_artists(limit=50, time_range=time_range)
                top_artists.extend(artists['items'])
            except Exception as e:
                print(f"Could not get {time_range} data: {e}")
        
        # Get your existing tracks to exclude
        your_track_ids = set()
        your_artist_names = set()
        
        # Add your top tracks
        for track in top_tracks:
            your_track_ids.add(track['id'])
            for artist in track['artists']:
                your_artist_names.add(artist['name'].lower())
        
        # Add playlist tracks
        try:
            playlists = sp.current_user_playlists(limit=50)
            for playlist in playlists['items']:
                if playlist['owner']['id'] == sp.me()['id']:
                    tracks = sp.playlist_tracks(playlist['id'])
                    for item in tracks['items']:
                        if item['track'] and item['track']['id']:
                            your_track_ids.add(item['track']['id'])
        except Exception as e:
            print(f"Warning: Could not check all playlists: {e}")
        
        print(f"✓ Found {len(your_track_ids)} tracks to exclude")
        print(f"✓ You listen to {len(your_artist_names)} different artists")
        
        # Step 2: Extract genres and styles from your artists
        your_genres = set()
        for artist in top_artists[:20]:  # Check top 20 artists
            if 'genres' in artist and artist['genres']:
                your_genres.update(artist['genres'])
        
        print(f"✓ Your music genres: {list(your_genres)[:10]}...")  # Show first 10
        
        # Step 3: Search for music using different strategies
        candidate_tracks = []
        search_strategies = []
        
        # Strategy 1: Search by genre combinations
        genre_list = list(your_genres)[:5]  # Use top 5 genres
        for genre in genre_list:
            search_strategies.append(f"genre:{genre}")
            search_strategies.append(f"genre:\"{genre}\" year:2020-2024")  # Recent music
        
        # Strategy 2: Search by your artist influences
        your_artist_list = list(your_artist_names)[:10]  # Use top 10 artists
        for artist in your_artist_list[:5]:  # Limit to 5 for performance
            search_strategies.append(f"artist:{artist}")
            search_strategies.append(f"similar to {artist}")  # Natural language search
        
        # Strategy 3: Search with temporal and discovery patterns
        if your_genres:
            # Use multiple genres instead of just the first one
            top_genres = list(your_genres)[:3]  # Use top 3 genres
            for genre in top_genres:
                search_strategies.extend([
                    f"{genre} new release",
                    f"{genre} year:2023-2024",  # Recent music in their genres
                    f"{genre} emerging"  # Discovering new artists in their genres
                ])
        
        # Strategy 4: Add some discovery variety
        search_strategies.extend([
            "new release",  # General new music
            "year:2024",    # Current year music
            "emerging artist"  # New artists discovery
        ])
        
        print(f"🔍 Using {len(search_strategies)} search strategies...")
        
        # Execute searches
        for strategy in search_strategies:
            try:
                print(f"Searching: {strategy}")
                results = sp.search(q=strategy, type='track', limit=20)
                
                for track in results['tracks']['items']:
                    # Skip if you already have this track
                    if track['id'] in your_track_ids:
                        continue
                    
                    # Skip if it's from an artist you already know well
                    artist_names = [a['name'].lower() for a in track['artists']]
                    if any(name in your_artist_names for name in artist_names):
                        continue
                    
                    # Skip very unpopular tracks (likely low quality)
                    if track['popularity'] < 20:
                        continue
                    
                    candidate_tracks.append({
                        "id": track['id'],
                        "name": track['name'],
                        "artist": ", ".join([a['name'] for a in track['artists']]),
                        "album": track['album']['name'],
                        "popularity": track['popularity'],
                        "preview_url": track['preview_url'],
                        "external_url": track['external_urls']['spotify'],
                        "release_date": track['album']['release_date'],
                        "source": f"Search: {strategy}"
                    })
                
                if len(candidate_tracks) >= n_recommendations * 5:  # Get plenty of options
                    break
                    
            except Exception as e:
                print(f"Search failed for '{strategy}': {e}")
                continue
        
        print(f"✓ Found {len(candidate_tracks)} candidates from search")
        
        # Step 4: Browse featured playlists for additional discovery
        try:
            print("🎵 Browsing featured playlists...")
            featured = sp.featured_playlists(limit=10, country='US')
            
            for playlist in featured['playlists']['items']:
                if 'discover' in playlist['name'].lower() or 'new' in playlist['name'].lower():
                    try:
                        tracks = sp.playlist_tracks(playlist['id'], limit=10)
                        for item in tracks['items']:
                            track = item['track']
                            if not track or track['id'] in your_track_ids:
                                continue
                            
                            artist_names = [a['name'].lower() for a in track['artists']]
                            if any(name in your_artist_names for name in artist_names):
                                continue
                            
                            if track['popularity'] >= 25:
                                candidate_tracks.append({
                                    "id": track['id'],
                                    "name": track['name'],
                                    "artist": ", ".join([a['name'] for a in track['artists']]),
                                    "album": track['album']['name'],
                                    "popularity": track['popularity'],
                                    "preview_url": track['preview_url'],
                                    "external_url": track['external_urls']['spotify'],
                                    "release_date": track['album']['release_date'],
                                    "source": f"Featured playlist: {playlist['name']}"
                                })
                    except Exception as e:
                        continue
        except Exception as e:
            print(f"Could not browse playlists: {e}")
        
        print(f"✓ Total candidates: {len(candidate_tracks)}")
        
        # Step 5: Remove duplicates and select the best ones
        seen_ids = set()
        unique_candidates = []
        
        for track in candidate_tracks:
            if track['id'] not in seen_ids:
                unique_candidates.append(track)
                seen_ids.add(track['id'])
        
        # Sort by popularity but add some randomization for variety
        unique_candidates.sort(key=lambda x: x['popularity'] + random.randint(-10, 10), reverse=True)
        
        final_recommendations = unique_candidates[:n_recommendations]
        
        print(f"🎉 Final recommendations: {len(final_recommendations)} tracks")
        
        return {
            "recommendations": final_recommendations,
            "total": len(final_recommendations),
            "discovery_stats": {
                "your_genres": list(your_genres)[:10],
                "tracks_excluded": len(your_track_ids),
                "artists_you_know": len(your_artist_names),
                "search_strategies_used": len(search_strategies),
                "total_candidates_found": len(candidate_tracks),
                "unique_candidates": len(unique_candidates)
            },
            "method": "Search-based discovery (bypassing recommendation APIs)"
        }
    
    except Exception as e:
        print(f"❌ Search discovery error: {e}")
        return {"error": f"Search discovery error: {str(e)}"}

@router.get("/custom")
async def get_custom_recommendations(
    token: str,
    track_ids: str = Query(..., description="Comma-separated list of Spotify track IDs"),
    n_recommendations: int = Query(30, ge=1, le=100, description="Number of songs to recommend")
):
    """
    Get AI-powered song recommendations based on specific tracks
    Format: track_ids should be like "4uLU6hMCjMI75M1A2tKUQC,2tGvwE8GcFKwNdoJYxrNCS"
    Note: May not work if audio features API access is unavailable
    """
    try:
        # Parse track IDs
        track_id_list = [tid.strip() for tid in track_ids.split(",") if tid.strip()]
        
        if not track_id_list:
            raise HTTPException(status_code=400, detail="No valid track IDs provided")
        
        if len(track_id_list) > 20:
            raise HTTPException(status_code=400, detail="Too many track IDs. Maximum is 20.")
        
        result = recommendation_service.get_recommendations(
            access_token=token,
            n_recommendations=n_recommendations,
            custom_track_ids=track_id_list
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Custom recommendation error: {str(e)}")

@router.get("/by-playlist")
async def get_recommendations_by_playlist(
    token: str,
    playlist_id: str = Query(..., description="Spotify playlist ID"),
    n_recommendations: int = Query(30, ge=1, le=100, description="Number of songs to recommend"),
    max_tracks_from_playlist: int = Query(50, ge=1, le=100, description="Max tracks to use from playlist as seeds")
):
    """
    Get recommendations based on tracks from a specific playlist
    Uses tracks from the playlist as seeds for recommendations
    Note: May not work if audio features API access is unavailable
    """
    try:
        from app.services.spotify_service import SpotifyService
        
        spotify_service = SpotifyService()
        sp = spotify_service.create_spotify_client(token)
        
        # Get tracks from playlist
        try:
            playlist_tracks = sp.playlist_tracks(playlist_id, limit=max_tracks_from_playlist)
            seed_track_ids = []
            
            for item in playlist_tracks['items']:
                if item['track'] and item['track']['id']:
                    seed_track_ids.append(item['track']['id'])
            
            if not seed_track_ids:
                raise HTTPException(status_code=400, detail="No tracks found in playlist")
            
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not access playlist: {str(e)}")
        
        # Get recommendations using the recommendation service
        result = recommendation_service.get_recommendations(
            access_token=token,
            n_recommendations=n_recommendations,
            custom_track_ids=seed_track_ids[:20]  # Limit to 20 seed tracks
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Add playlist info to the result
        result["seed_playlist_id"] = playlist_id
        result["seed_tracks_count"] = len(seed_track_ids)
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Playlist recommendation error: {str(e)}")
