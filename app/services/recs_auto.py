"""
Auto Discovery Recommendation Service - Using Last.fm API for automatic recommendations based on user's saved tracks
"""

import time
import random
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from .lastfm_service import LastFMService
from .recs_utils import RecommendationUtils

class AutoDiscoveryService:
    def __init__(self):
        self.lastfm_service = LastFMService()
        self.utils = RecommendationUtils()
        self.progress_messages = []
    
    def add_progress_message(self, message: str):
        """Add a progress message with timestamp"""
        self.utils.add_progress_message(message, self.progress_messages)
    
    def get_auto_discovery_recommendations(self, 
                                         analysis_tracks: List[Dict], 
                                         n_recommendations: int = 30, 
                                         excluded_track_ids: Set[str] = None, 
                                         access_token: str = None, 
                                         depth: int = 3, 
                                         popularity: int = 50, 
                                         excluded_track_data: List[Dict] = None,
                                         progress_callback: callable = None) -> Dict:
        """
        Get auto discovery recommendations based on a mix of user's saved tracks using Last.fm
        
        Args:
            analysis_tracks (List[Dict]): Filtered and randomized tracks used to build recommendations
            n_recommendations (int): Number of recommendations to generate
            excluded_track_ids (Set[str]): Set of track IDs to exclude
            access_token (str): Spotify access token
            depth (int): Analysis depth (number of top artists to use)
            popularity (int): User's popularity preference (0-100)
            excluded_track_data (List[Dict]): All saved tracks (only used if user decides to exclude them)
            progress_callback (callable): Optional progress callback function
            
        Returns:
            Dict: Recommendations with metadata
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
            print(f"top artists: {top_artists[:5]}")
            
            if n_recommendations < 20:
                selected_artists = random.sample(top_artists, 3)
            else:
                selected_artists = random.sample(top_artists, 4)

            print(f"Artists selected for recommendation seeds: {selected_artists}")
            
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
                selected_artists, all_excluded_tracks, excluded_track_data, 
                seen_artists, n_recommendations, popularity, access_token, progress_callback
            )
            
            # ============================================================================
            # STEP 6: FINALIZE & RETURN RECOMMENDATIONS
            # ============================================================================
            # Shuffle recommendations to ensure variety on each request (no predictable order)
            random.shuffle(all_recommendations)
            print(f"total recommendations before filter: {len(all_recommendations)}")
            
            # If we don't have enough recommendations, try expanding through similar artists
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
                for artist_name, _ in selected_artists:
                    used_artists.add(artist_name.lower())
                
                # Try to find similar artists of similar artists (depth expansion)
                expansion_artists = []
                for artist_name, _ in selected_artists:
                    # Get similar artists for the seed
                    similar_artists = self.lastfm_service.get_similar_artists(artist_name, limit=20)
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
                        if self.utils.is_live_or_commentary_track(track_name):
                            continue
                        
                        # Generate consistent track ID
                        track_id = self.utils.generate_track_id(track, expansion_artist)
                        
                        # Get track data from Spotify
                        spotify_data = self.utils.get_spotify_track_data(track_name, expansion_artist, access_token, all_excluded_tracks) if access_token else {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
                        
                        # Skip tracks that don't exist on Spotify
                        if not spotify_data.get('found', True):
                            continue
                        
                        # Check exclusions
                        if self.utils.is_track_excluded(track_name, expansion_artist, all_excluded_tracks, excluded_track_data):
                            continue
                        
                        # Check popularity preference
                        if not self.utils.matches_popularity_preference(spotify_data['popularity'], popularity):
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
                            'seed_track': f"{expansion_artist} (auto discovery expanded)"
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
                no_recommendations_message = "No more recommendations found for your current music taste. Please try different settings or add more music to your library!"
                print(f"INFO: {no_recommendations_message}")
            
            # Return the final recommendation results with metadata
            return {
                'recommendations': all_recommendations,
                'seed_track': {
                    'name': 'Auto Discovery',
                    'artist': 'User Library Analysis'
                },
                'generation_time': 0,
                'method': 'lastfm_auto_discovery',
                'progress_messages': self.progress_messages,
                'no_more_recommendations': len(all_recommendations) == 0
            }
            
        except Exception as e:
            return {"error": f"Last.fm auto discovery failed: {str(e)}"}

    def _process_artists_parallel(self, top_artists, all_excluded_tracks, excluded_track_data, 
                                 seen_artists, n_recommendations, popularity, access_token, progress_callback):
        """
        Process artists in parallel for faster recommendations
        
        Args:
            top_artists (list): List of (artist_name, count) tuples
            all_excluded_tracks (set): Set of excluded track IDs
            excluded_track_data (list): List of excluded track objects
            seen_artists (set): Set of artists already seen
            n_recommendations (int): Number of recommendations needed
            popularity (int): User's popularity preference
            access_token (str): Spotify access token
            progress_callback (callable): Optional progress callback
            
        Returns:
            list: List of recommendation dictionaries
        """
        all_recommendations = []
        recommendations_lock = threading.Lock()
        
        def process_artist(artist_data):
            """Process a single artist to find recommendations"""
            artist_name, artist_count = artist_data
            artist_recommendations = []
            
            print(f"🔍 Processing artist: {artist_name} (appears {artist_count} times in user's library)")
            
            try:
                # Get similar artists for this seed artist
                similar_artists = self.lastfm_service.get_similar_artists(artist_name, limit=20)
                
                if not similar_artists:
                    print(f"❌ No similar artists found for {artist_name}")
                    return artist_recommendations
                
                print(f"🎵 Found {len(similar_artists)} similar artists for {artist_name}")
                
                # Process similar artists to find recommendations
                for similar_artist in similar_artists:
                    if len(artist_recommendations) >= 8:  # Limit per seed artist
                        break
                    
                    similar_artist_name = similar_artist.get('name', '')
                    if not similar_artist_name or similar_artist_name.lower() in seen_artists:
                        continue
                    
                    # Get top tracks from this similar artist
                    all_tracks = self.lastfm_service.get_artist_top_tracks(similar_artist_name, limit=6)
                    
                    if not all_tracks:
                        continue
                    
                    # Select tracks based on popularity preference
                    if len(all_tracks) >= 4:
                        if popularity > 75:
                            top_tracks = all_tracks[0:2]  # Most popular
                        elif popularity > 35:
                            top_tracks = all_tracks[2:4]  # Balanced
                        else:
                            top_tracks = all_tracks[4:6]  # Less popular
                    else:
                        top_tracks = all_tracks[0:2]  # Get 1st and 2nd most popular tracks
                    
                    # Process these tracks
                    for track in top_tracks:
                        if len(artist_recommendations) >= 8:  # Limit per seed artist
                            break
                        
                        track_name = track.get('name', '')
                        if not track_name:
                            continue
                        
                        # Filter out Live and Commentary versions
                        if self.utils.is_live_or_commentary_track(track_name):
                            continue
                        
                        # Generate consistent track ID
                        track_id = self.utils.generate_track_id(track, similar_artist_name)
                        
                        # Get track data from Spotify
                        spotify_data = self.utils.get_spotify_track_data(track_name, similar_artist_name, access_token, all_excluded_tracks) if access_token else {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
                        
                        # Skip tracks that don't exist on Spotify
                        if not spotify_data.get('found', True):
                            continue
                        
                        # Check exclusions
                        if self.utils.is_track_excluded(track_name, similar_artist_name, all_excluded_tracks, excluded_track_data):
                            continue
                        
                        # Check popularity preference
                        if not self.utils.matches_popularity_preference(spotify_data['popularity'], popularity):
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
                            'seed_track': f"{artist_name} (auto discovery)"
                        }
                        
                        artist_recommendations.append(recommendation)
                        break  # Only take one track per artist for variety
                
                print(f"✅ Generated {len(artist_recommendations)} recommendations from {artist_name}")
                return artist_recommendations
                
            except Exception as e:
                print(f"❌ Error processing artist {artist_name}: {e}")
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
