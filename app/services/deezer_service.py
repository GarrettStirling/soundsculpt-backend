import requests
import logging
import unicodedata
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class DeezerService:
    def __init__(self):
        self.base_url = "https://api.deezer.com"
    
    def normalize_string(self, text: str) -> str:
        """
        Normalize accented characters and convert to lowercase for better matching
        Example: "Colón" -> "colon", "José" -> "jose"
        """
        if not text:
            return ""
        # Normalize unicode characters (NFD = Normalization Form Decomposed)
        normalized = unicodedata.normalize('NFD', text)
        # Remove accent marks (combining characters)
        without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        return without_accents.lower().strip()
        
    def search_track(self, track_name: str, artist_name: str) -> Dict:
        """
        Search for a track on Deezer and return preview URL if available
        """
        try:
            logger.info(f"🔍 Searching Deezer for: '{track_name}' by '{artist_name}'")
            
            # Create search query with both original and normalized versions
            search_query = f"{track_name} {artist_name}"
            normalized_query = f"{self.normalize_string(track_name)} {self.normalize_string(artist_name)}"
            
            # Add simplified version for tracks with parenthetical content
            simplified_track = re.sub(r'\s*\([^)]*\)', '', track_name).strip()
            simplified_query = f"{simplified_track} {artist_name}" if simplified_track != track_name else None
            
            # Search Deezer with original query first
            search_url = f"{self.base_url}/search"
            params = {
                'q': search_query,
                'limit': 10
            }
            
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # If no results with original query, try normalized query
            if not data.get('data') and search_query != normalized_query:
                logger.info(f"🔄 No results with original query, trying normalized: '{normalized_query}'")
                logger.info(f"   Original: '{search_query}' -> Normalized: '{normalized_query}'")
                params['q'] = normalized_query
                response = requests.get(search_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
            
            # If still no results and we have a simplified query, try that
            if not data.get('data') and simplified_query:
                logger.info(f"🔄 No results with normalized query, trying simplified: '{simplified_query}'")
                params['q'] = simplified_query
                response = requests.get(search_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
            
            if not data.get('data'):
                logger.info(f"❌ No Deezer results found for: '{search_query}' or '{normalized_query}'")
                return {
                    "found": False,
                    "error": "No results found"
                }
            
            # Look for the best match
            for track in data['data']:
                title = track['title']
                artist = track['artist']['name']
                
                # Normalize both search terms and Deezer results for better matching
                normalized_track_name = self.normalize_string(track_name)
                normalized_artist_name = self.normalize_string(artist_name)
                normalized_title = self.normalize_string(title)
                normalized_artist = self.normalize_string(artist)
                
                # Check for remix mismatch - if original doesn't have 'remix', don't match with remix
                original_has_remix = 'remix' in normalized_track_name
                deezer_has_remix = 'remix' in normalized_title
                
                if not original_has_remix and deezer_has_remix:
                    logger.info(f"🚫 Skipping remix mismatch: Original '{track_name}' (no remix) vs Deezer '{title}' (has remix)")
                    continue
                
                # Check if track name and artist match reasonably well
                track_match = (normalized_track_name in normalized_title or 
                              normalized_title in normalized_track_name)
                artist_match = (normalized_artist_name in normalized_artist or 
                               normalized_artist in normalized_artist_name)
                
                if track_match and artist_match:
                    # Check if preview is available
                    preview_url = track.get('preview')
                    if preview_url:
                        logger.info(f"✅ Found Deezer preview for: '{track_name}' by '{artist_name}'")
                        logger.info(f"   🎵 Title: {track['title']}")
                        logger.info(f"   🎵 Artist: {track['artist']['name']}")
                        logger.info(f"   🎵 Preview URL: {preview_url}")
                        
                        return {
                            "found": True,
                            "preview_url": preview_url,
                            "title": track['title'],
                            "artist": track['artist']['name'],
                            "album": track['album']['title'],
                            "duration": track['duration']
                        }
                    else:
                        logger.info(f"⚠️ Deezer track found but no preview available: '{track['title']}'")
                        continue
            
            logger.info(f"❌ No Deezer preview found for: '{search_query}'")
            return {
                "found": False,
                "error": "No preview available"
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Deezer API request failed: {e}")
            return {
                "found": False,
                "error": f"API request failed: {str(e)}"
            }
        except Exception as e:
            logger.error(f"❌ Deezer search error: {e}")
            return {
                "found": False,
                "error": str(e)
            }

# Create global instance
deezer_service = DeezerService()
