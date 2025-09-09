from fastapi import APIRouter, HTTPException, Header
from app.services.youtube_service import YouTubeService
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize YouTube service
youtube_api_key = os.getenv('YOUTUBE_API_KEY')
youtube_service = YouTubeService(youtube_api_key) if youtube_api_key else None

@router.post("/get-youtube-url")
async def get_youtube_url(
    track_name: str,
    artist_name: str,
    authorization: str = Header(None)
):
    """
    Get YouTube URL for a specific track
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Authorization required")
    
    if not youtube_service:
        raise HTTPException(status_code=500, detail="YouTube service not configured")
    
    try:
        print(f"🎵 YOUTUBE DEBUG: Searching for '{track_name}' by '{artist_name}'")
        result = youtube_service.search_track(track_name, artist_name)
        
        if not result:
            print(f"❌ YOUTUBE DEBUG: No results found for '{track_name}' by '{artist_name}'")
            raise HTTPException(status_code=404, detail="Track not found on YouTube")
        
        print(f"✅ YOUTUBE DEBUG: Found video - ID: {result.get('video_id')}, Title: {result.get('title')}, URL: {result.get('youtube_url')}")
        
        return {
            "success": True,
            "youtube_data": result
        }
        
    except Exception as e:
        logger.error(f"Error getting YouTube URL for {track_name} by {artist_name}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get YouTube URL")
