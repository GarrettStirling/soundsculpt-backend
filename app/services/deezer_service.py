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
    
    def _extract_primary_artist(self, artist_name: str) -> str:
        """Extract the primary artist from multi-artist strings"""
        if not artist_name:
            return ""
        
        # Handle common separators
        separators = [',', '&', 'feat.', 'featuring', 'ft.', 'with']
        
        for sep in separators:
            if sep in artist_name.lower():
                return artist_name.split(sep)[0].strip()
        
        return artist_name.strip()
    
    def _split_artists(self, artist_string: str) -> list:
        """Split multi-artist string into individual artists"""
        if not artist_string:
            return []
        
        # Handle different separators
        separators = [',', '&', 'feat.', 'featuring', 'ft.', 'with']
        
        for sep in separators:
            if sep in artist_string.lower():
                return [artist.strip() for artist in artist_string.split(sep) if artist.strip()]
        
        return [artist_string.strip()]
    
    def _check_artist_match(self, search_artist: str, deezer_artist: str) -> bool:
        """Enhanced artist matching for multi-artist scenarios"""
        if not search_artist or not deezer_artist:
            return False
        
        # Direct match
        if search_artist in deezer_artist or deezer_artist in search_artist:
            return True
        
        # Check if any individual artist from search matches
        search_artists = self._split_artists(search_artist)
        deezer_artists = self._split_artists(deezer_artist)
        
        for search_artist_individual in search_artists:
            for deezer_artist_individual in deezer_artists:
                if (search_artist_individual in deezer_artist_individual or 
                    deezer_artist_individual in search_artist_individual):
                    return True
        
        # Check primary artist match
        search_primary = self._extract_primary_artist(search_artist)
        deezer_primary = self._extract_primary_artist(deezer_artist)
        
        if (search_primary in deezer_primary or deezer_primary in search_primary):
            return True
        
        return False
        
    def search_track(self, track_name: str, artist_name: str) -> Dict:
        """
        Search for a track on Deezer and return preview URL if available
        Handles multi-artist tracks by trying multiple search strategies
        """
        try:
            logger.info(f"🔍 Searching Deezer for: '{track_name}' by '{artist_name}'")
            
            # Create multiple search strategies for multi-artist tracks
            search_strategies = []
            
            # Strategy 1: Full artist name
            search_strategies.append(f"{track_name} {artist_name}")
            
            # Strategy 2: Extract primary artist (for multi-artist strings)
            primary_artist = self._extract_primary_artist(artist_name)
            if primary_artist != artist_name:
                search_strategies.append(f"{track_name} {primary_artist}")
            
            # Strategy 3: Try each individual artist (for multi-artist strings)
            if ',' in artist_name or '&' in artist_name or 'feat.' in artist_name.lower():
                individual_artists = self._split_artists(artist_name)
                for individual_artist in individual_artists:
                    if individual_artist.strip():
                        search_strategies.append(f"{track_name} {individual_artist.strip()}")
            
            # Strategy 4: Just track name (fallback)
            search_strategies.append(track_name)
            
            # Remove duplicates while preserving order
            unique_strategies = []
            seen = set()
            for strategy in search_strategies:
                if strategy not in seen:
                    unique_strategies.append(strategy)
                    seen.add(strategy)
            
            search_strategies = unique_strategies
            
            # Try each search strategy
            search_url = f"{self.base_url}/search"
            
            for i, search_query in enumerate(search_strategies):
                try:
                    logger.info(f"🔍 Strategy {i+1}: Searching Deezer with '{search_query}'")
                    
                    params = {
                        'q': search_query,
                        'limit': 10
                    }
                    
                    response = requests.get(search_url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get('data'):
                        logger.info(f"✅ Found results with strategy {i+1}: '{search_query}'")
                        break
                    else:
                        logger.info(f"❌ No results with strategy {i+1}: '{search_query}'")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Strategy {i+1} failed: {e}")
                    continue
            
            if not data.get('data'):
                logger.info(f"❌ No Deezer results found with any strategy")
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
                
                # Check if track name matches reasonably well
                track_match = (normalized_track_name in normalized_title or 
                              normalized_title in normalized_track_name)
                
                # Enhanced artist matching for multi-artist scenarios
                artist_match = self._check_artist_match(normalized_artist_name, normalized_artist)
                
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
