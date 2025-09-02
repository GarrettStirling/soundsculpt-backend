import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class YouTubeService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
    
    def search_track(self, track_name: str, artist_name: str) -> Optional[Dict[str, Any]]:
        """
        Search for a track on YouTube and return the best match with audio URL
        Uses strict matching to avoid incorrect songs
        """
        try:
            # Create multiple search queries with increasing specificity
            search_queries = [
                f'"{track_name}" "{artist_name}" official audio',
                f'"{track_name}" "{artist_name}" official music video',
                f'"{track_name}" "{artist_name}" official',
                f'"{track_name}" by "{artist_name}"',
            ]
            
            for query in search_queries:
                # Search YouTube
                search_url = f"{self.base_url}/search"
                params = {
                    'part': 'snippet',
                    'q': query,
                    'type': 'video',
                    'videoCategoryId': '10',  # Music category
                    'maxResults': 10,
                    'key': self.api_key
                }
                
                response = requests.get(search_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if not data.get('items'):
                    continue
                
                # Strict matching: look for exact matches
                for item in data['items']:
                    title = item['snippet']['title'].lower()
                    description = item['snippet']['description'].lower()
                    channel_title = item['snippet']['channelTitle'].lower()
                    
                    # Check if both track name and artist are in the title or description
                    track_in_title = track_name.lower() in title
                    artist_in_title = artist_name.lower() in title
                    artist_in_channel = artist_name.lower() in channel_title
                    
                    # More strict matching - both track and artist should be present
                    track_words = set(track_name.lower().split())
                    artist_words = set(artist_name.lower().split())
                    title_words = set(title.split())
                    
                    track_word_matches = len(track_words.intersection(title_words))
                    artist_word_matches = len(artist_words.intersection(title_words)) or artist_in_channel
                    
                    # Strict criteria for a match
                    is_official = any(keyword in title or keyword in description or keyword in channel_title 
                                    for keyword in ['official', 'vevo', 'records', 'music'])
                    
                    # Must have significant word overlap for both track and artist
                    good_track_match = track_in_title or track_word_matches >= len(track_words) * 0.6
                    good_artist_match = artist_in_title or artist_in_channel or artist_word_matches
                    
                    if good_track_match and good_artist_match:
                        # Additional verification: check video duration (music videos are typically 2-8 minutes)
                        video_id = item['id']['videoId']
                        video_details = self._get_video_details(video_id)
                        
                        if video_details and self._is_reasonable_duration(video_details.get('duration')):
                            # Calculate confidence score
                            confidence_score = 0
                            if track_in_title: confidence_score += 30
                            if artist_in_title or artist_in_channel: confidence_score += 30
                            if is_official: confidence_score += 20
                            if track_word_matches >= len(track_words) * 0.8: confidence_score += 10
                            if artist_word_matches: confidence_score += 10
                            
                            confidence = 'high' if confidence_score >= 70 else 'medium' if confidence_score >= 50 else 'low'
                            
                            # This looks like a good match
                            return {
                                'video_id': video_id,
                                'title': item['snippet']['title'],
                                'channel': item['snippet']['channelTitle'],
                                'thumbnail': item['snippet']['thumbnails'].get('default', {}).get('url'),
                                'duration': video_details['duration'],
                                'view_count': video_details.get('view_count', 0),
                                'youtube_url': f"https://www.youtube.com/watch?v={video_id}",
                                'embed_url': f"https://www.youtube.com/embed/{video_id}?autoplay=1&controls=1&enablejsapi=1",
                                'confidence': confidence,
                                'search_query': query,
                                'match_score': confidence_score
                            }
            
            # If no good match found, return None instead of a poor match
            logger.warning(f"No reliable YouTube match found for: {track_name} by {artist_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching YouTube for {track_name} by {artist_name}: {str(e)}")
            return None
    
    def _get_video_details(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a video"""
        try:
            video_url = f"{self.base_url}/videos"
            video_params = {
                'part': 'contentDetails,statistics',
                'id': video_id,
                'key': self.api_key
            }
            
            video_response = requests.get(video_url, params=video_params)
            video_response.raise_for_status()
            video_data = video_response.json()
            
            if not video_data.get('items'):
                return None
            
            video_info = video_data['items'][0]
            return {
                'duration': video_info['contentDetails']['duration'],
                'view_count': video_info['statistics'].get('viewCount', 0)
            }
        except:
            return None
    
    def _is_reasonable_duration(self, duration_iso: str) -> bool:
        """Check if video duration is reasonable for a music track (30 seconds to 20 minutes)"""
        try:
            # Parse ISO 8601 duration (PT4M33S format)
            import re
            match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_iso)
            if not match:
                return False
            
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            
            total_seconds = hours * 3600 + minutes * 60 + seconds
            
            # Music tracks are typically between 30 seconds and 20 minutes
            return 30 <= total_seconds <= 1200
        except:
            return True  # If we can't parse, assume it's reasonable
    
    def get_audio_stream_url(self, video_id: str) -> Optional[str]:
        """
        This would require a separate service like youtube-dl or pytube
        For now, we'll use the embed URL which YouTube handles
        """
        return f"https://www.youtube.com/embed/{video_id}?autoplay=1&controls=1&enablejsapi=1"
