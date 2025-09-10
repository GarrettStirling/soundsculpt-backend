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
                return 'https://via.placeholder.com/300x300/333/fff?text=♪'
            
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
            
            return 'https://via.placeholder.com/300x300/333/fff?text=♪'
            
        except Exception as e:
            return 'https://via.placeholder.com/300x300/333/fff?text=♪'
    
    def get_spotify_track_data(self, track_name: str, artist_name: str, access_token: str) -> Dict:
        """Get track data including popularity from Spotify search"""
        try:
            if not access_token:
                return {'popularity': 50, 'album_cover': 'https://via.placeholder.com/300x300/333/fff?text=♪'}
            
            # Search for the track on Spotify
            sp = self.spotify_service.create_spotify_client(access_token)
            search_query = f"track:{track_name} artist:{artist_name}"
            
            results = sp.search(q=search_query, type='track', limit=1)
            
            if results and results.get('tracks', {}).get('items'):
                track = results['tracks']['items'][0]
                album = track.get('album', {})
                images = album.get('images', [])
                
                album_cover = 'https://via.placeholder.com/300x300/333/fff?text=♪'
                if images:
                    album_cover = images[1]['url'] if len(images) > 1 else images[0]['url']
                
                return {
                    'popularity': track.get('popularity', 50),
                    'album_cover': album_cover,
                    'duration_ms': track.get('duration_ms', 0),
                    'preview_url': track.get('preview_url'),
                    'external_url': track.get('external_urls', {}).get('spotify', f"https://open.spotify.com/search/{track_name}%20{artist_name}")
                }
            
            return {'popularity': 50, 'album_cover': 'https://via.placeholder.com/300x300/333/fff?text=♪'}
            
        except Exception as e:
            return {'popularity': 50, 'album_cover': 'https://via.placeholder.com/300x300/333/fff?text=♪'}
    
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
                                         user_saved_tracks: Set[str] = None, 
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
            all_excluded_tracks = excluded_ids.union(user_saved_tracks) if user_saved_tracks else excluded_ids
            
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
                    similar_artists = self.lastfm_service.get_similar_artists(seed_track['artist'], limit=10)
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
                            
                            # Skip if already excluded
                            if track_id in all_excluded_tracks:
                                continue
                            
                            # Get track data from Spotify
                            spotify_data = self.get_spotify_track_data(track_name, similar_artist_name, access_token) if access_token else {'popularity': 50, 'album_cover': 'https://via.placeholder.com/300x300/333/fff?text=♪'}
                            
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
                            break  # Only take one track per artist
                    
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
                    spotify_data = self.get_spotify_track_data(track_name, artist_name, access_token) if access_token else {'popularity': 50, 'album_cover': 'https://via.placeholder.com/300x300/333/fff?text=♪'}
                    
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
                    
                    recommendation = {
                        'id': f"lastfm_{track.get('mbid', '')}" if track.get('mbid') else f"lastfm_{hash(track_name + artist_name)}",
                        'name': track_name,
                        'artist': artist_name,
                        'album': 'Unknown Album',
                        'duration_ms': 0,
                        'popularity': 50,
                        'preview_url': None,
                        'external_url': f"https://open.spotify.com/search/{track_name}%20{artist_name}",
                        'images': [{'url': 'https://via.placeholder.com/300x300/333/fff?text=♪'}],
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
    
    def get_auto_discovery_recommendations(self, 
                                           user_tracks: List[Dict], # these are the filtered and randomized tracks used to build recommendations
                                           n_recommendations: int = 30, 
                                           excluded_track_ids: Set[str] = None, 
                                           access_token: str = None, 
                                           depth: int = 3, 
                                           popularity: int = 50, 
                                           user_saved_tracks: Set[str] = None, # these all all the saved tracks (only used if user decides to exclude them)
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
            
            for track in user_tracks:  # Analyze the filtered tracks provided (based on depth slider)
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
            
            print(f"top artists: {top_artists}")
            
            # ============================================================================
            # STEP 4: SETUP FILTERING & EXCLUSION LISTS
            # ============================================================================
            # Prepare lists to avoid recommending tracks the user already has
            all_recommendations = []
            seen_artists = set(artist_counts.keys())  # Exclude user's current artists
            excluded_ids = excluded_track_ids or set() # if the user decided to exclude tracks
            
            # Get user's saved track IDs for filtering
            user_track_ids = set()
            for track in user_tracks:
                if track.get('id'):
                    user_track_ids.add(track['id'])
            
            # Add user's saved tracks to the exclusion list (if the user decided to exclude them)
            if user_saved_tracks:
                user_track_ids.update(user_saved_tracks)
            
            # Create a combined exclusion set for easier filtering
            all_excluded_tracks = excluded_ids.union(user_track_ids)
            
            # ============================================================================
            # STEP 5: MAIN RECOMMENDATION GENERATION LOOP
            # ============================================================================
            # For each of the user's top artists, find similar artists and their best tracks
            for i, (artist_name, count) in enumerate(top_artists):
                if len(all_recommendations) >= n_recommendations:
                    break
                
                # Send progress update for each artist being processed
                self.add_progress_message(f"Discovering music similar to {artist_name}...")
                if progress_callback:
                    progress_callback(f"Discovering music similar to {artist_name}...")
                
                # ============================================================================
                # STEP 5A: FIND SIMILAR ARTISTS USING LAST.FM
                # ============================================================================
                # Use Last.fm's similarity data to find artists that sound like the user's favorites
                # This is the core of the recommendation algorithm
                time_start = time.time()
                similar_artists = self.lastfm_service.get_similar_artists(artist_name, limit=10)
                time_end = time.time()
                time_duration = round(time_end - time_start, 2)
                print(f"total duration of getting similar artists to {artist_name}: {time_duration}")
                print(f"total similar artists found: {len(similar_artists)}")
                print(f"🔍 DEBUG: Similar artists for {artist_name}: {[artist.get('name', 'Unknown') for artist in similar_artists[:5]]}")
                
                # ============================================================================
                # STEP 5B: GET TOP TRACKS FROM EACH SIMILAR ARTIST
                # ============================================================================
                # For each similar artist, get their most popular tracks
                # We limit to 2 tracks per artist to ensure variety
                for similar_artist in similar_artists:
                    if len(all_recommendations) >= n_recommendations:
                        break
                    
                    similar_artist_name = similar_artist.get('name', '')
                    if not similar_artist_name or similar_artist_name.lower() in seen_artists:
                        continue
                    
                    # Get tracks 3-4 from this similar artist (skip the most popular ones)
                    time_start = time.time()
                    all_tracks = self.lastfm_service.get_artist_top_tracks(similar_artist_name, limit=4)  # Get more tracks to ensure we have enough
                    time_end = time.time()
                    time_duration = round(time_end - time_start, 2)
                    print(f"total duration of getting top tracks from {similar_artist_name}: {time_duration}")
                    print(f"total tracks found: {len(all_tracks)}")
                    
                    # if artist has at least 4 tracks, then take tracks 3-4 (index 2-4), if not, then take tracks 1-2 (index 0-2)
                    if len(all_tracks) >= 4:
                        top_tracks = all_tracks[2:4]  # Get 3rd and 4th most popular tracks
                        print(f"✅ DEBUG: {similar_artist_name} has {len(all_tracks)} tracks, using tracks 3-4")
                    else:
                        top_tracks = all_tracks[0:2]  # Get 1st and 2nd most popular tracks
                        print(f"⚠️ DEBUG: {similar_artist_name} only has {len(all_tracks)} tracks, using tracks 1-2")
                    
                    print(f"🔍 DEBUG: Selected {len(top_tracks)} tracks from {similar_artist_name}")
                    
                    # ============================================================================
                    # STEP 5C: PROCESS EACH TRACK WITH FILTERING & ENRICHMENT
                    # ============================================================================
                    # For each track, apply filters and enrich with Spotify data
                    for track in top_tracks:
                        if len(all_recommendations) >= n_recommendations:
                            break
                        
                        track_name = track.get('name', '')
                        if not track_name:
                            continue
                        
                        # Filter out Live and Commentary versions (users typically want studio versions)
                        track_name_lower = track_name.lower()
                        if ('live' in track_name_lower or 'commentary' in track_name_lower or 
                            '(live' in track_name_lower or '(commentary' in track_name_lower or
                            '[live' in track_name_lower or '[commentary' in track_name_lower):
                            continue
                        
                        # Generate consistent track ID for deduplication
                        if track.get('mbid'):
                            track_id = f"lastfm_{track.get('mbid')}"
                        else:
                            # Use consistent hash based on track name and artist
                            normalized_str = f"{track_name.lower().strip()}|{similar_artist_name.lower().strip()}"
                            track_id = f"lastfm_{hash(normalized_str)}"
                        
                        # Skip if already excluded (saved by user or previously recommended)
                        if track_id in all_excluded_tracks:
                            continue
                        
                        # ============================================================================
                        # STEP 5D: ENRICH WITH SPOTIFY DATA & APPLY POPULARITY FILTERS
                        # ============================================================================
                       
                        # Get track data from Spotify (including popularity, album cover, preview URL)
                        time_start = time.time()
                        spotify_data = self.get_spotify_track_data(track_name, similar_artist_name, access_token) if access_token else {'popularity': 50, 'album_cover': 'https://via.placeholder.com/300x300/333/fff?text=♪'}
                        time_end = time.time()
                        time_duration = round(time_end - time_start, 2)
                        print(f"total duration of getting spotify data for {track_name} by {similar_artist_name}: {time_duration}")
                        # print new line
                        print("\n\n")
                        
                        # Check if track matches user's popularity preference
                        popularity_group = self.get_popularity_group(spotify_data['popularity'], popularity)
                        
                        # Skip tracks that don't match user's preference (unless they're in the balanced group)
                        if popularity_group == "underground" and popularity > 66:
                            continue  # User wants popular music, skip underground
                        elif popularity_group == "popular" and popularity < 34:
                            continue  # User wants underground music, skip popular
                        
                        # ============================================================================
                        # STEP 5E: CREATE RECOMMENDATION OBJECT
                        # ============================================================================
                        # Build the final recommendation object with all necessary data for the frontend
                        recommendation = {
                            'id': track_id,
                            'name': track_name,
                            'artist': similar_artist_name,
                            'album': 'Unknown Album',
                            'duration_ms': spotify_data.get('duration_ms', 0),
                            'popularity': spotify_data['popularity'],
                            # 'popularity_group': popularity_group,
                            'preview_url': spotify_data.get('preview_url'),
                            'external_url': spotify_data.get('external_url', f"https://open.spotify.com/search/{track_name}%20{similar_artist_name}"),
                            # 'images': [{'url': spotify_data['album_cover']}],
                            'album_cover': spotify_data['album_cover'],
                            # 'similarity_score': similarity_score,
                            # 'source': f'lastfm_auto_{artist_name}'
                        }
                        
                        all_recommendations.append(recommendation)
                        seen_artists.add(similar_artist_name.lower())
                        break  # Only take one track per artist to ensure variety
            
            # ============================================================================
            # STEP 6: FINALIZE & RETURN RECOMMENDATIONS
            # ============================================================================
            # Shuffle recommendations to ensure variety on each request (no predictable order)
            random.shuffle(all_recommendations)
            print(f"total recommendations before filter: {len(all_recommendations)}")
            
            # Limit to requested number of recommendations
            all_recommendations = all_recommendations[:n_recommendations]
            print(f"total recommendations after filter: {len(all_recommendations)}")
            
            # Return the final recommendation results with metadata
            return {
                'recommendations': all_recommendations,
                'seed_track': {
                    'name': 'User Profile',
                    'artist': 'Auto Discovery'
                },
                'generation_time': 0,
                'method': 'lastfm_auto_discovery',
                'progress_messages': self.progress_messages
            }
            
        except Exception as e:
            return {"error": f"Last.fm auto discovery failed: {str(e)}"}
