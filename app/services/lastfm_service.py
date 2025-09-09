"""
Last.fm API Service - For music similarity and recommendations
"""

import requests
import os
import time
import random
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

class LastFMService:
    def __init__(self):
        self.api_key = os.getenv('LASTFM_API_KEY')
        self.shared_secret = os.getenv('LASTFM_SHARED_SECRET')
        
        if not self.api_key or not self.shared_secret:
            print("WARNING: LASTFM_API_KEY and LASTFM_SHARED_SECRET not set. Last.fm features will be disabled.")
            self.api_key = None
            self.shared_secret = None
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        self.headers = {
            'User-Agent': 'Soundsculpt/1.0 (https://github.com/yourusername/soundsculpt)'
        }
    
    def _make_request(self, method: str, params: Dict) -> Optional[Dict]:
        """
        Make a request to the Last.fm API
        """
        if not self.api_key:
            print("Last.fm API key not available - skipping request")
            return None
            
        try:
            params.update({
                'method': method,
                'api_key': self.api_key,
                'format': 'json'
            })
            
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'error' in data:
                    print(f"Last.fm API error: {data.get('message', 'Unknown error')}")
                    return None
                return data
            else:
                print(f"Last.fm API request failed with status {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error making Last.fm API request: {e}")
            return None
    
    def get_similar_artists(self, artist_name: str, limit: int = 20) -> List[Dict]:
        """
        Get artists similar to the given artist
        """
        try:
            params = {
                'artist': artist_name,
                'limit': limit
            }
            
            data = self._make_request('artist.getSimilar', params)
            if not data or 'similarartists' not in data:
                return []
            
            similar_artists = data['similarartists'].get('artist', [])
            if isinstance(similar_artists, dict):
                similar_artists = [similar_artists]
            
            return similar_artists
            
        except Exception as e:
            print(f"Error getting similar artists for {artist_name}: {e}")
            return []
    
    def get_similar_tracks(self, artist_name: str, track_name: str, limit: int = 20) -> List[Dict]:
        """
        Get tracks similar to the given track
        """
        try:
            params = {
                'artist': artist_name,
                'track': track_name,
                'limit': limit
            }
            
            data = self._make_request('track.getSimilar', params)
            if not data or 'similartracks' not in data:
                return []
            
            similar_tracks = data['similartracks'].get('track', [])
            if isinstance(similar_tracks, dict):
                similar_tracks = [similar_tracks]
            
            return similar_tracks
            
        except Exception as e:
            print(f"Error getting similar tracks for {track_name} by {artist_name}: {e}")
            return []
    
    def get_artist_top_tracks(self, artist_name: str, limit: int = 20) -> List[Dict]:
        """
        Get top tracks by an artist
        """
        try:
            params = {
                'artist': artist_name,
                'limit': limit
            }
            
            data = self._make_request('artist.getTopTracks', params)
            if not data or 'toptracks' not in data:
                return []
            
            top_tracks = data['toptracks'].get('track', [])
            if isinstance(top_tracks, dict):
                top_tracks = [top_tracks]
            
            return top_tracks
            
        except Exception as e:
            print(f"Error getting top tracks for {artist_name}: {e}")
            return []
    
    def get_artist_top_tags(self, artist_name: str) -> List[Dict]:
        """
        Get top tags (genres) for an artist
        """
        try:
            params = {
                'artist': artist_name
            }
            
            data = self._make_request('artist.getTopTags', params)
            if not data or 'toptags' not in data:
                return []
            
            tags = data['toptags'].get('tag', [])
            if isinstance(tags, dict):
                tags = [tags]
            
            return tags
            
        except Exception as e:
            print(f"Error getting tags for {artist_name}: {e}")
            return []
    
    def get_tag_top_tracks(self, tag_name: str, limit: int = 20) -> List[Dict]:
        """
        Get top tracks for a specific tag/genre
        """
        try:
            params = {
                'tag': tag_name,
                'limit': limit
            }
            
            data = self._make_request('tag.getTopTracks', params)
            if not data or 'tracks' not in data:
                return []
            
            tracks = data['tracks'].get('track', [])
            if isinstance(tracks, dict):
                tracks = [tracks]
            
            return tracks
            
        except Exception as e:
            print(f"Error getting top tracks for tag {tag_name}: {e}")
            return []
    
    def search_track(self, track_name: str, artist_name: str) -> Optional[Dict]:
        """
        Search for a track to get Last.fm data
        """
        try:
            params = {
                'track': track_name,
                'artist': artist_name,
                'limit': 1
            }
            
            data = self._make_request('track.search', params)
            if not data or 'results' not in data:
                return None
            
            results = data['results']
            if 'trackmatches' in results and 'track' in results['trackmatches']:
                tracks = results['trackmatches']['track']
                if isinstance(tracks, list) and len(tracks) > 0:
                    return tracks[0]
                elif isinstance(tracks, dict):
                    return tracks
            
            return None
            
        except Exception as e:
            print(f"Error searching for track {track_name} by {artist_name}: {e}")
            return None
