"""
Shared utilities for recommendation services
Common functions used across multiple recommendation algorithms
"""

import spotipy
from typing import List, Dict, Optional, Set
import time
import random


class RecommendationUtils:
    """Shared utility functions for recommendation services"""
    
    @staticmethod
    def analyze_user_patterns(sp: spotipy.Spotify) -> Dict:
        """
        Analyze user's listening patterns - shared across services
        Returns patterns dict with top_genres, favorite_artists, diversity_score, preferences
        """
        patterns = {
            'top_genres': [],
            'favorite_artists': [],
            'diversity_score': 0,
            'preferences': {}
        }
        
        try:
            print(f"  🎵 Getting your top artists and genres...")
            
            # Get top artists
            top_artists = sp.current_user_top_artists(limit=50, time_range='medium_term')
            patterns['favorite_artists'] = [artist['name'] for artist in top_artists['items']]
            
            # Extract genres from artists
            genre_count = {}
            for artist in top_artists['items']:
                for genre in artist.get('genres', []):
                    genre_count[genre] = genre_count.get(genre, 0) + 1
            
            # Sort genres by frequency
            patterns['top_genres'] = [genre for genre, count in sorted(genre_count.items(), key=lambda x: x[1], reverse=True)]
            
            # Calculate diversity score
            total_genres = len(genre_count)
            patterns['diversity_score'] = min(total_genres / 10, 1.0)  # Normalize to 0-1
            
            # Set preferences based on analysis
            patterns['preferences'] = {
                'genre_diversity': 'High' if total_genres > 15 else 'Medium' if total_genres > 8 else 'Low',
                'artist_count': len(top_artists['items']),
                'primary_genres': patterns['top_genres'][:3]
            }
            
            print(f"    ✅ Found {len(patterns['favorite_artists'])} favorite artists")
            print(f"    ✅ Identified {len(patterns['top_genres'])} genres: {patterns['top_genres'][:5]}")
            print(f"    ✅ Diversity score: {patterns['diversity_score']:.2f}")
            
        except Exception as e:
            print(f"    ⚠️ Error analyzing patterns: {e}")
        
        return patterns
    
    @staticmethod
    def get_user_tracks_smart(sp: spotipy.Spotify, max_tracks: int = 1000) -> Set[str]:
        """
        Get user's existing tracks for filtering - shared across services
        Returns set of track IDs to avoid duplicates
        """
        user_tracks = set()
        
        print(f"  🔍 Getting user's existing tracks for filtering...")
        
        try:
            # Get saved tracks - scan more thoroughly
            saved = sp.current_user_saved_tracks(limit=50)
            total_saved = saved.get('total', 0)
            
            # Get more tracks for better filtering (up to max_tracks)
            limit = min(max_tracks, total_saved)
            offset = 0
            
            print(f"    📚 Scanning {limit} of {total_saved} saved tracks...")
            
            while offset < limit:
                batch = sp.current_user_saved_tracks(limit=50, offset=offset)
                if not batch['items']:
                    break
                for item in batch['items']:
                    if item['track'] and item['track']['id']:
                        user_tracks.add(item['track']['id'])
                        # Also check for different versions/remixes by name
                        track_name = item['track']['name'].lower()
                        # Could add more sophisticated name matching here if needed
                offset += 50
                if len(batch['items']) < 50:
                    break
            
            print(f"    ✅ Found {len(user_tracks)} saved tracks for filtering")
            
            # Also get recently played for additional filtering
            try:
                recent = sp.current_user_recently_played(limit=50)
                recent_count = 0
                for item in recent['items']:
                    if item['track'] and item['track']['id']:
                        user_tracks.add(item['track']['id'])
                        recent_count += 1
                print(f"    ✅ Added {recent_count} recently played tracks")
            except Exception as recent_error:
                print(f"    ⚠️ Error getting recent tracks: {recent_error}")
            
        except Exception as e:
            print(f"    ⚠️ Error getting saved tracks: {e}")
        
        return user_tracks
    
    @staticmethod
    def get_user_tracks_simple(sp: spotipy.Spotify, max_tracks: int = 2000) -> tuple[Set[str], Dict[str, int]]:
        """
        Simple user tracks collection with artist frequency tracking
        Returns (user_tracks_set, artist_track_count_dict)
        """
        user_tracks = set()
        artist_track_count = {}
        
        print("📊 Getting user's music collection for analysis...")
        try:
            # Get saved tracks more efficiently with larger batches
            offset = 0
            batch_size = 50
            total_processed = 0
            
            while total_processed < max_tracks:  # Limit to prevent excessive processing
                batch = sp.current_user_saved_tracks(limit=batch_size, offset=offset)
                if not batch['items']:
                    break
                
                for item in batch['items']:
                    if item['track'] and item['track']['id']:
                        user_tracks.add(item['track']['id'])
                        # Track artist frequency
                        if item['track']['artists']:
                            artist_name = item['track']['artists'][0]['name']
                            artist_track_count[artist_name] = artist_track_count.get(artist_name, 0) + 1
                
                total_processed += len(batch['items'])
                offset += batch_size
                
                if len(batch['items']) < batch_size:
                    break
            
            print(f"   📚 Analyzed {len(user_tracks)} saved tracks from {len(artist_track_count)} artists")
            
        except Exception as tracks_error:
            print(f"⚠️ Error getting saved tracks: {tracks_error}")
            user_tracks = set()
            artist_track_count = {}
        
        return user_tracks, artist_track_count
    
    @staticmethod
    def apply_pattern_variation(user_patterns: Dict, generation_seed: int) -> Dict:
        """
        Apply variation to user patterns for subsequent generations
        Shuffles genre/artist order and adjusts preferences to create different recommendations
        """
        # Create a copy to avoid modifying the original
        varied_patterns = user_patterns.copy()
        
        # Set random seed based on generation for reproducible but different results
        random.seed(generation_seed * 42)  # Multiply by 42 for more variation
        
        # Strategy 1: Shuffle and rotate genre priorities
        if 'top_genres' in varied_patterns and len(varied_patterns['top_genres']) > 3:
            genres = varied_patterns['top_genres'].copy()
            
            # Rotate the top genres to emphasize different ones
            rotation = generation_seed % min(5, len(genres))  # Rotate within top 5
            varied_patterns['top_genres'] = genres[rotation:] + genres[:rotation]
            
            # Add some randomness to genre order after rotation
            if len(genres) > 6:
                # Shuffle the middle portion to add variety
                middle_start = 2
                middle_end = min(8, len(genres))
                middle_genres = genres[middle_start:middle_end]
                random.shuffle(middle_genres)
                varied_patterns['top_genres'] = (
                    genres[:middle_start] + 
                    middle_genres + 
                    genres[middle_end:]
                )
        
        # Strategy 2: Shuffle and rotate artist priorities  
        if 'favorite_artists' in varied_patterns and len(varied_patterns['favorite_artists']) > 3:
            artists = varied_patterns['favorite_artists'].copy()
            
            # Rotate artist focus
            rotation = generation_seed % min(4, len(artists))  # Rotate within top 4
            varied_patterns['favorite_artists'] = artists[rotation:] + artists[:rotation]
            
            # Add some shuffling to middle artists
            if len(artists) > 6:
                middle_start = 2
                middle_end = min(10, len(artists))
                middle_artists = artists[middle_start:middle_end]
                random.shuffle(middle_artists)
                varied_patterns['favorite_artists'] = (
                    artists[:middle_start] + 
                    middle_artists + 
                    artists[middle_end:]
                )
        
        # Strategy 3: Slightly adjust diversity score to change discovery behavior
        if 'diversity_score' in varied_patterns:
            original_score = varied_patterns['diversity_score']
            # Add small variation (-0.1 to +0.1) based on generation
            variation = (generation_seed % 21 - 10) / 100  # Range: -0.1 to +0.1
            varied_patterns['diversity_score'] = max(0, min(1, original_score + variation))
        
        # Strategy 4: Add "exploration focus" that changes search behavior
        exploration_modes = ['genre_deep', 'artist_wide', 'time_recent', 'popularity_niche', 'mixed']
        varied_patterns['exploration_mode'] = exploration_modes[generation_seed % len(exploration_modes)]
        
        print(f"    🔄 Genre rotation: {rotation if 'top_genres' in varied_patterns else 0}")
        print(f"    🎯 Exploration mode: {varied_patterns.get('exploration_mode', 'mixed')}")
        print(f"    📊 Diversity adjustment: {variation if 'diversity_score' in varied_patterns else 0:.2f}")
        
        return varied_patterns
    
    # @staticmethod
    # def build_search_strategies_with_preferences(
    #     top_genres: List[str], 
    #     top_artists: List[str], 
    #     user_preferences: Optional[Dict] = None
    # ) -> List[str]:
    #     """
    #     Build search strategies based on user data and preferences
    #     Simplified to avoid hardcoded terms that don't map to actual audio features
    #     """
    #     search_strategies = []
        
    #     # Strategy 1: Use user's top genres with realistic search modifications
    #     for genre in top_genres[:10]:
    #         # Base genre searches
    #         base_queries = [
    #             f'genre:"{genre}" year:2020-2024',
    #             f'genre:"{genre}" year:2018-2022',
    #             f'{genre} indie discover',
    #             f'{genre} new release'
    #         ]
            
    #         # Add realistic preference-based search modifications
    #         if user_preferences:
    #             energy = user_preferences.get('energy', 50)
                
    #             # Use broader, more reliable search terms
    #             if energy < 40:  # Lower energy - focus on indie/alternative
    #                 base_queries.extend([
    #                     f'{genre} indie',
    #                     f'{genre} alternative',
    #                     f'{genre} underground'
    #                 ])
    #             elif energy > 60:  # Higher energy - allow more mainstream
    #                 base_queries.extend([
    #                     f'{genre} popular',
    #                     f'{genre} trending'
    #                 ])
            
    #         search_strategies.extend(base_queries)
        
    #     # Strategy 2: Discovery searches with realistic modifications
    #     base_discovery = [
    #         'indie rock discover year:2020-2024',
    #         'electronic discover year:2021-2024', 
    #         'alternative discover year:2019-2024',
    #         'indie pop discover year:2020-2024'
    #     ]
        
    #     if user_preferences:
    #         energy = user_preferences.get('energy', 50)
    #         if energy < 40:
    #             base_discovery.extend([
    #                 'indie underground discover',
    #                 'alternative experimental discover',
    #                 'indie folk discover'
    #             ])
    #         elif energy > 60:
    #             base_discovery.extend([
    #                 'popular indie discover',
    #                 'trending alternative discover',
    #                 'indie chart discover'
    #             ])
        
    #     search_strategies.extend(base_discovery)
        
    #     # Strategy 3: Based on user's artists but find similar artists
    #     for artist in top_artists[:5]:
    #         search_strategies.extend([
    #             f'similar to "{artist}" discover',
    #             f'like "{artist}" indie'
    #         ])
        
    #     return search_strategies
    
    @staticmethod
    def search_based_discovery(
        sp: spotipy.Spotify, 
        user_patterns: Dict, 
        user_tracks: Set[str], 
        n_recommendations: int, 
        user_preferences: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Discover new music using dynamic search patterns based purely on user data
        No hardcoded search terms - generates queries from user's actual listening patterns
        """
        print(f"  🔍 Data-driven discovery for {n_recommendations} tracks...")
        
        recommendations = []
        seen_ids = set(user_tracks)
        artist_counts = {}  # Track diversity
        seen_song_artist_pairs = set()  # Track song+artist combinations to avoid duplicates
        
        # Get user's actual data
        top_genres = user_patterns.get('top_genres', [])
        favorite_artists = user_patterns.get('favorite_artists', [])
        exploration_mode = user_patterns.get('exploration_mode', 'mixed')
        
        print(f"    🎯 Exploration mode: {exploration_mode}")
        
        # Calculate discovery preference - affects popularity filtering only
        discovery_focus = 50  # Default: balanced
        if user_preferences:
            discovery_focus = user_preferences.get('energy', 50)  # Using energy as discovery focus
        
        # Dynamic popularity threshold based on discovery focus AND exploration mode
        # Lower values = more underground/niche, Higher values = more mainstream
        base_threshold = 30 + (discovery_focus * 0.6)  # Range: 30-90
        
        # Modify threshold based on exploration mode
        if exploration_mode == 'popularity_niche':
            popularity_threshold = base_threshold * 0.7  # Prefer more niche tracks
        elif exploration_mode == 'genre_deep':
            popularity_threshold = base_threshold * 0.8  # Slightly more niche for deeper genre exploration
        else:
            popularity_threshold = base_threshold
        
        print(f"    Discovery focus: {discovery_focus} (popularity threshold: {popularity_threshold:.0f})")
        
        # Strategy 1: Pure genre search - adapt based on exploration mode
        genre_limit = 6  # Default
        if exploration_mode == 'genre_deep':
            genre_limit = 4  # Focus on fewer genres but search deeper
        elif exploration_mode == 'artist_wide':
            genre_limit = 3  # Focus more on artist discovery later
        elif exploration_mode == 'mixed':
            genre_limit = 5  # Balanced approach
            
        for genre in top_genres[:genre_limit]:
            try:
                print(f"    Searching genre: {genre}")
                
                # Simple, clean genre searches - adapt queries based on exploration mode
                search_queries = [
                    f'genre:"{genre}"',
                    f'{genre}',  # Sometimes genre: doesn't work well
                ]
                
                # Add time-based queries based on exploration mode
                current_year = 2024
                if exploration_mode == 'time_recent':
                    # Focus more on recent music
                    year_ranges = [f'{current_year-1}-{current_year}', f'{current_year-2}-{current_year-1}']
                else:
                    # Standard time ranges
                    year_ranges = [f'{current_year-2}-{current_year}', f'{current_year-4}-{current_year-2}']
                
                for year_range in year_ranges:
                    search_queries.append(f'genre:"{genre}" year:{year_range}')
                
                for query in search_queries:
                    try:
                        results = sp.search(q=query, type='track', limit=20)
                        
                        for track in results['tracks']['items']:
                            if len(recommendations) >= n_recommendations:
                                break
                                
                            if track['id'] in seen_ids:
                                continue
                                
                            # Check for duplicate song+artist combinations
                            song_artist_key = f"{track['name'].lower()}_{track['artists'][0]['name'].lower() if track['artists'] else 'unknown'}"
                            if song_artist_key in seen_song_artist_pairs:
                                print(f"      Skipped duplicate: {track['name']} by {track['artists'][0]['name'] if track['artists'] else 'Unknown'}")
                                continue
                                
                            # Enforce artist diversity
                            main_artist = track['artists'][0]['name'] if track['artists'] else 'Unknown'
                            if artist_counts.get(main_artist, 0) >= 2:  # Max 2 per artist
                                continue
                                
                            # Apply popularity filtering based on discovery preference
                            track_popularity = track.get('popularity', 0)
                            if track_popularity <= popularity_threshold:
                                # Debug logging to check track data
                                print(f"      DEBUG - Track name: '{track['name']}', Genre context: '{genre}'")
                                
                                recommendations.append(RecommendationUtils.format_track_recommendation(
                                    track, f'genre_{genre.replace(" ", "_")}'
                                ))
                                seen_ids.add(track['id'])
                                seen_song_artist_pairs.add(song_artist_key)
                                artist_counts[main_artist] = artist_counts.get(main_artist, 0) + 1
                                print(f"      Added: {track['name']} by {main_artist} (pop: {track_popularity})")
                                
                    except Exception as query_error:
                        print(f"      Search error for '{query}': {query_error}")
                        continue
                        
                if len(recommendations) >= n_recommendations:
                    break
                    
            except Exception as genre_error:
                print(f"    Error searching genre '{genre}': {genre_error}")
                continue
        
        # Strategy 2: Artist-based discovery - adapt based on exploration mode
        if len(recommendations) < n_recommendations:
            print(f"    Expanding search with artist similarity...")
            
            artist_limit = 4  # Default
            if exploration_mode == 'artist_wide':
                artist_limit = 6  # Use more artists for wider discovery
            elif exploration_mode == 'genre_deep':
                artist_limit = 2  # Use fewer artists, focus stayed on genres
            
            for artist_name in favorite_artists[:artist_limit]:
                try:
                    # Search using artist name as a style reference
                    # This finds tracks that mention the artist or are similar
                    search_queries = [
                        f'"{artist_name}"',  # Tracks that reference this artist
                        artist_name  # Broader search
                    ]
                    
                    for query in search_queries:
                        try:
                            results = sp.search(q=query, type='track', limit=15)
                            
                            for track in results['tracks']['items']:
                                if len(recommendations) >= n_recommendations:
                                    break
                                    
                                if track['id'] in seen_ids:
                                    continue
                                    
                                # Check for duplicate song+artist combinations
                                song_artist_key = f"{track['name'].lower()}_{track['artists'][0]['name'].lower() if track['artists'] else 'unknown'}"
                                if song_artist_key in seen_song_artist_pairs:
                                    continue
                                    
                                # Don't recommend the actual artist we're searching for
                                track_artists = [a['name'].lower() for a in track['artists']]
                                if artist_name.lower() in track_artists:
                                    continue
                                    
                                main_artist = track['artists'][0]['name'] if track['artists'] else 'Unknown'
                                if artist_counts.get(main_artist, 0) >= 2:
                                    continue
                                    
                                # Apply popularity filtering
                                track_popularity = track.get('popularity', 0)
                                # Be slightly more lenient for artist-based discovery
                                artist_popularity_threshold = popularity_threshold + 10
                                
                                if track_popularity <= artist_popularity_threshold:
                                    recommendations.append(RecommendationUtils.format_track_recommendation(
                                        track, f'similar_to_{artist_name.replace(" ", "_")}'
                                    ))
                                    seen_ids.add(track['id'])
                                    seen_song_artist_pairs.add(song_artist_key)
                                    artist_counts[main_artist] = artist_counts.get(main_artist, 0) + 1
                                    print(f"      Added: {track['name']} by {main_artist} (similar to {artist_name})")
                                    
                        except Exception as query_error:
                            print(f"      Search error for '{query}': {query_error}")
                            continue
                            
                    if len(recommendations) >= n_recommendations:
                        break
                        
                except Exception as artist_error:
                    print(f"    Error searching artist '{artist_name}': {artist_error}")
                    continue
        
        print(f"  ✅ Generated {len(recommendations)} recommendations using pure data-driven search")
        return recommendations

    @staticmethod
    def calculate_popularity_threshold(user_preferences: Optional[Dict], base_threshold: int = 75) -> int:
        """Calculate popularity threshold based on user preferences"""
        if user_preferences:
            energy = user_preferences.get('energy', 50)
            # Lower energy = prefer less popular (more niche) tracks
            # Higher energy = allow more popular (mainstream) tracks
            return int(base_threshold - 15 + (energy * 0.2))  # Range: 60-90
        return base_threshold

    @staticmethod
    def format_track_recommendation(track: Dict, discovery_method: str) -> Dict:
        """Standard format for track recommendations across services"""
        return {
            'id': track['id'],
            'name': track['name'],
            'artist': ', '.join([a['name'] for a in track['artists']]),
            'album': track['album']['name'],
            'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
            'external_url': track['external_urls']['spotify'],
            'popularity': track.get('popularity', 0),
            'discovery_method': discovery_method
        }
