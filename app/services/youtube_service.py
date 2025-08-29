from youtubesearchpython import VideosSearch
import re
from typing import Optional

class YouTubeService:
    def __init__(self):
        pass
    
    def search_track_preview(self, track_name: str, artist_name: str) -> Optional[str]:
        """
        Search for a YouTube video of the track for audio preview
        Returns the YouTube video ID if found, None otherwise
        """
        try:
            # Clean up the search query
            query = f"{track_name} {artist_name}"
            # Remove featuring artists and extra info
            query = re.sub(r'\(feat\..*?\)', '', query)
            query = re.sub(r'\[.*?\]', '', query)
            query = query.strip()
            
            # Search for videos
            videos_search = VideosSearch(query, limit=5)
            results = videos_search.result()
            
            if results and 'result' in results:
                for video in results['result']:
                    # Prefer official videos, music videos, or audio uploads
                    title = video.get('title', '').lower()
                    channel = video.get('channel', {}).get('name', '').lower()
                    
                    # Skip live performances, covers, etc.
                    if any(word in title for word in ['live', 'cover', 'remix', 'karaoke', 'instrumental']):
                        continue
                    
                    # Prefer official channels or music-related channels
                    if any(word in channel for word in ['official', 'records', 'music', artist_name.lower()]):
                        video_id = video.get('id')
                        if video_id:
                            return video_id
                
                # If no official video found, return the first non-live result
                for video in results['result']:
                    title = video.get('title', '').lower()
                    if 'live' not in title:
                        video_id = video.get('id')
                        if video_id:
                            return video_id
            
            return None
            
        except Exception as e:
            print(f"YouTube search error for {track_name} by {artist_name}: {e}")
            return None
    
    def get_embed_url(self, video_id: str) -> str:
        """
        Convert YouTube video ID to embeddable URL
        """
        return f"https://www.youtube.com/embed/{video_id}?autoplay=1&start=30&end=60"
    
    def get_watch_url(self, video_id: str) -> str:
        """
        Convert YouTube video ID to watch URL
        """
        return f"https://www.youtube.com/watch?v={video_id}"
