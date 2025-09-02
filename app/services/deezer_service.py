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
        Search for a track on Deezer and return the best match with preview
        Uses improved matching logic to avoid wrong songs
        """
        try:
            # Clean the search query
            query = f'"{track_name}" "{artist_name}"'.strip()
            
            # Search for the track
            search_url = f"{self.base_url}/search"
            params = {
                'q': query,
                'limit': 25  # Get more results to find best match
            }
            
            response = requests.get(search_url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                tracks = data.get('data', [])
                
                # Normalize names for comparison
                track_lower = track_name.lower().strip()
                artist_lower = artist_name.lower().strip()
                
                # Remove common parenthetical content for matching
                track_clean = track_lower.replace('(acoustic)', '').replace('(live)', '').replace('(remix)', '').strip()
                
                # Look for exact or very close matches first
                best_match = None
                best_score = 0
                
                for track in tracks:
                    preview_url = track.get('preview')
                    if not preview_url or preview_url == "":
                        continue
                    
                    deezer_title = track.get('title', '').lower().strip()
                    deezer_artist = track.get('artist', {}).get('name', '').lower().strip()
                    
                    # Calculate matching score
                    score = 0
                    
                    # Exact track name match gets highest score
                    if track_lower == deezer_title:
                        score += 50
                    elif track_clean in deezer_title or deezer_title in track_clean:
                        score += 30
                    elif any(word in deezer_title for word in track_lower.split() if len(word) > 2):
                        score += 10
                    
                    # Exact artist match
                    if artist_lower == deezer_artist:
                        score += 50
                    elif artist_lower in deezer_artist or deezer_artist in artist_lower:
                        score += 30
                    elif any(word in deezer_artist for word in artist_lower.split() if len(word) > 2):
                        score += 10
                    
                    # Bonus for having both artist and track words
                    if score >= 60:  # Good match threshold
                        best_match = track
                        best_score = score
                        break  # Take first good match
                    elif score > best_score:
                        best_match = track
                        best_score = score
                
                if best_match and best_score >= 30:  # Minimum threshold
                    print(f"✅ Found match with score {best_score}: '{best_match.get('title')}' by '{best_match.get('artist', {}).get('name')}'")
                    return {
                        'deezer_id': best_match.get('id'),
                        'title': best_match.get('title'),
                        'artist': best_match.get('artist', {}).get('name'),
                        'preview_url': best_match.get('preview'),
                        'duration': best_match.get('duration'),
                        'album': best_match.get('album', {}).get('title'),
                        'track_name': best_match.get('title'),  # Add standardized field names
                        'artist_name': best_match.get('artist', {}).get('name'),
                        'album_name': best_match.get('album', {}).get('title'),
                        'match_score': best_score
                    }
                
                # If no good match found, return None
                print(f"❌ No suitable Deezer match found for: {track_name} by {artist_name} (best score: {best_score})")
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
