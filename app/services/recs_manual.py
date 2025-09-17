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
            print(f"🎵 Processing {len(seed_tracks)} seeds for {n_recommendations} recommendations")
            
            all_recommendations = []
            recommended_track_ids = set()
            seen_artists = set()
            
            # Create a combined exclusion set for easier filtering
            excluded_ids = excluded_track_ids or set()
            
            # Add previously generated track IDs to exclusion list to avoid duplicates across batches
            if previously_generated_track_ids:
                excluded_ids = excluded_ids.union(previously_generated_track_ids)
            
            all_excluded_tracks = excluded_ids
            
            # Process seed tracks in parallel
            
            with ThreadPoolExecutor(max_workers=min(3, len(seed_tracks))) as executor:
                seed_futures = [executor.submit(self._process_single_seed_track, i, seed_track, 
                                              all_excluded_tracks, excluded_tracks, access_token, 
                                              popularity, progress_callback) 
                               for i, seed_track in enumerate(seed_tracks)]
                
                for future in as_completed(seed_futures):
                    try:
                        seed_recs = future.result()
                        all_recommendations.extend(seed_recs)
                    except Exception as e:
                        print(f"❌ Error processing seed track: {e}")
                        continue
            
            print(f"📊 Generated {len(all_recommendations)} total recommendations")
            
            # Remove duplicates and limit results
            step_start = time.time()
            
            unique_recommendations = []
            seen_track_ids = set()
            
            excluded_count = 0
            duplicate_count = 0
            
            for rec in all_recommendations:
                track_id = rec.get('id')
                if not track_id:
                    continue
                    
                if track_id in seen_track_ids:
                    duplicate_count += 1
                    continue
                    
                if track_id in all_excluded_tracks:
                    excluded_count += 1
                    continue
                    
                unique_recommendations.append(rec)
                seen_track_ids.add(track_id)
                # Don't break early - return ALL unique recommendations
            
            print(f"🔍 DEBUG: Filtering results - Total: {len(all_recommendations)}, Duplicates: {duplicate_count}, Excluded: {excluded_count}, Unique: {len(unique_recommendations)}")
            
            # Debug: Show why recommendations are being excluded
            if excluded_count > 0 and all_recommendations:
                print(f"🔍 DEBUG: {excluded_count} recommendations excluded (already in exclusion list)")
                if excluded_count == len(all_recommendations):
                    print(f"⚠️ DEBUG: ALL recommendations excluded - generating new ones from previous tracks")
                    
                    # Generate new recommendations using previous tracks as seeds
                    new_recommendations = self._generate_new_recommendations_from_previous_tracks(
                        all_excluded_tracks, excluded_tracks, access_token, popularity, progress_callback
                    )
                    
                    if new_recommendations:
                        print(f"✅ DEBUG: Generated {len(new_recommendations)} new recommendations from previous tracks")
                        unique_recommendations.extend(new_recommendations)
                    else:
                        print(f"❌ DEBUG: Could not generate new recommendations - no more sources available")
            
            step_duration = time.time() - step_start
            print(f"⏱️  Filtering and deduplication: {step_duration:.3f}s")
            print(f"🎯 Final unique recommendations: {len(unique_recommendations)}")
            
            # Filter to one song per artist (manual discovery only)
            step_start = time.time()
            artist_filtered_recommendations = []
            seen_artists = set()
            
            for rec in unique_recommendations:
                artist = rec.get('artist', 'Unknown')
                if artist not in seen_artists:
                    artist_filtered_recommendations.append(rec)
                    seen_artists.add(artist)
            
            step_duration = time.time() - step_start
            print(f"⏱️  Artist filtering (one per artist): {step_duration:.3f}s")
            print(f"🎯 After artist filtering: {len(artist_filtered_recommendations)} recommendations")
            
            # Check for insufficient recommendations and try to fill using previous recommendations as seeds
            final_recommendations = artist_filtered_recommendations
            if len(final_recommendations) < n_recommendations and len(final_recommendations) > 0:
                print(f"⚠️ INSUFFICIENT RECOMMENDATIONS: Got {len(final_recommendations)}, need {n_recommendations}")
                print(f"🔄 Attempting to fill using current recommendations as seeds...")
                
                # Use some of the current recommendations as new seeds
                new_seeds = final_recommendations[:min(3, len(final_recommendations))]  # Use up to 3 as seeds
                additional_recommendations = []
                
                for seed_rec in new_seeds:
                    try:
                        # Create a seed track from the recommendation
                        new_seed_track = {
                            'name': seed_rec.get('name', ''),
                            'artist': seed_rec.get('primary_artist', seed_rec.get('artist', ''))
                        }
                        
                        # Get similar tracks for this new seed
                        similar_tracks = self.lastfm_service.get_similar_tracks(
                            new_seed_track['artist'], 
                            new_seed_track['name'], 
                            limit=10
                        )
                        
                        if similar_tracks:
                            # Process these similar tracks
                            seed_recs = self._process_similar_tracks(
                                similar_tracks, new_seed_track, all_excluded_tracks, 
                                excluded_tracks, access_token, popularity
                            )
                            additional_recommendations.extend(seed_recs)
                            
                            if len(additional_recommendations) >= (n_recommendations - len(final_recommendations)):
                                break
                                
                    except Exception as e:
                        print(f"⚠️ Error using recommendation as seed: {e}")
                        continue
                
                # Filter additional recommendations to avoid duplicates
                seen_ids = {rec.get('id') for rec in final_recommendations}
                unique_additional = []
                for rec in additional_recommendations:
                    if rec.get('id') not in seen_ids and rec.get('id') not in all_excluded_tracks:
                        unique_additional.append(rec)
                        seen_ids.add(rec.get('id'))
                        if len(unique_additional) >= (n_recommendations - len(final_recommendations)):
                            break
                
                # Add unique additional recommendations
                final_recommendations.extend(unique_additional)
                print(f"🔄 Added {len(unique_additional)} additional recommendations from seed expansion")
            
            # Log final recommendations
            if final_recommendations:
                print(f"📋 FINAL RECOMMENDATIONS:")
                for i, rec in enumerate(final_recommendations[:5]):
                    print(f"   {i+1}. {rec.get('name', 'Unknown')} by {rec.get('artist', 'Unknown')}")
                if len(final_recommendations) > 5:
                    print(f"   ... and {len(final_recommendations) - 5} more")
            
            service_duration = time.time() - service_start_time
            print(f"⏱️  TOTAL SERVICE DURATION: {service_duration:.3f}s")
            
            # Check for no more recommendations and insufficient recommendations
            no_more_recommendations = len(final_recommendations) == 0
            insufficient_recommendations = len(final_recommendations) > 0 and len(final_recommendations) < n_recommendations
            
            return {
                'recommendations': final_recommendations,
                'total_found': len(all_recommendations),
                'unique_count': len(final_recommendations),
                'seed_tracks_processed': len(seed_tracks),
                'generation_time': service_duration,
                'method': 'lastfm_multiple_seed',
                'progress_messages': self.progress_messages,
                'no_more_recommendations': no_more_recommendations,
                'insufficient_recommendations': insufficient_recommendations
            }
            
        except Exception as e:
            print(f"❌ CRITICAL ERROR in manual discovery service: {str(e)}")
            print(f"❌ Error type: {type(e).__name__}")
            import traceback
            print(f"❌ Full traceback: {traceback.format_exc()}")
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
            similar_artists = self.lastfm_service.get_similar_artists(seed_track['artist'], limit=20)
            step_duration = time.time() - step_start
            print(f"⏱️  Last.fm similar artists API call: {step_duration:.3f}s")
            print(f"🔍 DEBUG: Found {len(similar_artists)} similar artists as fallback")
            
            if not similar_artists:
                print(f"❌ DEBUG: No similar artists found for '{seed_track['artist']}'")
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
            # Continue to get more tracks per artist to reach target count
        
        return recommendations

    def _generate_new_recommendations_from_previous_tracks(self, all_excluded_tracks, excluded_tracks, access_token, popularity, progress_callback):
        """
        Generate new recommendations using previously generated tracks as seeds.
        This is used when all original recommendations have been exhausted.
        """
        try:
            # Get some previously generated tracks to use as new seeds
            # We'll use the first few tracks from the exclusion list as seeds
            excluded_track_list = list(all_excluded_tracks)[:5]  # Use first 5 as seeds
            
            if not excluded_track_list:
                return []
            
            print(f"🔍 DEBUG: Using {len(excluded_track_list)} previous tracks as new seeds")
            
            new_recommendations = []
            
            for track_id in excluded_track_list:
                try:
                    # Parse the track ID to get track name and artist
                    # Format: "lastfm_{hash}_{track_name}_by_{artist_name}"
                    if '_by_' in track_id:
                        parts = track_id.split('_by_')
                        if len(parts) == 2:
                            track_name = parts[0].split('_', 2)[-1].replace('_', ' ')
                            artist_name = parts[1].replace('_', ' ')
                            
                            # Create a seed track
                            seed_track = {
                                'name': track_name,
                                'artist': artist_name
                            }
                            
                            # Get similar tracks for this seed
                            similar_tracks = self.lastfm_service.get_similar_tracks(artist_name, track_name, limit=10)
                            
                            if similar_tracks:
                                # Process similar tracks
                                seed_recommendations = self._process_similar_tracks(
                                    similar_tracks, seed_track, all_excluded_tracks, excluded_tracks, access_token, popularity
                                )
                                new_recommendations.extend(seed_recommendations)
                                
                                if len(new_recommendations) >= 20:  # Stop when we have enough
                                    break
                
                except Exception as e:
                    print(f"⚠️ DEBUG: Error processing previous track as seed: {e}")
                    continue
            
            return new_recommendations[:20]  # Return up to 20 new recommendations
            
        except Exception as e:
            print(f"❌ DEBUG: Error generating new recommendations from previous tracks: {e}")
            return []

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
