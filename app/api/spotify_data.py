from fastapi import APIRouter, HTTPException, Header, Query
from app.services.spotify_service import SpotifyService
from app.services.deezer_service import DeezerService
from typing import Optional, Dict, List
import spotipy

router = APIRouter(prefix="/spotify", tags=["Spotify Data"])

# Initialize services
spotify_service = SpotifyService()
deezer_service = DeezerService()

@router.get("/test-token")
async def test_token(token: str):
    """Simple test endpoint that takes token as query parameter"""
    try:
        # Create Spotify client directly with token
        sp = spotify_service.create_spotify_client(token)
        
        # Get user profile as a simple test
        profile = spotify_service.get_user_profile(sp)
        
        return {
            "message": "Token works!",
            "user": profile.get("display_name", "Unknown"),
            "id": profile.get("id")
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token test failed: {str(e)}")

@router.get("/top-tracks-simple")
async def get_top_tracks_simple(
    token: str,
    time_range: str = "medium_term",  # short_term, medium_term, long_term
    limit: int = 20
):
    """Get user's top tracks using query parameter instead of header"""
    try:
        sp = spotify_service.create_spotify_client(token)
        
        # Get top tracks
        results = sp.current_user_top_tracks(
            limit=limit,
            time_range=time_range
        )
        
        tracks = []
        for track in results['items']:
            tracks.append({
                "name": track['name'],
                "artist": ", ".join([artist['name'] for artist in track['artists']]),
                "album": track['album']['name'],
                "popularity": track['popularity'],
                "external_url": track['external_urls']['spotify'],
                "duration_ms": track['duration_ms']
            })
        
        return {
            "tracks": tracks,
            "total": len(tracks),
            "time_range": time_range
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching top tracks: {str(e)}")

@router.get("/profile")
async def get_user_profile(authorization: str = Header(..., alias="Authorization")):
    """Get user's Spotify profile information"""
    try:
        # Extract token from Authorization header (format: "Bearer <token>")
        if authorization.startswith("Bearer "):
            access_token = authorization.replace("Bearer ", "")
        else:
            access_token = authorization
        
        # Create Spotify client
        sp = spotify_service.create_spotify_client(access_token)
        
        # Get user profile
        profile = spotify_service.get_user_profile(sp)
        
        return {
            "display_name": profile.get("display_name"),
            "id": profile.get("id"),
            "followers": profile.get("followers", {}).get("total", 0),
            "country": profile.get("country"),
            "product": profile.get("product"),  # free, premium, etc.
            "images": profile.get("images", [])
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching profile: {str(e)}")

@router.get("/top-tracks")
async def get_top_tracks(
    authorization: str = Header(..., alias="Authorization"),
    time_range: str = "medium_term",  # short_term, medium_term, long_term
    limit: int = 20
):
    """Get user's top tracks"""
    try:
        if authorization.startswith("Bearer "):
            access_token = authorization.replace("Bearer ", "")
        else:
            access_token = authorization
        sp = spotify_service.create_spotify_client(access_token)
        
        # Get top tracks
        results = sp.current_user_top_tracks(
            limit=limit,
            time_range=time_range
        )
        
        tracks = []
        for track in results['items']:
            tracks.append({
                "name": track['name'],
                "artist": ", ".join([artist['name'] for artist in track['artists']]),
                "album": track['album']['name'],
                "popularity": track['popularity'],
                "duration_ms": track['duration_ms'],
                "external_urls": track['external_urls'],
                "images": track['album']['images']
            })
        
        return {
            "time_range": time_range,
            "total": len(tracks),
            "tracks": tracks
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching top tracks: {str(e)}")

@router.get("/top-artists")
async def get_top_artists(
    authorization: str = Header(..., alias="Authorization"),
    time_range: str = "medium_term",
    limit: int = 20
):
    """Get user's top artists"""
    try:
        if authorization.startswith("Bearer "):
            access_token = authorization.replace("Bearer ", "")
        else:
            access_token = authorization
        sp = spotify_service.create_spotify_client(access_token)
        
        # Get top artists
        results = sp.current_user_top_artists(
            limit=limit,
            time_range=time_range
        )
        
        artists = []
        for artist in results['items']:
            artists.append({
                "name": artist['name'],
                "genres": artist['genres'],
                "popularity": artist['popularity'],
                "followers": artist['followers']['total'],
                "external_urls": artist['external_urls'],
                "images": artist['images']
            })
        
        return {
            "time_range": time_range,
            "total": len(artists),
            "artists": artists
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching top artists: {str(e)}")

@router.get("/recently-played")
async def get_recently_played(
    authorization: str = Header(..., alias="Authorization"),
    limit: int = 20
):
    """Get user's recently played tracks"""
    try:
        if authorization.startswith("Bearer "):
            access_token = authorization.replace("Bearer ", "")
        else:
            access_token = authorization
        sp = spotify_service.create_spotify_client(access_token)
        
        # Get recently played tracks
        results = sp.current_user_recently_played(limit=limit)
        
        tracks = []
        for item in results['items']:
            track = item['track']
            tracks.append({
                "name": track['name'],
                "artist": ", ".join([artist['name'] for artist in track['artists']]),
                "album": track['album']['name'],
                "played_at": item['played_at'],
                "duration_ms": track['duration_ms'],
                "external_urls": track['external_urls'],
                "images": track['album']['images']
            })
        
        return {
            "total": len(tracks),
            "tracks": tracks
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching recently played: {str(e)}")

@router.get("/playlists")
async def get_user_playlists(
    authorization: str = Header(..., alias="Authorization"),
    limit: int = 20
):
    """Get user's playlists"""
    try:
        if authorization.startswith("Bearer "):
            access_token = authorization.replace("Bearer ", "")
        else:
            access_token = authorization
        sp = spotify_service.create_spotify_client(access_token)
        
        # Get user playlists
        results = sp.current_user_playlists(limit=limit)
        
        playlists = []
        for playlist in results['items']:
            playlists.append({
                "name": playlist['name'],
                "description": playlist['description'],
                "tracks_total": playlist['tracks']['total'],
                "public": playlist['public'],
                "collaborative": playlist['collaborative'],
                "external_urls": playlist['external_urls'],
                "images": playlist['images']
            })
        
        return {
            "total": len(playlists),
            "playlists": playlists
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching playlists: {str(e)}")

@router.get("/deezer-preview")
async def get_deezer_preview(
    track_name: str = Query(..., description="Track name"),
    artist_name: str = Query(..., description="Artist name")
):
    """
    Get Deezer preview URL for a track
    """
    try:
        print(f"🎵 Searching Deezer for: '{track_name}' by '{artist_name}'")
        
        # Search for the track on Deezer
        deezer_result = deezer_service.search_track(track_name, artist_name)
        
        if deezer_result:
            print(f"✅ Found Deezer preview: {deezer_result['preview_url']}")
            return {
                "found": True,
                "preview_url": deezer_result['preview_url'],
                "deezer_id": deezer_result['deezer_id'],
                "title": deezer_result['title'],
                "artist": deezer_result['artist'],
                "duration": deezer_result['duration']
            }
        else:
            print(f"❌ No Deezer preview found for: '{track_name}' by '{artist_name}'")
            return {
                "found": False,
                "error": "No preview available on Deezer"
            }
            
    except Exception as e:
        print(f"Error getting Deezer preview: {e}")
        return {
            "found": False,
            "error": str(e)
        }

@router.get("/search")
async def search_spotify(
    token: str = Query(..., description="Spotify access token"),
    query: str = Query(..., description="Search query"),
    search_type: str = Query("track", description="Search type: track, artist, album, playlist"),
    limit: int = Query(20, description="Number of results to return")
):
    """Search Spotify for tracks, artists, albums, or playlists"""
    try:
        sp = spotify_service.create_spotify_client(token)
        
        results = sp.search(q=query, type=search_type, limit=limit)
        
        if search_type == "track":
            items = results['tracks']['items']
            formatted_items = []
            for item in items:
                formatted_items.append({
                    "id": item['id'],
                    "name": item['name'],
                    "artist": ", ".join([artist['name'] for artist in item['artists']]),
                    "album": item['album']['name'],
                    "duration_ms": item['duration_ms'],
                    "popularity": item['popularity'],
                    "external_urls": item['external_urls'],
                    "preview_url": item.get('preview_url'),
                    "images": item['album']['images']
                })
        elif search_type == "artist":
            items = results['artists']['items']
            formatted_items = []
            for item in items:
                formatted_items.append({
                    "id": item['id'],
                    "name": item['name'],
                    "genres": item['genres'],
                    "popularity": item['popularity'],
                    "followers": item['followers']['total'],
                    "external_urls": item['external_urls'],
                    "images": item['images']
                })
        else:
            # For album and playlist, return basic structure
            items = results[f'{search_type}s']['items']
            formatted_items = []
            for item in items:
                formatted_items.append({
                    "id": item['id'],
                    "name": item['name'],
                    "external_urls": item['external_urls'],
                    "images": item.get('images', [])
                })
        
        return {
            "results": formatted_items,
            "total": len(formatted_items),
            "query": query,
            "type": search_type
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Search error: {str(e)}")

@router.get("/user-playlists")
async def get_user_playlists_simple(
    token: str = Query(..., description="Spotify access token"),
    limit: int = Query(50, description="Number of playlists to return")
):
    """Get user's saved playlists with simple query parameter"""
    try:
        sp = spotify_service.create_spotify_client(token)
        
        results = sp.current_user_playlists(limit=limit)
        
        playlists = []
        for playlist in results['items']:
            playlists.append({
                "id": playlist['id'],
                "name": playlist['name'],
                "description": playlist['description'],
                "tracks_total": playlist['tracks']['total'],
                "public": playlist['public'],
                "collaborative": playlist['collaborative'],
                "external_urls": playlist['external_urls'],
                "images": playlist['images'],
                "owner": playlist['owner']['display_name']
            })
        
        return {
            "playlists": playlists,
            "total": len(playlists)
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching playlists: {str(e)}")

@router.get("/test-deezer-connection")
async def test_deezer_connection():
    """
    Test Deezer API connection with a known track
    """
    try:
        # Test with a well-known track
        test_result = deezer_service.search_track("Come A Little Closer", "Cage The Elephant")
        
        if test_result:
            return {
                "status": "success",
                "message": "Deezer API connection working",
                "test_track": test_result
            }
        else:
            return {
                "status": "no_preview",
                "message": "Deezer API connected but no preview found for test track"
            }
            
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Deezer API connection failed: {str(e)}",
            "note": "Make sure RAPIDAPI_KEY is set in .env file"
        }
