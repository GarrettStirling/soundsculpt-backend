"""
Manual Discovery Recommendation Service - Using Last.fm API for manually selected seed tracks
"""

import time
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from .lastfm_service import LastFMService
from .recs_utils import RecommendationUtils

class ManualDiscoveryService:
    def __init__(self):
        self.lastfm_service = LastFMService()
        self.utils = RecommendationUtils()
        self.progress_messages = []
    
    def add_progress_message(self, message: str):
        """Add a progress message with timestamp"""
        self.utils.add_progress_message(message, self.progress_messages)
    
    def get_multiple_seed_recommendations(self, 
                                        seed_tracks: List[Dict], 
                                        n_recommendations: int = 20,
                                        excluded_track_ids: Optional[Set[str]] = None,
                                        excluded_tracks: Optional[List[Dict]] = None,
                                        access_token: Optional[str] = None,
                                        popularity: int = 50,
                                        depth: int = 3,
                                        progress_callback: Optional[callable] = None,
                                        previously_generated_track_ids: Optional[Set[str]] = None) -> Dict:
        """
        Get recommendations based on multiple seed tracks using Last.fm similarity
        
        Args:
            seed_tracks (List[Dict]): List of seed track dictionaries with 'name' and 'artist'
            n_recommendations (int): Number of recommendations to generate
            excluded_track_ids (Set[str]): Set of track IDs to exclude
            excluded_tracks (List[Dict]): List of track objects to exclude
            access_token (str): Spotify access token for additional data
            popularity (int): User's popularity preference (0-100)
            depth (int): Analysis depth (not used in this implementation)
            progress_callback (callable): Optional progress callback function
            previously_generated_track_ids (Set[str]): Track IDs from previous batches to exclude
            
        Returns:
            Dict: Recommendations with metadata
        """
        try:
            service_start_time = time.time()
            print(f"🎵 Starting Last.fm multiple seed recommendations")
            print(f"   📊 Seed tracks: {len(seed_tracks)}")
            print(f"   🎯 Target recommendations: {n_recommendations}")
            print(f"   🚫 Excluded track IDs: {len(excluded_track_ids) if excluded_track_ids else 0}")
            print(f"   🚫 Excluded tracks: {len(excluded_tracks) if excluded_tracks else 0}")
            print(f"   🎚️ Popularity preference: {popularity}")
            print(f"   🔒 Previously generated track IDs: {len(previously_generated_track_ids) if previously_generated_track_ids else 0}")
            
            # Log seed track details
            print(f"📋 SEED TRACKS DETAILS:")
            for i, track in enumerate(seed_tracks):
                print(f"   {i+1}. {track.get('name', 'Unknown')} by {track.get('artist', 'Unknown')}")
            
            all_recommendations = []
            recommended_track_ids = set()
            seen_artists = set()
            
            # Create a combined exclusion set for easier filtering
            print(f"🔧 STEP 1: Processing exclusion logic...")
            step_start = time.time()
            excluded_ids = excluded_track_ids or set()
            
            # Add previously generated track IDs to exclusion list to avoid duplicates across batches
            if previously_generated_track_ids:
                excluded_ids = excluded_ids.union(previously_generated_track_ids)
                print(f"🔒 Added {len(previously_generated_track_ids)} previously generated track IDs to exclusion list")
                print(f"🔒 Previously generated IDs: {list(previously_generated_track_ids)[:5]}{'...' if len(previously_generated_track_ids) > 5 else ''}")
            
            all_excluded_tracks = excluded_ids
            print(f"🚫 TOTAL EXCLUDED TRACK IDs: {len(all_excluded_tracks)}")
            step_duration = time.time() - step_start
            print(f"⏱️  Exclusion processing: {step_duration:.3f}s")
            
            # Process each seed track in parallel
            print(f"🔧 STEP 2: Processing seed tracks in parallel...")
            step_start = time.time()
            print(f"🎯 Using ThreadPoolExecutor with max_workers={min(3, len(seed_tracks))}")
            
            with ThreadPoolExecutor(max_workers=min(3, len(seed_tracks))) as executor:
                seed_futures = [executor.submit(self._process_single_seed_track, i, seed_track, 
                                              all_excluded_tracks, excluded_tracks, access_token, 
                                              popularity, progress_callback) 
                               for i, seed_track in enumerate(seed_tracks)]
                
                print(f"📋 Submitted {len(seed_futures)} seed track processing tasks")
                for future in as_completed(seed_futures):
                    try:
                        seed_recs = future.result()
                        all_recommendations.extend(seed_recs)
                        print(f"✅ Completed seed track processing, got {len(seed_recs)} recommendations")
                    except Exception as e:
                        print(f"❌ Error processing seed track: {e}")
                        continue
            
            step_duration = time.time() - step_start
            print(f"⏱️  Parallel seed processing: {step_duration:.3f}s")
            print(f"📊 Collected {len(all_recommendations)} total recommendations from {len(seed_tracks)} seed tracks")
            
            # Show breakdown by seed track
            for i, seed_track in enumerate(seed_tracks):
                seed_name = seed_track.get('name', 'Unknown')
                seed_artist = seed_track.get('artist', 'Unknown')
                seed_recs = [rec for rec in all_recommendations if rec.get('seed_track', '').startswith(f"{seed_name} by {seed_artist}")]
                print(f"   🎵 Seed {i+1}: '{seed_name}' by {seed_artist} → {len(seed_recs)} recommendations")
            
            # Remove duplicates and limit results
            print(f"🔧 STEP 3: Filtering and deduplicating recommendations...")
            step_start = time.time()
            
            unique_recommendations = []
            seen_track_ids = set()
            
            for rec in all_recommendations:
                track_id = rec.get('id')
                if track_id and track_id not in seen_track_ids and track_id not in all_excluded_tracks:
                    unique_recommendations.append(rec)
                    seen_track_ids.add(track_id)
                    # Don't break early - return ALL unique recommendations
            
            step_duration = time.time() - step_start
            print(f"⏱️  Filtering and deduplication: {step_duration:.3f}s")
            print(f"🎯 Final unique recommendations: {len(unique_recommendations)}")
            
            # Log final recommendations
            if unique_recommendations:
                print(f"📋 FINAL RECOMMENDATIONS:")
                for i, rec in enumerate(unique_recommendations[:5]):
                    print(f"   {i+1}. {rec.get('name', 'Unknown')} by {rec.get('artist', 'Unknown')}")
                if len(unique_recommendations) > 5:
                    print(f"   ... and {len(unique_recommendations) - 5} more")
            
            service_duration = time.time() - service_start_time
            print(f"⏱️  TOTAL SERVICE DURATION: {service_duration:.3f}s")
            
            return {
                'recommendations': unique_recommendations,
                'total_found': len(all_recommendations),
                'unique_count': len(unique_recommendations),
                'seed_tracks_processed': len(seed_tracks),
                'generation_time': service_duration,
                'method': 'lastfm_multiple_seed',
                'progress_messages': self.progress_messages,
                'no_more_recommendations': len(unique_recommendations) == 0
            }
            
        except Exception as e:
            return {"error": f"Last.fm multiple seed recommendations failed: {str(e)}"}

    def _process_single_seed_track(self, seed_index, seed_track, all_excluded_tracks, excluded_tracks, access_token, popularity, progress_callback):
        """
        Process a single seed track to find recommendations.
        
        This method handles both similar tracks and fallback to similar artists.
        It's designed to be called in parallel for multiple seed tracks.
        
        Args:
            seed_index (int): Index of the seed track for logging
            seed_track (dict): The seed track data with 'name' and 'artist'
            all_excluded_tracks (set): Set of excluded track IDs
            excluded_tracks (list): List of excluded track objects
            access_token (str): Spotify access token
            popularity (int): User's popularity preference (0-100)
            progress_callback (callable): Optional progress callback function
            
        Returns:
            list: List of recommendation dictionaries for this seed track
        """
        seed_recommendations = []
        seed_start_time = time.time()
        print(f"🔍 DEBUG: Processing seed track {seed_index+1}: '{seed_track['name']}' by {seed_track['artist']}")
        self.add_progress_message(f"Finding music similar to '{seed_track['name']}' by {seed_track['artist']}...")
        if progress_callback:
            progress_callback(f"Finding music similar to '{seed_track['name']}' by {seed_track['artist']}...")
        
        # Get similar tracks for this seed
        print(f"🔍 Getting similar tracks from Last.fm...")
        step_start = time.time()
        similar_tracks = self.lastfm_service.get_similar_tracks(seed_track['artist'], seed_track['name'], limit=30)
        step_duration = time.time() - step_start
        print(f"⏱️  Last.fm similar tracks API call: {step_duration:.3f}s")
        print(f"🔍 DEBUG: Found {len(similar_tracks)} similar tracks for '{seed_track['name']}' by {seed_track['artist']}")
        
        if not similar_tracks:
            # Fallback: try similar artists
            print(f"❌ DEBUG: No similar tracks found for '{seed_track['name']}' by {seed_track['artist']}")
            print(f"🔄 DEBUG: Trying similar artists as fallback for '{seed_track['name']}' by {seed_track['artist']}")
            
            print(f"🔍 Getting similar artists from Last.fm...")
            step_start = time.time()
            similar_artists = self.lastfm_service.get_similar_artists(seed_track['artist'], limit=10)
            step_duration = time.time() - step_start
            print(f"⏱️  Last.fm similar artists API call: {step_duration:.3f}s")
            print(f"🔍 DEBUG: Found {len(similar_artists)} similar artists as fallback")
            
            if not similar_artists:
                print(f"❌ DEBUG: No similar artists found either for '{seed_track['artist']}'")
                print(f"⚠️ No similar tracks or artists found for seed {seed_index+1}: '{seed_track['name']}' by {seed_track['artist']}")
                return []
            
            # Process similar artists in parallel
            seed_recommendations = self._process_similar_artists_parallel(
                similar_artists, seed_track, all_excluded_tracks, excluded_tracks, 
                access_token, popularity
            )
        else:
            # Process similar tracks
            print(f"🎵 Processing seed {seed_index+1}: '{seed_track['name']}' by {seed_track['artist']} - found {len(similar_tracks)} similar tracks")
            seed_recommendations = self._process_similar_tracks(
                similar_tracks, seed_track, all_excluded_tracks, excluded_tracks, 
                access_token, popularity
            )
        
        seed_duration = time.time() - seed_start_time
        print(f"⏱️  TOTAL SEED PROCESSING TIME: {seed_duration:.3f}s")
        print(f"📊 Seed {seed_index+1} generated {len(seed_recommendations)} recommendations")
        
        return seed_recommendations

    def _process_similar_artists_parallel(self, similar_artists, seed_track, all_excluded_tracks, excluded_tracks, access_token, popularity):
        """
        Process similar artists in parallel to find fallback recommendations.
        
        When a seed track has no similar tracks, this method finds similar artists
        and gets their top tracks as recommendations.
        
        Args:
            similar_artists (list): List of similar artist data from Last.fm
            seed_track (dict): The original seed track
            all_excluded_tracks (set): Set of excluded track IDs
            excluded_tracks (list): List of excluded track objects
            access_token (str): Spotify access token
            popularity (int): User's popularity preference (0-100)
            
        Returns:
            list: List of recommendation dictionaries from similar artists
        """
        recommendations = []
        
        # Use ThreadPoolExecutor for similar artists processing
        with ThreadPoolExecutor(max_workers=min(5, len(similar_artists))) as executor:
            artist_futures = [executor.submit(self._process_single_similar_artist, artist, seed_track, 
                                            all_excluded_tracks, excluded_tracks, access_token, popularity) 
                            for artist in similar_artists]
            for future in as_completed(artist_futures):
                try:
                    artist_recs = future.result()
                    recommendations.extend(artist_recs)
                except Exception as e:
                    print(f"❌ Error processing similar artist: {e}")
                    continue
        
        return recommendations

    def _process_single_similar_artist(self, similar_artist, seed_track, all_excluded_tracks, excluded_tracks, access_token, popularity):
        """
        Process a single similar artist to find recommendations.
        
        Gets the top tracks from a similar artist and filters them based on
        user preferences and exclusions.
        
        Args:
            similar_artist (dict): Similar artist data from Last.fm
            seed_track (dict): The original seed track
            all_excluded_tracks (set): Set of excluded track IDs
            excluded_tracks (list): List of excluded track objects
            access_token (str): Spotify access token
            popularity (int): User's popularity preference (0-100)
            
        Returns:
            list: List of recommendation dictionaries (usually 0-1 items)
        """
        recommendations = []
        similar_artist_name = similar_artist.get('name', '')
        if not similar_artist_name:
            return recommendations
        
        print(f"🔍 DEBUG: Fallback - {similar_artist_name}")
        
        # Get top tracks from this similar artist
        all_tracks = self.lastfm_service.get_artist_top_tracks(similar_artist_name, limit=6)
        
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
            if self.utils.is_track_excluded(track_name, similar_artist_name, all_excluded_tracks, excluded_tracks):
                continue
            
            # Check popularity preference
            if not self.utils.matches_popularity_preference(spotify_data['popularity'], popularity):
                continue
            
            # Create recommendation with multi-artist support
            recommendation = {
                'id': track_id,
                'name': track_name,
                'artist': spotify_data.get('all_artists_string', similar_artist_name),  # Use all artists if available
                'primary_artist': spotify_data.get('primary_artist', similar_artist_name),
                'all_artists': spotify_data.get('matched_artists', [similar_artist_name]),
                'album_cover': spotify_data['album_cover'],
                'preview_url': spotify_data.get('preview_url', ''),
                'external_url': spotify_data.get('external_url', ''),
                'duration_ms': spotify_data.get('duration_ms', 0),
                'popularity': spotify_data['popularity'],
                'similarity_score': 0.7,  # Default for fallback
                'source': 'lastfm_fallback',
                'seed_track': f"{seed_track['name']} by {seed_track['artist']} (fallback)"
            }
            
            recommendations.append(recommendation)
            break  # Only take one track per artist for variety
        
        return recommendations

    def _process_similar_tracks(self, similar_tracks, seed_track, all_excluded_tracks, excluded_tracks, access_token, popularity):
        """
        Process similar tracks from Last.fm to find recommendations.
        
        This is the primary recommendation method that processes tracks
        that are directly similar to the seed track.
        
        Args:
            similar_tracks (list): List of similar track data from Last.fm
            seed_track (dict): The original seed track
            all_excluded_tracks (set): Set of excluded track IDs
            excluded_tracks (list): List of excluded track objects
            access_token (str): Spotify access token
            popularity (int): User's popularity preference (0-100)
            
        Returns:
            list: List of recommendation dictionaries
        """
        recommendations = []
        
        for track in similar_tracks:
            track_name = track.get('name', '')
            artist_name = track.get('artist', {}).get('name', '') if isinstance(track.get('artist'), dict) else str(track.get('artist', ''))
            
            if not track_name or not artist_name:
                continue
            
            # Filter out Live and Commentary versions
            if self.utils.is_live_or_commentary_track(track_name):
                continue
            
            # Generate track ID
            track_id = self.utils.generate_track_id(track, artist_name)
            
            # Get track data from Spotify
            spotify_data = self.utils.get_spotify_track_data(track_name, artist_name, access_token, all_excluded_tracks) if access_token else {'found': False, 'spotify_id': None, 'popularity': 50, 'album_cover': 'https://picsum.photos/300/300?random=1'}
            
            # Skip tracks that don't exist on Spotify
            if not spotify_data.get('found', True):
                continue
            
            # Check exclusions
            if self.utils.is_track_excluded(track_name, artist_name, all_excluded_tracks, excluded_tracks):
                continue
            
            # Check popularity preference
            if not self.utils.matches_popularity_preference(spotify_data['popularity'], popularity):
                continue
            
            # Use actual similarity score from Last.fm
            similarity_score = float(track.get('match', 0)) if track.get('match') else 0.8
            
            # Create recommendation with multi-artist support
            recommendation = {
                'id': track_id,
                'name': track_name,
                'artist': spotify_data.get('all_artists_string', artist_name),  # Use all artists if available
                'primary_artist': spotify_data.get('primary_artist', artist_name),
                'all_artists': spotify_data.get('matched_artists', [artist_name]),
                'album_cover': spotify_data['album_cover'],
                'preview_url': spotify_data.get('preview_url', ''),
                'external_url': spotify_data.get('external_url', ''),
                'duration_ms': spotify_data.get('duration_ms', 0),
                'popularity': spotify_data['popularity'],
                'similarity_score': similarity_score,
                'source': 'lastfm_similar',
                'seed_track': f"{seed_track['name']} by {seed_track['artist']}"
            }
            
            recommendations.append(recommendation)
        
        return recommendations
