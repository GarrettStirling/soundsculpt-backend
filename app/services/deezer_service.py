"""
Deezer API Service - For getting audio previews
"""

import requests
import os
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()

class DeezerService:
    def __init__(self):
        self.api_key = os.getenv('RAPIDAPI_KEY')
        self.base_url = "https://deezerdevs-deezer.p.rapidapi.com"
        self.headers = {
            'X-RapidAPI-Key': self.api_key,
            'X-RapidAPI-Host': 'deezerdevs-deezer.p.rapidapi.com'
        }
    
    def search_track(self, track_name: str, artist_name: str) -> Optional[Dict]:
        """
        Search for a track on Deezer and return the first match with preview
        """
        try:
            # Clean the search query
            query = f"{track_name} {artist_name}".strip()
            
            # Search for the track
            search_url = f"{self.base_url}/search"
            params = {
                'q': query,
                'limit': 10  # Get multiple results to find one with preview
            }
            
            response = requests.get(search_url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                tracks = data.get('data', [])
                
                # Look for a track with a preview URL
                for track in tracks:
                    preview_url = track.get('preview')
                    if preview_url and preview_url != "":
                        return {
                            'deezer_id': track.get('id'),
                            'title': track.get('title'),
                            'artist': track.get('artist', {}).get('name'),
                            'preview_url': preview_url,
                            'duration': track.get('duration'),
                            'album': track.get('album', {}).get('title')
                        }
                
                # If no track with preview found, return None
                print(f"No Deezer preview found for: {track_name} by {artist_name}")
                return None
            else:
                print(f"Deezer search failed with status {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error searching Deezer: {e}")
            return None
    
    def get_track_by_id(self, deezer_id: str) -> Optional[Dict]:
        """
        Get track details by Deezer ID
        """
        try:
            track_url = f"{self.base_url}/track/{deezer_id}"
            response = requests.get(track_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                track = response.json()
                preview_url = track.get('preview')
                
                if preview_url and preview_url != "":
                    return {
                        'deezer_id': track.get('id'),
                        'title': track.get('title'),
                        'artist': track.get('artist', {}).get('name'),
                        'preview_url': preview_url,
                        'duration': track.get('duration'),
                        'album': track.get('album', {}).get('title')
                    }
                else:
                    print(f"No preview available for Deezer track {deezer_id}")
                    return None
            else:
                print(f"Deezer track fetch failed with status {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error fetching Deezer track: {e}")
            return None
