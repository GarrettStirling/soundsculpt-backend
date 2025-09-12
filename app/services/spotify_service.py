import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
import os
from typing import List, Dict, Optional
import pandas as pd
from dotenv import load_dotenv

load_dotenv()  # This will load variables from .env if not already loaded

class SpotifyService:
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

        print("SpotifyService initialized with client ID:", self.client_id)

        # Define the scope of permissions we need (expanded for recommendations and playlists)
        self.scope = (
            "user-read-recently-played user-library-read user-library-modify "
            "playlist-read-private user-top-read playlist-read-collaborative "
            "user-read-email playlist-modify-public playlist-modify-private"
        )
        
        # Initialize Spotify OAuth
        self.sp_oauth = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope
        )
    
    def get_auth_url(self) -> str:
        """Get the authorization URL for Spotify login"""
        return self.sp_oauth.get_authorize_url(state="state")
    
    def get_access_token(self, code: str) -> Optional[Dict]:
        """Exchange authorization code for access token"""
        try:
            token_info = self.sp_oauth.get_access_token(code)
            return token_info
        except Exception as e:
            print(f"TOKEN ERROR: {e}")
            return None
    
    def create_spotify_client(self, access_token: str) -> spotipy.Spotify:
        """Create authenticated Spotify client"""
        return spotipy.Spotify(auth=access_token)
    
    def is_token_expired(self, sp_client: spotipy.Spotify) -> bool:
        """Check if the Spotify access token has expired"""
        try:
            # Try a simple API call to test the token
            sp_client.current_user()
            return False
        except Exception as e:
            if "401" in str(e) or "expired" in str(e).lower():
                return True
            return False
    
    # def get_user_saved_tracks_optimized(self, sp_client, max_tracks: int = None, exclude_tracks: bool = False) -> tuple:
    #     """
    #     Optimized method to fetch user's saved tracks for both analysis and exclusion.
        
    #     Args:
    #         sp_client: Authenticated Spotify client
    #         max_tracks: Maximum number of tracks to fetch for analysis (None for all)
    #         exclude_tracks: Whether to collect ALL track IDs for exclusion
            
    #     Returns:
    #         tuple: (analysis_tracks, excluded_track_ids, excluded_track_data)
    #     """
    #     import time
        
        
    #     # Check cache first (cache key based on parameters)
    #     cache_key = f"saved_tracks_{max_tracks}_{exclude_tracks}"
    #     current_time = time.time()
        
    #     if hasattr(self, '_cached_saved_tracks') and hasattr(self, '_cached_timestamp'):
    #         if cache_key in self._cached_saved_tracks and (current_time - self._cached_timestamp.get(cache_key, 0)) < 300:  # Cache for 5 minutes
    #             print(f"DEBUG: Using cached saved tracks for {cache_key}")
    #             return self._cached_saved_tracks[cache_key]
        
    #     print(f"DEBUG: Fetching fresh saved tracks for {cache_key}")
        
    #     analysis_tracks = []
    #     excluded_track_ids = set()
    #     excluded_track_data = []  # Full track data for name/artist matching
    #     seen_track_ids = set()
        
    #     limit = 50  # Spotify API maximum
    #     offset = 0
        
    #     while True:
    #         try:
    #             saved_tracks = sp_client.current_user_saved_tracks(limit=limit, offset=offset)
    #             if not saved_tracks or not saved_tracks.get('items'):
    #                 print(f"DEBUG: No more saved tracks at offset {offset}, breaking loop")
    #                 break
                
    #             for item in saved_tracks['items']:
    #                 track = item['track']
    #                 if not track or not track.get('id'):
    #                     continue
                    
    #                 track_id = track['id']
                    
    #                 # Add to exclusion set if needed (ALWAYS add ALL tracks when exclude_tracks=True)
    #                 if exclude_tracks:
    #                     excluded_track_ids.add(track_id)
    #                     # Also store full track data for name/artist matching
    #                     excluded_track_data.append({
    #                         'id': track_id,
    #                         'name': track['name'],
    #                         'artist': ', '.join([artist['name'] for artist in track.get('artists', [])])
    #                     })
                    
    #                 # Add to analysis tracks if we haven't reached the limit
    #                 # This is independent of the exclusion logic
    #                 if max_tracks is None or len(analysis_tracks) < max_tracks:
    #                     if track_id not in seen_track_ids:
    #                         seen_track_ids.add(track_id)
    #                         analysis_tracks.append({
    #                             'id': track_id,
    #                             'name': track['name'],
    #                             'artists': [{'name': artist['name']} for artist in track.get('artists', [])],
    #                             'added_at': item.get('added_at')
    #                         })
                
    #             offset += limit
                
    #             # Safety limits - but only stop if we have enough analysis tracks AND we're not excluding
    #             # If we're excluding tracks, we need to fetch ALL tracks regardless of analysis limit
    #             if max_tracks and len(analysis_tracks) >= max_tracks and not exclude_tracks:
    #                 print(f"DEBUG: Reached analysis limit {max_tracks}, breaking (exclude_tracks={exclude_tracks})")
    #                 break
    #             if offset > 10000:  # Max 10,000 tracks
    #                 print(f"DEBUG: Reached safety limit of 10,000 tracks, breaking")
    #                 break
                    
    #         except Exception as e:
    #             print(f"Error fetching saved tracks at offset {offset}: {e}")
    #             break
        
    #     print(f"FINAL: analysis_tracks: {len(analysis_tracks)}, excluded_track_ids: {len(excluded_track_ids)}")
        
    #     # Cache the results
    #     if not hasattr(self, '_cached_saved_tracks'):
    #         self._cached_saved_tracks = {}
    #     if not hasattr(self, '_cached_timestamp'):
    #         self._cached_timestamp = {}
            
    #     result = (analysis_tracks, excluded_track_ids, excluded_track_data)
    #     self._cached_saved_tracks[cache_key] = result
    #     self._cached_timestamp[cache_key] = current_time
        
    #     print(f"Cached saved tracks for {cache_key}")
        
    #     return result
    
    def get_user_saved_tracks_parallel(self, 
                                       sp_client, 
                                       max_tracks: int = None, 
                                       exclude_tracks: bool = False) -> tuple:
        """
        Parallel version of get_user_saved_tracks_optimized for faster fetching.
        Uses concurrent requests to reduce fetch time from ~84s to ~10-15s.
        
        Args:
            sp_client: Authenticated Spotify client
            max_tracks: Maximum number of tracks to fetch for analysis (None for all)
            exclude_tracks: Whether to collect ALL track IDs for exclusion
            
        Returns:
            tuple: (analysis_tracks, excluded_track_ids, excluded_track_data)
        """
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Initialize variables
        analysis_tracks = None
        excluded_ids = set()
        excluded_track_data = []
        
        # Check cache first - separate caches for analysis and exclusion tracks
        current_time = time.time()
        
        # Cache key for analysis tracks (always cached)
        analysis_cache_key = "analysis_tracks"
        # Cache key for exclusion tracks (only when exclude_tracks=True)
        exclusion_cache_key = "exclusion_tracks"
        
        if hasattr(self, '_cached_saved_tracks') and hasattr(self, '_cached_timestamp'):
            # Check analysis tracks cache
            if analysis_cache_key in self._cached_saved_tracks and (current_time - self._cached_timestamp.get(analysis_cache_key, 0)) < 300:
                print(f"Using cached analysis tracks")
                cached_analysis_tracks = self._cached_saved_tracks[analysis_cache_key]
                
                # Sample analysis tracks if needed
                if max_tracks and len(cached_analysis_tracks) > max_tracks:
                    import random
                    analysis_tracks = random.sample(cached_analysis_tracks, max_tracks)
                else:
                    analysis_tracks = cached_analysis_tracks
            
            # Check exclusion tracks cache (only if exclude_tracks=True)
            if exclude_tracks and exclusion_cache_key in self._cached_saved_tracks and (current_time - self._cached_timestamp.get(exclusion_cache_key, 0)) < 300:
                print(f"Using cached exclusion tracks")
                excluded_ids, excluded_track_data = self._cached_saved_tracks[exclusion_cache_key]
            
            # If we have both cached, return them
            if analysis_tracks is not None and (not exclude_tracks or excluded_ids):
                return analysis_tracks, excluded_ids, excluded_track_data
        
        # Determine what we need to fetch
        need_analysis_tracks = analysis_tracks is None
        need_exclusion_tracks = exclude_tracks and not excluded_ids
        
        if need_analysis_tracks or need_exclusion_tracks:
            print(f"Fetching fresh saved tracks - analysis: {need_analysis_tracks}, exclusion: {need_exclusion_tracks}")
            start_time = time.time()
            
            # First, get total count to determine how many parallel requests we need
            try:
                initial_response = sp_client.current_user_saved_tracks(limit=1, offset=0)
                total_tracks = initial_response.get('total', 0)
                print(f"Total saved tracks: {total_tracks}")
            except Exception as e:
                print(f"Error getting total count: {e}")
                return [], set(), []
            
            if total_tracks == 0:
                return [], set(), []
            
            # Determine how many tracks to fetch
            if need_exclusion_tracks:
                # If we need exclusion tracks, fetch ALL tracks
                tracks_to_fetch = total_tracks
            else:
                # If we only need analysis tracks, fetch up to max_tracks
                tracks_to_fetch = min(max_tracks or total_tracks, total_tracks)
        
        # Calculate number of parallel requests needed
        limit = 50  # Spotify API maximum
        num_requests = (tracks_to_fetch + limit - 1) // limit  # Ceiling division
        
        print(f"Making {num_requests} parallel requests to fetch {tracks_to_fetch} tracks")
        
        def fetch_batch(offset):
            """Fetch a batch of saved tracks"""
            try:
                return sp_client.current_user_saved_tracks(limit=limit, offset=offset)
            except Exception as e:
                print(f"Error fetching batch at offset {offset}: {e}")
                return None
        
        # Initialize variables for fetching
        if need_analysis_tracks:
            analysis_tracks = []
        if need_exclusion_tracks:
            excluded_track_ids = set()
            excluded_track_data = []
        
        seen_track_ids = set()
        
        with ThreadPoolExecutor(max_workers=10) as executor:  # Limit concurrent requests
            # Submit all requests
            future_to_offset = {
                executor.submit(fetch_batch, offset): offset 
                for offset in range(0, tracks_to_fetch, limit)
            }
            
            # Process completed requests
            for future in as_completed(future_to_offset):
                saved_tracks = future.result()
                if not saved_tracks or not saved_tracks.get('items'):
                    continue
                
                for item in saved_tracks['items']:
                    track = item['track']
                    if not track or not track.get('id'):
                        continue
                    
                    track_id = track['id']
                    
                    # Collect tracks based on what we need
                    if track_id not in seen_track_ids:
                        seen_track_ids.add(track_id)
                        
                        # Collect for analysis tracks if needed
                        if need_analysis_tracks:
                            analysis_tracks.append({
                                'id': track_id,
                                'name': track['name'],
                                'artists': [{'name': artist['name']} for artist in track.get('artists', [])],
                                'added_at': item.get('added_at')
                            })
                        
                        # Collect for exclusion data if needed
                        if need_exclusion_tracks:
                            excluded_track_ids.add(track_id)
                            excluded_track_data.append({
                                'id': track_id,
                                'name': track['name'],
                                'artist': ', '.join([artist['name'] for artist in track.get('artists', [])])
                            })
        
        if need_analysis_tracks or need_exclusion_tracks:
            fetch_time = time.time() - start_time
            print(f"Fetched {len(analysis_tracks) if need_analysis_tracks else 0} analysis tracks, {len(excluded_track_ids) if need_exclusion_tracks else 0} excluded tracks in {fetch_time:.2f}s")
        
        # Cache the results separately
        if not hasattr(self, '_cached_saved_tracks'):
            self._cached_saved_tracks = {}
        if not hasattr(self, '_cached_timestamp'):
            self._cached_timestamp = {}
        
        # Cache analysis tracks if we fetched them
        if need_analysis_tracks:
            self._cached_saved_tracks[analysis_cache_key] = analysis_tracks
            self._cached_timestamp[analysis_cache_key] = current_time
        
        # Cache exclusion tracks if we fetched them
        if need_exclusion_tracks:
            self._cached_saved_tracks[exclusion_cache_key] = (excluded_track_ids, excluded_track_data)
            self._cached_timestamp[exclusion_cache_key] = current_time
        
        # Sample analysis tracks if needed
        if max_tracks and len(analysis_tracks) > max_tracks:
            import random
            analysis_tracks = random.sample(analysis_tracks, max_tracks)
        
        # Return appropriate data
        excluded_ids = excluded_track_ids if exclude_tracks else set()
        excluded_track_data = excluded_track_data if exclude_tracks else []
        
        return analysis_tracks, excluded_ids, excluded_track_data
    
    def get_user_profile(self, sp: spotipy.Spotify) -> Dict:
        """Get user's basic profile information"""
        try:
            return sp.current_user()
        except Exception as e:
            print(f"Error getting user profile: {e}")
            return {}
    
    
    def get_user_playlists(self, sp: spotipy.Spotify) -> List[Dict]:
        """Get user's playlists"""
        try:
            playlists = []
            results = sp.current_user_playlists(limit=50)
            playlists.extend(results['items'])
            
            # Handle pagination
            while results['next']:
                results = sp.next(results)
                playlists.extend(results['items'])
            
            return playlists
        except Exception as e:
            print(f"Error getting playlists: {e}")
            return []
    
    def get_playlist_tracks(self, sp: spotipy.Spotify, playlist_id: str) -> List[Dict]:
        """Get tracks from a specific playlist"""
        try:
            tracks = []
            results = sp.playlist_tracks(playlist_id)
            tracks.extend([item['track'] for item in results['items'] if item['track']])
            
            # Handle pagination
            while results['next']:
                results = sp.next(results)
                tracks.extend([item['track'] for item in results['items'] if item['track']])
            
            return tracks
        except Exception as e:
            print(f"Error getting playlist tracks: {e}")
            return []
    
    
    def get_recently_played(self, sp: spotipy.Spotify, limit: int = 50) -> List[Dict]:
        """Get user's recently played tracks"""
        try:
            results = sp.current_user_recently_played(limit=limit)
            return [item['track'] for item in results['items']]
        except Exception as e:
            print(f"Error getting recently played: {e}")
            return []
    
    
    def create_playlist(self, sp: spotipy.Spotify, name: str, description: str = "", public: bool = False) -> Optional[Dict]:
        """Create a new playlist for the user"""
        try:
            user_id = sp.current_user()['id']
            playlist = sp.user_playlist_create(
                user=user_id,
                name=name,
                public=public,
                description=description
            )
            return playlist
        except Exception as e:
            print(f"Error creating playlist: {e}")
            return None
    
    def add_tracks_to_playlist(self, sp: spotipy.Spotify, playlist_id: str, track_ids: List[str]) -> bool:
        """Add tracks to an existing playlist"""
        try:
            print(f"Adding {len(track_ids)} tracks to playlist {playlist_id}")  # DEBUG
            # Spotify API allows max 100 tracks per request
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i:i+100]
                track_uris = [f"spotify:track:{track_id}" for track_id in batch]
                sp.playlist_add_items(playlist_id, track_uris)
            return True
        except Exception as e:
            print(f"Error adding tracks to playlist: {e}")
            return False
    
    def create_playlist_from_recommendations(self, sp: spotipy.Spotify, recommendations: List[Dict], playlist_name: str, description: str = "") -> Optional[Dict]:
        """Create a playlist and add recommended tracks to it"""
        try:
            # Create the playlist
            playlist = self.create_playlist(sp, playlist_name, description, public=False)
            if not playlist:
                return None
            
            # Extract track IDs from recommendations
            track_ids = [track['id'] for track in recommendations if track.get('id')]
            
            # Add tracks to the playlist
            if track_ids:
                success = self.add_tracks_to_playlist(sp, playlist['id'], track_ids)
                if success:
                    return playlist
            
            return None
        except Exception as e:
            print(f"Error creating playlist from recommendations: {e}")
            return None