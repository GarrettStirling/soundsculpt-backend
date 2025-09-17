"""
Utility functions for Last.fm-based recommendation services
"""

import requests
import os
import time
import random
from typing import List, Dict, Optional, Set
from .spotify_service import SpotifyService
from dotenv import load_dotenv

load_dotenv()

class RecommendationUtils:
    def __init__(self):
        self.spotify_service = SpotifyService()
    
    def add_progress_message(self, message: str, progress_messages: List[str]) -> None:
        """Add a progress message with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        progress_messages.append(f"[{timestamp}] {message}")
    
    def get_spotify_album_cover(self, track_name: str, artist_name: str, access_token: str) -> str:
        """
        Get album cover from Spotify for a track
        
        Args:
            track_name (str): Name of the track
            artist_name (str): Name of the artist
            access_token (str): Spotify access token
            
        Returns:
            str: URL of the album cover image
        """
        try:
            if not access_token:
                return 'https://picsum.photos/300/300?random=1'
            
            # Search for the track on Spotify
            sp = self.spotify_service.create_spotify_client(access_token)
            search_query = f"track:{track_name} artist:{artist_name}"
            
            results = sp.search(q=search_query, type='track', limit=1)
            
            if results and results.get('tracks', {}).get('items'):
                track = results['tracks']['items'][0]
                album = track.get('album', {})
                images = album.get('images', [])
                
                if images:
                    # Return the medium-sized image (usually index 1)
                    cover_url = images[1]['url'] if len(images) > 1 else images[0]['url']
                    return cover_url
            
            return 'https://picsum.photos/300/300?random=1'
            
        except Exception as e:
            print(f"Error getting album cover for {track_name} by {artist_name}: {e}")
            return 'https://picsum.photos/300/300?random=1'

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

    def _find_best_track_match(self, tracks: List[Dict], target_track_name: str, target_artist_name: str) -> Dict:
        """Find the best matching track from Spotify results"""
        if not tracks:
            return None
        
        target_track_lower = target_track_name.lower()
        target_artist_lower = target_artist_name.lower()
        
        # Score each track based on name and artist similarity
        best_match = None
        best_score = 0
        
        for track in tracks:
            track_name = track.get('name', '').lower()
            track_artists = [artist.get('name', '').lower() for artist in track.get('artists', [])]
            
            # Calculate similarity score
            score = 0
            
            # Track name similarity (most important)
            if target_track_lower in track_name or track_name in target_track_lower:
                score += 10
            
            # Artist similarity
            for artist in track_artists:
                if target_artist_lower in artist or artist in target_artist_lower:
                    score += 5
                elif self._extract_primary_artist(target_artist_lower) in artist:
                    score += 3
            
            # Prefer tracks with preview URLs
            if track.get('preview_url'):
                score += 1
            
            if score > best_score:
                best_score = score
                best_match = track
        
        return best_match if best_score > 0 else tracks[0]  # Fallback to first result

    def get_spotify_track_data(self, track_name: str, artist_name: str, access_token: str, excluded_track_ids: Set[str] = None) -> Dict:
        """
        Get comprehensive track data from Spotify including popularity, duration, preview URL, etc.
        
        Args:
            track_name (str): Name of the track
            artist_name (str): Name of the artist
            access_token (str): Spotify access token
            excluded_track_ids (Set[str]): Set of track IDs to exclude
            
        Returns:
            Dict: Track data including popularity, duration, preview URL, etc.
        """
        try:
            if not access_token:
                return {
                    'found': False,
                    'spotify_id': None,
                    'popularity': 50,
                    'album_cover': 'https://picsum.photos/300/300?random=1',
                    'preview_url': '',
                    'external_url': '',
                    'duration_ms': 0
                }
            
            # Search for the track on Spotify using multiple strategies
            sp = self.spotify_service.create_spotify_client(access_token)
            
            # Try multiple search strategies to handle multi-artist tracks
            search_strategies = [
                # Strategy 1: Exact match with full artist name
                f"track:\"{track_name}\" artist:\"{artist_name}\"",
                # Strategy 2: More flexible search
                f"track:\"{track_name}\" {artist_name}",
                # Strategy 3: Just track name (in case artist name is incomplete)
                f"track:\"{track_name}\"",
                # Strategy 4: Extract primary artist from multi-artist strings
                f"track:\"{track_name}\" artist:\"{self._extract_primary_artist(artist_name)}\""
            ]
            
            for search_query in search_strategies:
                try:
                    results = sp.search(q=search_query, type='track', limit=5)  # Get more results to find best match
                    
                    if results and results.get('tracks', {}).get('items'):
                        # Find the best match from the results
                        best_match = self._find_best_track_match(results['tracks']['items'], track_name, artist_name)
                        
                        if best_match:
                            track_id = best_match['id']
                            
                            # Check if this track is in the exclusion list
                            if excluded_track_ids and track_id in excluded_track_ids:
                                continue  # Try next strategy
                            
                            # Get album cover
                            album = best_match.get('album', {})
                            images = album.get('images', [])
                            cover_url = images[1]['url'] if len(images) > 1 else (images[0]['url'] if images else 'https://picsum.photos/300/300?random=1')
                            
                            # Get all artists from Spotify
                            all_artists = [artist['name'] for artist in best_match.get('artists', [])]
                            
                            return {
                                'found': True,
                                'spotify_id': track_id,
                                'popularity': best_match.get('popularity', 50),
                                'album_cover': cover_url,
                                'preview_url': best_match.get('preview_url', ''),
                                'external_url': best_match.get('external_urls', {}).get('spotify', ''),
                                'duration_ms': best_match.get('duration_ms', 0),
                                'matched_artists': all_artists,
                                'primary_artist': all_artists[0] if all_artists else artist_name,
                                'all_artists_string': ', '.join(all_artists) if all_artists else artist_name
                            }
                except Exception as e:
                    print(f"Search strategy failed for '{search_query}': {e}")
                    continue
            
            return {
                'found': False,
                'spotify_id': None,
                'popularity': 50,
                'album_cover': 'https://picsum.photos/300/300?random=1',
                'preview_url': '',
                'external_url': '',
                'duration_ms': 0
            }
            
        except Exception as e:
            print(f"Error getting Spotify track data for {track_name} by {artist_name}: {e}")
            return {
                'found': False,
                'spotify_id': None,
                'popularity': 50,
                'album_cover': 'https://picsum.photos/300/300?random=1',
                'preview_url': '',
                'external_url': '',
                'duration_ms': 0
            }

    def get_popularity_group(self, popularity: int, user_preference: int) -> str:
        """
        Determine the popularity group of a track based on its popularity score and user preference
        
        Args:
            popularity (int): Track's popularity score (0-100)
            user_preference (int): User's popularity preference (0-100)
            
        Returns:
            str: 'popular', 'balanced', or 'underground'
        """
        if popularity >= 70:
            return "popular"
        elif popularity >= 30:
            return "balanced"
        else:
            return "underground"

    def is_live_or_commentary_track(self, track_name: str) -> bool:
        """
        Check if a track is a live or commentary version that should be filtered out.
        
        Args:
            track_name (str): The track name to check
            
        Returns:
            bool: True if the track should be filtered out
        """
        track_name_lower = track_name.lower()
        return ('live' in track_name_lower or 'commentary' in track_name_lower or 
                '(live' in track_name_lower or '(commentary' in track_name_lower or
                '[live' in track_name_lower or '[commentary' in track_name_lower)

    def generate_track_id(self, track: Dict, artist_name: str) -> str:
        """
        Generate a consistent track ID for a track.
        
        Args:
            track (dict): Track data from Last.fm
            artist_name (str): Artist name
            
        Returns:
            str: Generated track ID
        """
        track_name = track.get('name', '')
        if track.get('mbid'):
            return f"lastfm_{track['mbid']}_{track_name.replace(' ', '_')}_by_{artist_name.replace(' ', '_')}"
        else:
            normalized_str = f"{track_name.lower().strip()}|{artist_name.lower().strip()}"
            return f"lastfm_{hash(normalized_str)}_{track_name.replace(' ', '_')}_by_{artist_name.replace(' ', '_')}"

    def is_track_excluded(self, track_name: str, artist_name: str, all_excluded_tracks: Set[str], excluded_tracks: List[Dict]) -> bool:
        """
        Check if a track should be excluded based on exclusion lists.
        
        Args:
            track_name (str): Track name
            artist_name (str): Artist name
            all_excluded_tracks (set): Set of excluded track IDs
            excluded_tracks (list): List of excluded track objects
            
        Returns:
            bool: True if the track should be excluded
        """
        # Generate track ID for checking
        track_id = f"lastfm_{hash(f'{track_name.lower().strip()}|{artist_name.lower().strip()}')}"
        
        # Check by track ID
        if track_id in all_excluded_tracks:
            return True
        
        # Check by name + artist matching
        track_name_lower = track_name.lower().strip()
        artist_name_lower = artist_name.lower().strip()
        
        for excluded_track in (excluded_tracks or []):
            excluded_name = excluded_track.get('name', '').lower().strip()
            excluded_artist = excluded_track.get('artist', '').lower().strip()
            if (track_name_lower == excluded_name and artist_name_lower == excluded_artist):
                return True
        
        return False

    def matches_popularity_preference(self, track_popularity: int, user_popularity_preference: int) -> bool:
        """
        Check if a track's popularity matches the user's preference.
        
        Args:
            track_popularity (int): Track's popularity score (0-100)
            user_popularity_preference (int): User's preference (0-100)
            
        Returns:
            bool: True if the track matches the user's preference
        """
        popularity_group = self.get_popularity_group(track_popularity, user_popularity_preference)
        
        # Skip tracks that don't match user's preference
        if popularity_group == "underground" and user_popularity_preference > 66:
            return False  # User wants popular music, skip underground
        elif popularity_group == "popular" and user_popularity_preference < 34:
            return False  # User wants underground music, skip popular
        
        return True
