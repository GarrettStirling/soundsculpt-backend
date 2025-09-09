from fastapi import APIRouter, HTTPException, Header, Query
from app.services.spotify_service import SpotifyService
from typing import Optional, Dict, List
from pydantic import BaseModel
import spotipy

router = APIRouter(prefix="/spotify", tags=["Spotify Data"])

# Initialize services
spotify_service = SpotifyService()

class UpdatePlaylistRequest(BaseModel):
    track_uris: List[str]

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
    Note: Deezer service is currently disabled - returns not found
    """
    try:
        print(f"🎵 Deezer service disabled - skipping search for: '{track_name}' by '{artist_name}'")
        
        # Return not found since Deezer service is not implemented
        return {
            "found": False,
            "error": "Deezer service not available"
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
    limit: int = Query(50, description="Number of playlists to return per request")
):
    """Get user's saved playlists with simple query parameter"""
    try:
        sp = spotify_service.create_spotify_client(token)
        
        # Get all playlists by paginating through results
        all_playlists = []
        results = sp.current_user_playlists(limit=limit)
        all_playlists.extend(results['items'])
        
        # Continue fetching if there are more playlists
        while results['next']:
            results = sp.next(results)
            all_playlists.extend(results['items'])
        
        playlists = []
        for playlist in all_playlists:
            playlists.append({
                "id": playlist['id'],
                "name": playlist['name'],
                "description": playlist['description'],
                "tracks_total": playlist['tracks']['total'],
                "public": playlist['public'],
                "collaborative": playlist['collaborative'],
                "external_urls": playlist['external_urls'],
                "images": playlist['images'],
                "owner": {
                    "id": playlist['owner']['id'],
                    "display_name": playlist['owner']['display_name']
                }
            })
        
        return {
            "playlists": playlists,
            "total": len(playlists)
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching playlists: {str(e)}")

@router.get("/playlist-tracks")
async def get_playlist_tracks(
    token: str = Query(..., description="Spotify access token"),
    playlist_id: str = Query(..., description="Spotify playlist ID")
):
    """
    Get tracks from a specific Spotify playlist
    """
    try:
        sp = spotify_service.create_spotify_client(token)
        
        # Get all playlist tracks with pagination
        tracks = []
        results = sp.playlist_tracks(playlist_id, limit=50)
        tracks.extend(results['items'])
        
        # Continue fetching if there are more tracks
        while results['next']:
            results = sp.next(results)
            tracks.extend(results['items'])
        
        track_list = []
        for item in tracks:
            if item['track'] and item['track']['type'] == 'track':
                track = item['track']
                
                # Get artist names
                artists = ', '.join([artist['name'] for artist in track['artists']])
                
                # Build track data
                track_data = {
                    "id": track['id'],
                    "uri": track['uri'],  # Add URI for playlist updates
                    "name": track['name'],
                    "artist": artists,
                    "album": track['album']['name'],
                    "duration_ms": track['duration_ms'],
                    "external_url": track['external_urls']['spotify'],
                    "preview_url": track.get('preview_url'),
                    "images": track['album'].get('images', [])
                }
                
                track_list.append(track_data)
        
        return {
            "tracks": track_list,
            "total": len(track_list)
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching playlist tracks: {str(e)}")

@router.put("/update-playlist")
async def update_playlist(
    request: UpdatePlaylistRequest,
    token: str = Query(...),
    playlist_id: str = Query(...)
):
    """Update a playlist with new track order using direct Spotify Web API"""
    try:
        import requests
        
        print(f"🎵 Updating playlist {playlist_id} with {len(request.track_uris)} tracks")
        print(f"🎵 Track URIs: {request.track_uris[:3]}...") # Show first 3 for debugging
        
        # Use direct Spotify Web API PUT request to replace all tracks
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Spotify Web API can handle up to 100 tracks per request
        batch_size = 100
        all_snapshot_ids = []
        
        for i in range(0, len(request.track_uris), batch_size):
            batch = request.track_uris[i:i + batch_size]
            
            if i == 0:
                # Replace all tracks for the first batch using PUT
                url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
                data = {"uris": batch}
                response = requests.put(url, headers=headers, json=data)
            else:
                # Add additional tracks using POST
                url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
                data = {"uris": batch}
                response = requests.post(url, headers=headers, json=data)
            
            if response.status_code not in [200, 201]:
                error_detail = response.json() if response.content else {"error": "Unknown error"}
                print(f"❌ Spotify API Error: Status {response.status_code}, Details: {error_detail}")
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"Spotify API error: {error_detail}"
                )
            
            result = response.json()
            if "snapshot_id" in result:
                all_snapshot_ids.append(result["snapshot_id"])
        
        print(f"✅ Playlist updated successfully")
        
        return {
            "success": True,
            "message": "Playlist updated successfully",
            "snapshot_id": all_snapshot_ids[0] if all_snapshot_ids else None,
            "total_batches": len(all_snapshot_ids)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating playlist: {str(e)}")
        print(f"❌ Error type: {type(e)}")
        raise HTTPException(status_code=400, detail=f"Error updating playlist: {str(e)}")
