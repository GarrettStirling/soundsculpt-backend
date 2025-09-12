"""
Last.fm-Based Recommendation Service - Using Last.fm API for musical similarity
"""

import requests
import os
import time
import random
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from .lastfm_service import LastFMService
from .spotify_service import SpotifyService
from dotenv import load_dotenv

load_dotenv()

class LastFMRecommendationService:
    def __init__(self):
        self.lastfm_service = LastFMService()
        self.spotify_service = SpotifyService()
        self.progress_messages = []
    
    def add_progress_message(self, message: str):
        """Add a progress message with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        self.progress_messages.append(f"[{timestamp}] {message}")
    
    def get_spotify_album_cover(self, track_name: str, artist_name: str, access_token: str) -> str:
        """
        Get album cover from Spotify for a track
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
            return 'https://picsum.photos/300/300?random=1'
    
    def get_spotify_track_data(self, track_name: str, artist_name: str, access_token: str, excluded_track_ids: Set[str] = None) -> Dict:
        """Get track data including popularity from Spotify search, with smart matching for exclusion"""
        try:
            if not access_token:
                return {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
            
            sp = self.spotify_service.create_spotify_client(access_token)
            
            # Try multiple search strategies to find the best match
            search_queries = [
                f"track:{track_name} artist:{artist_name}",
                f'"{track_name}" "{artist_name}"',
                f"{track_name} {artist_name}",
                f"track:{track_name} {artist_name}"
            ]
            
            best_match = None
            best_score = 0
            
            for search_query in search_queries:
                try:
                    results = sp.search(q=search_query, type='track', limit=10)  # Get more results to find best match
                    
                    if results and results.get('tracks', {}).get('items'):
                        for track in results['tracks']['items']:
                            # Calculate match score based on name and artist similarity
                            track_name_match = track_name.lower() in track.get('name', '').lower()
                            artist_match = any(artist_name.lower() in artist.get('name', '').lower() 
                                             for artist in track.get('artists', []))
                            
                            if track_name_match and artist_match:
                                # Prefer tracks that are in the user's saved tracks (for better exclusion matching)
                                track_id = track.get('id')
                                is_saved = track_id in excluded_track_ids if excluded_track_ids else False
                                
                                score = 100 if is_saved else 50  # Higher score for saved tracks
                                
                                if score > best_score:
                                    best_score = score
                                    best_match = track
                                    
                                    # Only log for specific tracks we're investigating
                                    if track_name == 'Some Feeling' and artist_name == 'Mild Orange':
                                        print(f"BEST MATCH: '{track.get('name')}' by {[artist.get('name') for artist in track.get('artists', [])]}")
                                        print(f"  Spotify ID: {track_id}, Album: '{track.get('album', {}).get('name', 'Unknown')}'")
                                        print(f"  Is saved version: {is_saved}")
                                            
                except Exception as e:
                    continue
            
            if best_match:
                track = best_match
                album = track.get('album', {})
                images = album.get('images', [])
                
                album_cover = 'https://picsum.photos/300/300?random=1'
                if images:
                    album_cover = images[1]['url'] if len(images) > 1 else images[0]['url']
                
                spotify_id = track.get('id')
                
                return {
                    'found': True,
                    'spotify_id': spotify_id,
                    'popularity': track.get('popularity', 50),
                    'album_cover': album_cover,
                    'duration_ms': track.get('duration_ms', 0),
                    'preview_url': track.get('preview_url'),
                    'external_url': track.get('external_urls', {}).get('spotify', f"https://open.spotify.com/search/{track_name}%20{artist_name}")
                }
            
            return {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
            
        except Exception as e:
            return {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
    
    def should_exclude_track_hybrid(self, track_name: str, artist_name: str, spotify_id: str, excluded_tracks: Set[str], excluded_track_data: List[Dict] = None) -> tuple:
        """
        Hybrid exclusion method: Check exact ID match first, then fallback to name+artist matching
        Returns: (should_exclude: bool, match_type: str, timing_info: dict)
        """
        try:
            import time
            start_time = time.time()
        
            # Method 1: Exact Spotify ID match (fastest)
            id_check_start = time.time()
            if spotify_id and spotify_id in excluded_tracks:
                id_check_time = time.time() - id_check_start
                total_time = time.time() - start_time
                return True, "exact_id", {"id_check_ms": round(id_check_time * 1000, 2), "total_ms": round(total_time * 1000, 2)}
            id_check_time = time.time() - id_check_start
            
            # Method 2: Name + Artist matching (if we have track data)
            if excluded_track_data:
                name_check_start = time.time()
                track_name_lower = track_name.lower().strip()
                artist_name_lower = artist_name.lower().strip()
                
                for excluded_track in excluded_track_data:
                    excluded_name = excluded_track.get('name', '').lower().strip()
                    excluded_artist = excluded_track.get('artist', '').lower().strip()
                    
                    # Exact match
                    if excluded_name == track_name_lower and excluded_artist == artist_name_lower:
                        name_check_time = time.time() - name_check_start
                        total_time = time.time() - start_time
                        return True, "exact_name_artist", {
                            "id_check_ms": round(id_check_time * 1000, 2),
                            "name_check_ms": round(name_check_time * 1000, 2),
                            "total_ms": round(total_time * 1000, 2)
                        }
                    
                    # Fuzzy match (handle common variations)
                    if (self._fuzzy_match(excluded_name, track_name_lower) and 
                        self._fuzzy_match(excluded_artist, artist_name_lower)):
                        name_check_time = time.time() - name_check_start
                        total_time = time.time() - start_time
                        return True, "fuzzy_name_artist", {
                            "id_check_ms": round(id_check_time * 1000, 2),
                            "name_check_ms": round(name_check_time * 1000, 2),
                            "total_ms": round(total_time * 1000, 2)
                        }
                
                name_check_time = time.time() - name_check_start
            else:
                name_check_time = 0
            
            total_time = time.time() - start_time
            return False, "no_match", {
                "id_check_ms": round(id_check_time * 1000, 2),
                "name_check_ms": round(name_check_time * 1000, 2),
                "total_ms": round(total_time * 1000, 2)
            }
        except Exception as e:
            print(f"ERROR in should_exclude_track_hybrid: {e}")
            import traceback
            traceback.print_exc()
            return False, "error", {"error": str(e), "total_ms": 0}
    
    def _fuzzy_match(self, str1: str, str2: str) -> bool:
        """Simple fuzzy matching for track/artist names - more strict to avoid false positives"""
        # Remove common suffixes and prefixes
        clean1 = str1.replace('(feat.', '').replace('(ft.', '').replace('featuring', '').replace('feat', '').strip()
        clean2 = str2.replace('(feat.', '').replace('(ft.', '').replace('featuring', '').replace('feat', '').strip()
        
        # Remove punctuation and extra spaces
        import re
        clean1 = re.sub(r'[^\w\s]', '', clean1).strip()
        clean2 = re.sub(r'[^\w\s]', '', clean2).strip()
        
        # Only exact match after cleaning - no partial matches to avoid false positives
        return clean1 == clean2

    def get_popularity_group(self, popularity: int, user_preference: int) -> str:
        """Determine popularity group based on user preference and track popularity"""
        # Define thresholds based on user preference
        if user_preference <= 33:  # Underground preference
            underground_threshold, balanced_threshold = 30, 60
        elif user_preference <= 66:  # Balanced preference
            underground_threshold, balanced_threshold = 40, 70
        else:  # Popular preference
            underground_threshold, balanced_threshold = 50, 80
        
        # Return group based on thresholds
        if popularity <= underground_threshold:
            return "underground"
        elif popularity <= balanced_threshold:
            return "balanced"
        else:
            return "popular"
    
    def get_multiple_seed_recommendations(self, 
                                         seed_tracks: List[Dict], 
                                         n_recommendations: int = 20, 
                                         excluded_track_ids: Set[str] = None, 
                                         user_saved_tracks: List[Dict] = None, 
                                         access_token: str = None,
                                         popularity: int = 50,
                                         depth: int = 3,
                                         progress_callback: callable = None) -> Dict:
        """
        Get recommendations based on multiple seed tracks using Last.fm similarity data
        """
        start_time = time.time()
        
        try:
            print(f"🚀 DEBUG: get_multiple_seed_recommendations called with {len(seed_tracks)} seed tracks")
            print(f"🚀 DEBUG: Requesting {n_recommendations} recommendations")
            
            # Clear previous progress messages
            self.progress_messages = []
            
            self.add_progress_message("Starting Last.fm recommendation engine...")
            if progress_callback:
                progress_callback("Starting Last.fm recommendation engine...")
            
            self.add_progress_message("Analyzing your selected seed tracks...")
            if progress_callback:
                progress_callback("Analyzing your selected seed tracks...")
            
            # Check if Last.fm service is available
            if not self.lastfm_service.api_key:
                return {"error": "Last.fm API not configured. Please set LASTFM_API_KEY and LASTFM_SHARED_SECRET environment variables."}
            
            # Process each seed track and collect recommendations
            all_recommendations = []
            seen_artists = set()
            recommended_track_ids = set()
            
            # Add all seed artists to excluded list
            for seed_track in seed_tracks:
                seen_artists.add(seed_track['artist'].lower())
            
            self.add_progress_message("Setting up recommendation filters...")
            if progress_callback:
                progress_callback("Setting up recommendation filters...")
            
            # Create a combined exclusion set for easier filtering
            excluded_ids = excluded_track_ids or set()
            all_excluded_tracks = excluded_ids
            
            # Process each seed track
            for i, seed_track in enumerate(seed_tracks):
                print(f"🔍 DEBUG: Processing seed track {i+1}/{len(seed_tracks)}: '{seed_track['name']}' by {seed_track['artist']}")
                self.add_progress_message(f"Finding music similar to '{seed_track['name']}' by {seed_track['artist']}...")
                if progress_callback:
                    progress_callback(f"Finding music similar to '{seed_track['name']}' by {seed_track['artist']}...")
                
                # Get similar tracks for this seed
                similar_tracks = self.lastfm_service.get_similar_tracks(seed_track['artist'], seed_track['name'], limit=50)
                print(f"🔍 DEBUG: Found {len(similar_tracks)} similar tracks for '{seed_track['name']}' by {seed_track['artist']}")
                
                if not similar_tracks:
                    print(f"❌ DEBUG: No similar tracks found for '{seed_track['name']}' by {seed_track['artist']}")
                    print(f"🔄 DEBUG: Trying similar artists as fallback for '{seed_track['name']}' by {seed_track['artist']}")
                    
                    # Fallback: try to get similar artists and their top tracks
                    similar_artists = self.lastfm_service.get_similar_artists(seed_track['artist'], limit=30)
                    print(f"🔍 DEBUG: Found {len(similar_artists)} similar artists as fallback")
                    
                    if not similar_artists:
                        print(f"❌ DEBUG: No similar artists found either for '{seed_track['artist']}'")
                        print(f"⚠️ No similar tracks or artists found for seed {i+1}: '{seed_track['name']}' by {seed_track['artist']}")
                        continue
                    
                    # Process similar artists instead of similar tracks
                    for similar_artist in similar_artists:
                        if len(all_recommendations) >= n_recommendations:
                            break
                        
                        similar_artist_name = similar_artist.get('name', '')
                        if not similar_artist_name or similar_artist_name.lower() in seen_artists:
                            continue
                        print(f"🔍 DEBUG: Fallback - {similar_artist_name}")
                        
                        # Get top tracks from this similar artist
                        all_tracks = self.lastfm_service.get_artist_top_tracks(similar_artist_name, limit=4)
                        
                        if len(all_tracks) >= 4:
                            top_tracks = all_tracks[2:4]  # Get 3rd and 4th most popular tracks
                        else:
                            top_tracks = all_tracks[0:2]  # Get 1st and 2nd most popular tracks
                        
                        # Process these tracks (same logic as below)
                        for track in top_tracks:
                            if len(all_recommendations) >= n_recommendations:
                                break
                            
                            track_name = track.get('name', '')
                            if not track_name:
                                continue
                            
                            # Filter out Live and Commentary versions
                            track_name_lower = track_name.lower()
                            if ('live' in track_name_lower or 'commentary' in track_name_lower or 
                                '(live' in track_name_lower or '(commentary' in track_name_lower or
                                '[live' in track_name_lower or '[commentary' in track_name_lower):
                                continue
                            
                            # Generate consistent track ID
                            if track.get('mbid'):
                                track_id = f"lastfm_{track.get('mbid')}"
                            else:
                                normalized_str = f"{track_name.lower().strip()}|{similar_artist_name.lower().strip()}"
                                track_id = f"lastfm_{hash(normalized_str)}"
                            
                            # Get track data from Spotify first to get the actual Spotify track ID
                            spotify_data = self.get_spotify_track_data(track_name, similar_artist_name, access_token, all_excluded_tracks) if access_token else {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
                            
                            # Skip tracks that don't exist on Spotify
                            if not spotify_data.get('found', True):
                                continue
                            
                            # Get the actual Spotify track ID for exclusion checking
                            spotify_track_id = spotify_data.get('spotify_id')
                            if not spotify_track_id:
                                # Fallback: try to extract from external_url
                                external_url = spotify_data.get('external_url', '')
                                if '/track/' in external_url:
                                    spotify_track_id = external_url.split('/track/')[-1].split('?')[0]
                            
                            # Simple exact name + artist matching for exclusion
                            track_name_lower = track_name.lower().strip()
                            artist_name_lower = similar_artist_name.lower().strip()
                            
                            # Check if this track is in the exclusion list by name + artist
                            is_excluded = False
                            for excluded_track in excluded_track_data:
                                excluded_name = excluded_track.get('name', '').lower().strip()
                                excluded_artist = excluded_track.get('artist', '').lower().strip()
                                
                                if excluded_name == track_name_lower and excluded_artist == artist_name_lower:
                                    print(f"EXCLUDED {track_name} by {similar_artist_name} - exact name+artist match")
                                    is_excluded = True
                                    break
                            
                            if is_excluded:
                                continue
                            
                            # Check popularity preference
                            popularity_group = self.get_popularity_group(spotify_data['popularity'], popularity)
                            if popularity_group == "underground" and popularity > 66:
                                continue
                            elif popularity_group == "popular" and popularity < 34:
                                continue
                            
                            # Create recommendation
                            recommendation = {
                                'id': track_id,
                                'name': track_name,
                                'artist': similar_artist_name,
                                'album': 'Unknown Album',
                                'duration_ms': spotify_data.get('duration_ms', 0),
                                'popularity': spotify_data['popularity'],
                                'preview_url': spotify_data.get('preview_url'),
                                'external_url': spotify_data.get('external_url', f"https://open.spotify.com/search/{track_name}%20{similar_artist_name}"),
                                'album_cover': spotify_data['album_cover'],
                                'seed_track': f"{seed_track['name']} by {seed_track['artist']} (fallback)"
                            }
                            
                            all_recommendations.append(recommendation)
                            seen_artists.add(similar_artist_name.lower())
                            break  # Only take one track per artist for variety
                    
                    continue  # Skip the normal similar tracks processing
                
                print(f"🎵 Processing seed {i+1}: '{seed_track['name']}' by {seed_track['artist']} - found {len(similar_tracks)} similar tracks")
                
                # Process similar tracks (collect from all seeds first, then limit later)
                for track in similar_tracks:
                    track_name = track.get('name', '')
                    artist_name = track.get('artist', {}).get('name', '') if isinstance(track.get('artist'), dict) else str(track.get('artist', ''))
                    
                    if not track_name or not artist_name:
                        continue
                    
                    # Filter out Live and Commentary versions
                    track_name_lower = track_name.lower()
                    if ('live' in track_name_lower or 'commentary' in track_name_lower or 
                        '(live' in track_name_lower or '(commentary' in track_name_lower or
                        '[live' in track_name_lower or '[commentary' in track_name_lower):
                        continue
                    
                    # Generate track ID
                    if track.get('mbid'):
                        track_id = f"lastfm_{track['mbid']}_{track_name.replace(' ', '_')}_by_{artist_name.replace(' ', '_')}"
                    else:
                        normalized_str = f"{track_name.lower().strip()}|{artist_name.lower().strip()}"
                        track_id = f"lastfm_{hash(normalized_str)}_{track_name.replace(' ', '_')}_by_{artist_name.replace(' ', '_')}"
                    
                    # Skip if already recommended, excluded, or from seen artists
                    if (artist_name.lower() in seen_artists or 
                        track_id in all_excluded_tracks or
                        track_id in recommended_track_ids):
                        continue
                    
                    # Use actual similarity score from Last.fm
                    similarity_score = float(track.get('match', 0)) if track.get('match') else 0.8
                    
                    # Get track data from Spotify (including popularity)
                    spotify_data = self.get_spotify_track_data(track_name, artist_name, access_token, all_excluded_tracks) if access_token else {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
                    
                    # Skip tracks that don't exist on Spotify
                    if not spotify_data.get('found', True):
                        continue
                    
                    # Get the actual Spotify track ID for exclusion checking
                    spotify_track_id = spotify_data.get('spotify_id')
                    if not spotify_track_id:
                        # Fallback: try to extract from external_url
                        external_url = spotify_data.get('external_url', '')
                        if '/track/' in external_url:
                            spotify_track_id = external_url.split('/track/')[-1].split('?')[0]
                    
                    # Skip if already excluded (check both Last.fm ID and Spotify ID)
                    if track_id in all_excluded_tracks or (spotify_track_id and spotify_track_id in all_excluded_tracks):
                        continue
                    
                    # Check if track matches user's popularity preference
                    popularity_group = self.get_popularity_group(spotify_data['popularity'], popularity)
                    
                    # Skip tracks that don't match user's preference
                    if popularity_group == "underground" and popularity > 66:
                        continue  # User wants popular music, skip underground
                    elif popularity_group == "popular" and popularity < 34:
                        continue  # User wants underground music, skip popular
                    
                    # Add to recommendations
                    recommendation = {
                        'id': track_id,
                        'name': track_name,
                        'artist': artist_name,
                        'album_cover': spotify_data['album_cover'],
                        'preview_url': spotify_data.get('preview_url', ''),
                        'external_url': spotify_data.get('external_url', ''),
                        'duration_ms': spotify_data.get('duration_ms', 0),
                        'popularity': spotify_data['popularity'],
                        'similarity_score': similarity_score,
                        'source': 'lastfm_similar',
                        'seed_track': f"{seed_track['name']} by {seed_track['artist']}"
                    }
                    
                    all_recommendations.append(recommendation)
                    recommended_track_ids.add(track_id)
                    seen_artists.add(artist_name.lower())
            
            print(f"📊 Collected {len(all_recommendations)} total recommendations from {len(seed_tracks)} seed tracks")
            
            # Show breakdown by seed track
            seed_counts = {}
            for rec in all_recommendations:
                seed = rec.get('seed_track', 'Unknown')
                seed_counts[seed] = seed_counts.get(seed, 0) + 1
            
            for seed, count in seed_counts.items():
                print(f"   🎵 {seed}: {count} recommendations")

            # Shuffle and limit results to mix recommendations from different seed tracks
            random.shuffle(all_recommendations)
            all_recommendations = all_recommendations[:n_recommendations]
            
            print(f"🎲 After shuffling and limiting to {n_recommendations}: {len(all_recommendations)} final recommendations")
            
            # Show final breakdown
            final_seed_counts = {}
            for rec in all_recommendations:
                seed = rec.get('seed_track', 'Unknown')
                final_seed_counts[seed] = final_seed_counts.get(seed, 0) + 1
            
            for seed, count in final_seed_counts.items():
                print(f"   🎯 {seed}: {count} final recommendations")

            elapsed_time = time.time() - start_time
            
            self.add_progress_message(f"Found {len(all_recommendations)} perfect recommendations for you!")
            if progress_callback:
                progress_callback(f"Found {len(all_recommendations)} perfect recommendations for you!")
            
            return {
                'recommendations': all_recommendations,
                'progress_messages': self.progress_messages,
                'total_recommendations': len(all_recommendations),
                'processing_time': elapsed_time
            }
            
        except Exception as e:
            print(f"Error in multi-seed Last.fm recommendation service: {e}")
            return {"error": f"Failed to generate multi-seed Last.fm recommendations: {str(e)}"}
    
    def _get_artist_based_recommendations(self, seed_artist_name: str, n_recommendations: int, excluded_track_ids: Set[str]) -> Dict:
        """
        Fallback method: get recommendations based on similar artists only
        """
        try:
            print(f"Using artist-based fallback for {seed_artist_name}")
            
            # Check if Last.fm service is available
            if not self.lastfm_service.api_key:
                return {"error": "Last.fm API not configured. Please set LASTFM_API_KEY and LASTFM_SHARED_SECRET environment variables."}
            
            similar_artists = self.lastfm_service.get_similar_artists(seed_artist_name, limit=20)
            if not similar_artists:
                return {"error": f"No similar artists found for '{seed_artist_name}'"}
            
            all_recommendations = []
            seen_artists = set([seed_artist_name.lower()])
            
            for artist in similar_artists:
                if len(all_recommendations) >= n_recommendations:
                    break
                
                artist_name = artist.get('name', '')
                if not artist_name or artist_name.lower() in seen_artists:
                    continue
                
                # Get top tracks from this similar artist
                top_tracks = self.lastfm_service.get_artist_top_tracks(artist_name, limit=3)
                
                for track in top_tracks:
                    if len(all_recommendations) >= n_recommendations:
                        break
                    
                    track_name = track.get('name', '')
                    if not track_name:
                        continue
                    
                    # Check if track exists on Spotify before creating recommendation
                    spotify_data = self.get_spotify_track_data(track_name, artist_name, access_token, all_excluded_tracks) if access_token else {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
                    
                    # Skip tracks that don't exist on Spotify
                    if not spotify_data.get('found', True):
                        continue
                    
                    # Get the actual Spotify track ID for exclusion checking
                    spotify_track_id = spotify_data.get('spotify_id')
                    if not spotify_track_id:
                        # Fallback: try to extract from external_url
                        external_url = spotify_data.get('external_url', '')
                        if '/track/' in external_url:
                            spotify_track_id = external_url.split('/track/')[-1].split('?')[0]
                    
                    # Skip if already excluded (check Spotify ID)
                    if spotify_track_id and spotify_track_id in all_excluded_tracks:
                        continue
                    
                    recommendation = {
                        'id': f"lastfm_{track.get('mbid', '')}" if track.get('mbid') else f"lastfm_{hash(track_name + artist_name)}",
                        'name': track_name,
                        'artist': artist_name,
                        'album': 'Unknown Album',
                        'duration_ms': spotify_data.get('duration_ms', 0),
                        'popularity': spotify_data['popularity'],
                        'preview_url': spotify_data.get('preview_url'),
                        'external_url': spotify_data.get('external_url', f"https://open.spotify.com/search/{track_name}%20{artist_name}"),
                        'images': [{'url': spotify_data['album_cover']}],
                        'similarity_score': float(artist.get('match', 0)) if artist.get('match') else 0.6,
                        'source': 'lastfm_artist_fallback'
                    }
                    
                    all_recommendations.append(recommendation)
                    seen_artists.add(artist_name.lower())
                    break  # Only take one track per artist
            
            return {
                'recommendations': all_recommendations,
                'seed_track': {
                    'name': 'Unknown',
                    'artist': seed_artist_name
                },
                'generation_time': 0,
                'method': 'lastfm_artist_similarity'
            }
            
        except Exception as e:
            print(f"Error in artist-based fallback: {e}")
            return {"error": f"Artist-based fallback failed: {str(e)}"}
    
    def _process_artists_parallel(self, top_artists, all_excluded_tracks, excluded_track_data, 
                                 seen_artists, n_recommendations, popularity, access_token, progress_callback):
        """Process artists in parallel for faster recommendations"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        all_recommendations = []
        recommendations_lock = threading.Lock()
        seen_artists_lock = threading.Lock()
        
        def process_artist(artist_data):
            """Process a single artist and return recommendations"""
            artist_name, count = artist_data
            artist_recommendations = []
            
            try:
                # Send progress update
                if progress_callback:
                    progress_callback(f"Discovering music similar to {artist_name}...")
                
                # Find similar artists
                similar_artists = self.lastfm_service.get_similar_artists(artist_name, limit=10)
                print(f"🔍 DEBUG: Similar artists for {artist_name}: {[artist.get('name', 'Unknown') for artist in similar_artists[:5]]}")
                
                # Process each similar artist
                for similar_artist in similar_artists:
                    similar_artist_name = similar_artist.get('name', '')
                    if not similar_artist_name:
                        continue
                    
                    # Check if we've already seen this artist (thread-safe)
                    with seen_artists_lock:
                        if similar_artist_name.lower() in seen_artists:
                            continue
                        seen_artists.add(similar_artist_name.lower())
                    
                    # Get tracks from this similar artist
                    all_tracks = self.lastfm_service.get_artist_top_tracks(similar_artist_name, limit=4)
                    
                    # Select tracks based on popularity preference
                    if len(all_tracks) >= 6:
                        if popularity > 75: # popular
                            top_tracks = all_tracks[0:2] 
                        elif popularity > 35: # balanced
                            top_tracks = all_tracks[2:4]
                        else: # underground
                            top_tracks = all_tracks[4:6]
                    else:
                        top_tracks = all_tracks[0:2]
                    
                    # Process each track
                    for track in top_tracks:
                        track_name = track.get('name', '')
                        if not track_name:
                            continue
                        
                        # Filter out Live and Commentary versions
                        track_name_lower = track_name.lower()
                        if ('live' in track_name_lower or 'commentary' in track_name_lower or 
                            '(live' in track_name_lower or '(commentary' in track_name_lower or
                            '[live' in track_name_lower or '[commentary' in track_name_lower):
                            continue
                        
                        # Generate track ID
                        if track.get('mbid'):
                            track_id = f"lastfm_{track.get('mbid')}"
                        else:
                            normalized_str = f"{track_name.lower().strip()}|{similar_artist_name.lower().strip()}"
                            track_id = f"lastfm_{hash(normalized_str)}"
                        
                        # Get Spotify data
                        spotify_data = self.get_spotify_track_data(track_name, similar_artist_name, access_token, all_excluded_tracks) if access_token else {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
                        
                        # Skip tracks not found on Spotify
                        if not spotify_data.get('found', True):
                            continue
                        
                        # Get Spotify track ID for exclusion
                        spotify_track_id = spotify_data.get('spotify_id')
                        if not spotify_track_id:
                            external_url = spotify_data.get('external_url', '')
                            if '/track/' in external_url:
                                spotify_track_id = external_url.split('/track/')[-1].split('?')[0]
                        
                        # Simple exact name + artist matching for exclusion
                        track_name_lower = track_name.lower().strip()
                        artist_name_lower = similar_artist_name.lower().strip()
                        
                        # Check if this track is in the exclusion list by name + artist
                        is_excluded = False
                        for excluded_track in excluded_track_data:
                            excluded_name = excluded_track.get('name', '').lower().strip()
                            excluded_artist = excluded_track.get('artist', '').lower().strip()
                            
                            if excluded_name == track_name_lower and excluded_artist == artist_name_lower:
                                print(f"EXCLUDED {track_name} by {similar_artist_name} - exact name+artist match")
                                is_excluded = True
                                break
                        
                        if is_excluded:
                            continue
                        
                        # Check popularity preference
                        popularity_group = self.get_popularity_group(spotify_data['popularity'], popularity)
                        if popularity_group == "underground" and popularity > 66:
                            continue
                        elif popularity_group == "popular" and popularity < 34:
                            continue
                        
                        # Create recommendation
                        recommendation = {
                            'id': track_id,
                            'name': track_name,
                            'artist': similar_artist_name,
                            'album': 'Unknown Album',
                            'duration_ms': spotify_data.get('duration_ms', 0),
                            'popularity': spotify_data['popularity'],
                            'preview_url': spotify_data.get('preview_url'),
                            'external_url': spotify_data.get('external_url', f"https://open.spotify.com/search/{track_name}%20{similar_artist_name}"),
                            'album_cover': spotify_data['album_cover'],
                        }
                        
                        artist_recommendations.append(recommendation)
                        break  # Only take one track per artist
                        
            except Exception as e:
                print(f"Error processing artist {artist_name}: {e}")
            
            return artist_recommendations
        
        # Process artists in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all artist processing tasks
            future_to_artist = {executor.submit(process_artist, artist_data): artist_data for artist_data in top_artists}
            
            # Collect results as they complete
            for future in as_completed(future_to_artist):
                try:
                    artist_recommendations = future.result()
                    with recommendations_lock:
                        all_recommendations.extend(artist_recommendations)
                except Exception as e:
                    artist_name = future_to_artist[future][0]
                    print(f"Error processing artist {artist_name}: {e}")
        
        return all_recommendations

    def get_auto_discovery_recommendations(self, 
                                           analysis_tracks: List[Dict], # these are the filtered and randomized tracks used to build recommendations
                                           n_recommendations: int = 30, 
                                           excluded_track_ids: Set[str] = None, 
                                           access_token: str = None, 
                                           depth: int = 3, 
                                           popularity: int = 50, 
                                           excluded_track_data: List[Dict] = None, # these are all the saved tracks (only used if user decides to exclude them)
                                           progress_callback: callable = None) -> Dict:
        """
        Get auto discovery recommendations based on a mix of user's saved tracks using Last.fm
        """
        try:
            # ============================================================================
            # STEP 1: INITIALIZATION & VALIDATION
            # ============================================================================
            # Clear previous progress messages and validate Last.fm API availability
            self.progress_messages = []
            
            if not self.lastfm_service.api_key:
                return {"error": "Last.fm API not configured. Please set LASTFM_API_KEY and LASTFM_SHARED_SECRET environment variables."}
            
            # ============================================================================
            # STEP 2: COUNT ARTISTS IN USER'S SAVED TRACKS
            # ============================================================================
            # Count how often each artist appears in the user's saved tracks (filtered by depth slider)
            # This identifies which artists the user listens to most frequently
            artist_counts = {}
            
            for track in analysis_tracks:  # Analyze the filtered tracks provided (based on depth slider)
                artist_name = track.get('artists', [{}])[0].get('name', '') if track.get('artists') else ''
                if artist_name:
                    artist_counts[artist_name] = artist_counts.get(artist_name, 0) + 1
            
            if not artist_counts:
                return {"error": "Could not analyze user's artist preferences"}
            
            # ============================================================================
            # STEP 3: SELECT TOP ARTISTS FOR RECOMMENDATION SEEDS
            # ============================================================================
            # Get the user's most-played artists (based on depth slider setting)
            # These will be our "seed artists" to find similar music
            top_artists = sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:depth]
            if n_recommendations < 20:
                top_artists = top_artists[:3]
            else:
                top_artists = top_artists[:5]

            print(f"top artists: {top_artists[:5]}")
            
            # ============================================================================
            # STEP 4: SETUP FILTERING & EXCLUSION LISTS
            # ============================================================================
            # Prepare lists to avoid recommending tracks the user already has
            all_recommendations = []
            seen_artists = set(artist_counts.keys())  # Exclude user's current artists
            excluded_ids = excluded_track_ids or set() # if the user decided to exclude tracks
            
            # Get user's saved track IDs for filtering
            user_track_ids = set()
            for track in analysis_tracks:
                if track.get('id'):
                    user_track_ids.add(track['id'])
            
            # Add user's saved tracks to the exclusion list (if the user decided to exclude them)
            if excluded_track_data:
                print(f"DEBUG: Adding {len(excluded_track_data)} saved tracks to exclusion set")
                # Extract track IDs from the track data
                saved_track_ids = {track.get('id') for track in excluded_track_data if track.get('id')}
                user_track_ids.update(saved_track_ids)
                print(f"DEBUG: user_track_ids now has {len(user_track_ids)} tracks")
            else:
                print(f"DEBUG: excluded_track_data is None or empty, not adding to exclusion")
            
            # Create a combined exclusion set for easier filtering
            all_excluded_tracks = excluded_ids.union(user_track_ids)
            print(f"DEBUG: Final exclusion set has {len(all_excluded_tracks)} tracks")
            print(f"DEBUG: First 5 excluded track IDs: {list(all_excluded_tracks)[:5]}")
            
            # ============================================================================
            # STEP 5: MAIN RECOMMENDATION GENERATION LOOP (PARALLELIZED)
            # ============================================================================
            # Process artists in parallel for faster recommendations
            print(f"DEBUG: Starting recommendation generation with {len(all_excluded_tracks)} excluded tracks")
            
            # Use parallel processing for artist recommendations
            all_recommendations = self._process_artists_parallel(
                top_artists, all_excluded_tracks, excluded_track_data, 
                seen_artists, n_recommendations, popularity, access_token, progress_callback
            )
            
            # ============================================================================
            # STEP 6: FINALIZE & RETURN RECOMMENDATIONS
            # ============================================================================
            # Shuffle recommendations to ensure variety on each request (no predictable order)
            random.shuffle(all_recommendations)
            print(f"total recommendations before filter: {len(all_recommendations)}")
            
            # If we don't have enough recommendations, try expanding through similar artists of similar artists
            if len(all_recommendations) < n_recommendations:
                print(f"🔄 DEBUG: Only found {len(all_recommendations)} recommendations, expanding search depth...")
                self.add_progress_message("Expanding search to find more recommendations...")
                if progress_callback:
                    progress_callback("Expanding search to find more recommendations...")
                
                # Get all artists we've already used
                used_artists = set()
                for rec in all_recommendations:
                    used_artists.add(rec['artist'].lower())
                
                # Add seed artists to used list
                for seed_track in seed_tracks:
                    used_artists.add(seed_track['artist'].lower())
                
                # Try to find similar artists of similar artists (depth expansion)
                expansion_artists = []
                for seed_track in seed_tracks:
                    # Get similar artists for the seed
                    similar_artists = self.lastfm_service.get_similar_artists(seed_track['artist'], limit=20)
                    for similar_artist in similar_artists:
                        similar_artist_name = similar_artist.get('name', '')
                        if similar_artist_name and similar_artist_name.lower() not in used_artists:
                            # Get similar artists of this similar artist (depth 2)
                            depth2_artists = self.lastfm_service.get_similar_artists(similar_artist_name, limit=10)
                            for depth2_artist in depth2_artists:
                                depth2_name = depth2_artist.get('name', '')
                                if depth2_name and depth2_name.lower() not in used_artists:
                                    expansion_artists.append(depth2_name)
                                    used_artists.add(depth2_name.lower())
                
                print(f"🔍 DEBUG: Found {len(expansion_artists)} expansion artists")
                
                # Process expansion artists
                for expansion_artist in expansion_artists:
                    if len(all_recommendations) >= n_recommendations:
                        break
                    
                    print(f"🔍 DEBUG: Processing expansion artist: {expansion_artist}")
                    
                    # Get top tracks from this expansion artist
                    all_tracks = self.lastfm_service.get_artist_top_tracks(expansion_artist, limit=4)
                    
                    if len(all_tracks) >= 4:
                        top_tracks = all_tracks[2:4]  # Get 3rd and 4th most popular tracks
                    else:
                        top_tracks = all_tracks[0:2]  # Get 1st and 2nd most popular tracks
                    
                    # Process these tracks
                    for track in top_tracks:
                        if len(all_recommendations) >= n_recommendations:
                            break
                        
                        track_name = track.get('name', '')
                        if not track_name:
                            continue
                        
                        # Filter out Live and Commentary versions
                        track_name_lower = track_name.lower()
                        if ('live' in track_name_lower or 'commentary' in track_name_lower or 
                            '(live' in track_name_lower or '(commentary' in track_name_lower or
                            '[live' in track_name_lower or '[commentary' in track_name_lower):
                            continue
                        
                        # Generate consistent track ID
                        if track.get('mbid'):
                            track_id = f"lastfm_{track.get('mbid')}"
                        else:
                            normalized_str = f"{track_name.lower().strip()}|{expansion_artist.lower().strip()}"
                            track_id = f"lastfm_{hash(normalized_str)}"
                        
                        # Get track data from Spotify
                        spotify_data = self.get_spotify_track_data(track_name, expansion_artist, access_token, all_excluded_tracks) if access_token else {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
                        
                        # Skip tracks that don't exist on Spotify
                        if not spotify_data.get('found', True):
                            continue
                        
                        # Get the actual Spotify track ID for exclusion checking
                        spotify_track_id = spotify_data.get('spotify_id')
                        if not spotify_track_id:
                            # Fallback: try to extract from external_url
                            external_url = spotify_data.get('external_url', '')
                            if '/track/' in external_url:
                                spotify_track_id = external_url.split('/track/')[-1].split('?')[0]
                        
                        # Simple exact name + artist matching for exclusion
                        track_name_lower = track_name.lower().strip()
                        artist_name_lower = expansion_artist.lower().strip()
                        
                        # Check if this track is in the exclusion list by name + artist
                        is_excluded = False
                        for excluded_track in excluded_track_data:
                            excluded_name = excluded_track.get('name', '').lower().strip()
                            excluded_artist = excluded_track.get('artist', '').lower().strip()
                            
                            if excluded_name == track_name_lower and excluded_artist == artist_name_lower:
                                print(f"EXCLUDED {track_name} by {expansion_artist} - exact name+artist match")
                                is_excluded = True
                                break
                        
                        if is_excluded:
                            continue
                        
                        # Check popularity preference
                        popularity_group = self.get_popularity_group(spotify_data['popularity'], popularity)
                        if popularity_group == "underground" and popularity > 66:
                            continue
                        elif popularity_group == "popular" and popularity < 34:
                            continue
                        
                        # Create recommendation
                        recommendation = {
                            'id': track_id,
                            'name': track_name,
                            'artist': expansion_artist,
                            'album': 'Unknown Album',
                            'duration_ms': spotify_data.get('duration_ms', 0),
                            'popularity': spotify_data['popularity'],
                            'preview_url': spotify_data.get('preview_url'),
                            'external_url': spotify_data.get('external_url', f"https://open.spotify.com/search/{track_name}%20{expansion_artist}"),
                            'album_cover': spotify_data['album_cover'],
                            'seed_track': f"{seed_track['name']} by {seed_track['artist']} (expanded)"
                        }
                        
                        all_recommendations.append(recommendation)
                        break  # Only take one track per artist
            
            # Limit to requested number of recommendations
            all_recommendations = all_recommendations[:n_recommendations]
            print(f"total recommendations after filter: {len(all_recommendations)}")
            
            # Final shuffle to ensure proper mixing of all recommendation sources
            random.shuffle(all_recommendations)
            print(f"🎲 Final shuffle completed: {len(all_recommendations)} recommendations ready")
            
            # Add message if we still don't have enough recommendations
            if len(all_recommendations) < n_recommendations:
                exhaustion_message = f"⚠️ Found {len(all_recommendations)} recommendations (requested {n_recommendations}). Try adding more seed tracks or artists for better results."
                self.add_progress_message(exhaustion_message)
                print(f"⚠️ {exhaustion_message}")
            
            # Check if we have zero recommendations and add special message
            if len(all_recommendations) == 0:
                no_recommendations_message = "No more recommendations found for your current seed music. Please enter new music for new recommendations!"
                print(f"INFO: {no_recommendations_message}")
            
            # Return the final recommendation results with metadata
            return {
                'recommendations': all_recommendations,
                'seed_track': {
                    'name': 'Manual Discovery',
                    'artist': 'User Selected'
                },
                'generation_time': 0,
                'method': 'lastfm_manual_discovery',
                'progress_messages': self.progress_messages,
                'no_more_recommendations': len(all_recommendations) == 0
            }
            
        except Exception as e:
            return {"error": f"Last.fm manual discovery failed: {str(e)}"}
