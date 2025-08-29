from dotenv import load_dotenv
load_dotenv()
"""
Advanced Recommendation Service - Pattern-based music discovery approach
Uses search patterns and user behavior analysis since Spotify deprecated most ML endpoints
"""

import spotipy
import numpy as np
from typing import List, Dict, Optional
import time
import random
from .spotify_service import SpotifyService
import cProfile
import pstats
from io import StringIO

class AdvancedRecommendationService:
    def __init__(self):
        self.spotify_service = SpotifyService()
        
    def get_recommendations(self, access_token: str, n_recommendations: int = 30) -> Dict:
        """
        Get recommendations using advanced pattern-based discovery (audio features deprecated Nov 2024)
        """
        start_time = time.time()
        
        try:
            print("=== ADVANCED PATTERN-BASED RECOMMENDATION SERVICE ===")
            print("[DEPRECATED NOTICE] Spotify deprecated audio features, related artists, and recommendations APIs on Nov 27, 2024")
            print("[NEW APPROACH] Using advanced search patterns and user behavior analysis")
            print("[BIAS NOTICE] This model may favor certain genres and time periods due to search limitations. Results depend on Spotify's search algorithm biases and user listening patterns.")
            
            sp = self.spotify_service.create_spotify_client(access_token)
            
            # Test the connection first
            try:
                print(f"Testing token...")
                user_info = sp.me()
                print(f"Connected to Spotify user: {user_info.get('display_name', 'Unknown')}")
            except Exception as auth_error:
                print(f"Authentication failed: {auth_error}")
                return {"error": f"Invalid access token: {str(auth_error)}"}
            
            step_time = time.time()
            print("STEP 1: Analyzing your music taste patterns...")
            user_patterns = self._analyze_user_patterns(sp)
            print(f"  ⏱️ Step 1 completed in {time.time() - step_time:.2f}s")
            
            step_time = time.time()
            print("STEP 2: Getting your existing tracks for filtering...")
            user_tracks = self._get_user_tracks_smart(sp)
            print(f"  ⏱️ Step 2 completed in {time.time() - step_time:.2f}s")
            
            step_time = time.time()
            print("STEP 3: Discovering new music using pattern analysis...")
            recommendations = self._search_based_discovery(sp, user_patterns, user_tracks, n_recommendations)
            print(f"  ⏱️ Step 3 completed in {time.time() - step_time:.2f}s")
            
            execution_time = time.time() - start_time
            print(f"✅ TOTAL TIME: {execution_time:.2f}s for {len(recommendations)} recommendations")
            
            return {
                "recommendations": recommendations,
                "execution_time_seconds": execution_time,
                "algorithm": "Advanced Pattern-Based Discovery",
                "user_profile": {
                    "top_genres": user_patterns.get('top_genres', [])[:5],
                    "favorite_artists": user_patterns.get('favorite_artists', [])[:5],
                    "listening_diversity": user_patterns.get('diversity_score', 0),
                    "preferences": user_patterns.get('preferences', {})
                },
                "total_candidates_analyzed": len(user_tracks) + len(recommendations)
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"❌ Error in advanced recommendations: {str(e)}")
            return {
                "error": str(e),
                "execution_time_seconds": execution_time,
                "recommendations": []
            }
    
    def _analyze_user_patterns(self, sp) -> Dict:
        """Analyze user's listening patterns"""
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
    
    def _get_user_tracks_smart(self, sp) -> set:
        """Get user's existing tracks for filtering"""
        user_tracks = set()
        
        print(f"  🔍 Getting user's existing tracks for filtering...")
        
        try:
            # Get saved tracks - scan more thoroughly
            saved = sp.current_user_saved_tracks(limit=50)
            total_saved = saved.get('total', 0)
            
            # Get more tracks for better filtering (up to 1000)
            limit = min(1000, total_saved)
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
    
    def _search_based_discovery(self, sp, user_patterns: Dict, user_tracks: set, n_recommendations: int) -> List[Dict]:
        """Discover new music using search patterns"""
        print(f"  🔍 Search-based discovery for {n_recommendations} tracks...")
        
        recommendations = []
        seen_ids = set(user_tracks)
        artist_counts = {}  # Track diversity
        
        # Strategy 1: Genre-based search
        top_genres = user_patterns.get('top_genres', [])
        
        for genre in top_genres[:5]:  # Use top 5 genres
            try:
                print(f"    Searching for {genre} tracks...")
                
                # Search for recent tracks in this genre
                search_queries = [
                    f'genre:"{genre}" year:2022-2024',
                    f'genre:"{genre}" year:2020-2022', 
                    f'{genre} indie year:2020-2024'
                ]
                
                for query in search_queries:
                    try:
                        results = sp.search(q=query, type='track', limit=15)
                        
                        for track in results['tracks']['items']:
                            if len(recommendations) >= n_recommendations:
                                break
                                
                            if track['id'] in seen_ids:
                                # Debug logging for skipped tracks
                                if track['name'].lower() == 'is it true':
                                    print(f"      🚫 DEBUG: Skipping 'Is It True' - already in user tracks")
                                continue
                                
                            # Enforce artist diversity
                            main_artist = track['artists'][0]['name'] if track['artists'] else 'Unknown'
                            if artist_counts.get(main_artist, 0) >= 2:  # Max 2 per artist
                                continue
                                
                            # Prefer less popular tracks for discovery
                            if track['popularity'] < 75:
                                # Debug logging for specific track
                                if track['name'].lower() == 'is it true':
                                    print(f"      🚨 DEBUG: Adding 'Is It True' - this should NOT happen if it's saved!")
                                    print(f"         Track ID: {track['id']}")
                                    print(f"         Track in seen_ids: {track['id'] in seen_ids}")
                                    print(f"         Track in user_tracks: {track['id'] in user_tracks}")
                                
                                recommendations.append({
                                    'id': track['id'],
                                    'name': track['name'],
                                    'artist': ', '.join([a['name'] for a in track['artists']]),
                                    'album': track['album']['name'],
                                    'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
                                    'preview_url': track.get('preview_url'),  # May be null due to API restrictions
                                    'external_url': track['external_urls']['spotify'],
                                    'popularity': track.get('popularity', 0),
                                    'discovery_method': f'genre_search_{genre}',
                                    'note': 'Preview may be unavailable due to Spotify API restrictions for new apps'
                                })
                                seen_ids.add(track['id'])
                                artist_counts[main_artist] = artist_counts.get(main_artist, 0) + 1
                                print(f"      Added: {track['name']} by {main_artist}")
                                
                    except Exception as query_error:
                        print(f"      Search error for '{query}': {query_error}")
                        continue
                        
                if len(recommendations) >= n_recommendations:
                    break
                    
            except Exception as genre_error:
                print(f"    Error searching genre '{genre}': {genre_error}")
                continue
        
        # Strategy 2: Artist-style search if we need more
        if len(recommendations) < n_recommendations:
            print(f"    Need more tracks, searching by artist styles...")
            
            favorite_artists = user_patterns.get('favorite_artists', [])
            
            for artist_name in favorite_artists[:3]:
                try:
                    # Search for tracks by similar-sounding artists
                    search_queries = [
                        f'"{artist_name}" style year:2020-2024',
                        f'like "{artist_name}" indie',
                        f'similar to "{artist_name}"'
                    ]
                    
                    for query in search_queries:
                        try:
                            results = sp.search(q=query, type='track', limit=10)
                            
                            for track in results['tracks']['items']:
                                if len(recommendations) >= n_recommendations:
                                    break
                                    
                                if track['id'] in seen_ids:
                                    # Debug logging for skipped tracks
                                    if track['name'].lower() == 'is it true':
                                        print(f"      🚫 DEBUG: Skipping 'Is It True' (artist search) - already in user tracks")
                                    continue
                                    
                                # Don't recommend the actual artist we're searching for
                                track_artists = [a['name'].lower() for a in track['artists']]
                                if artist_name.lower() in track_artists:
                                    continue
                                    
                                main_artist = track['artists'][0]['name'] if track['artists'] else 'Unknown'
                                if artist_counts.get(main_artist, 0) >= 2:
                                    continue
                                    
                                if track['popularity'] < 80:  # Slightly higher for artist-style search
                                    recommendations.append({
                                        'id': track['id'],
                                        'name': track['name'],
                                        'artist': ', '.join([a['name'] for a in track['artists']]),
                                        'album': track['album']['name'],
                                        'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
                                        'preview_url': track.get('preview_url'),
                                        'external_url': track['external_urls']['spotify'],
                                        'popularity': track.get('popularity', 0),
                                        'discovery_method': f'artist_style_{artist_name}',
                                        'note': 'Preview may be unavailable due to Spotify API restrictions for new apps'
                                    })
                                    seen_ids.add(track['id'])
                                    artist_counts[main_artist] = artist_counts.get(main_artist, 0) + 1
                                    print(f"      Added: {track['name']} by {main_artist}")
                                    
                        except Exception as query_error:
                            print(f"      Search error for '{query}': {query_error}")
                            continue
                            
                    if len(recommendations) >= n_recommendations:
                        break
                        
                except Exception as artist_error:
                    print(f"    Error searching artist style '{artist_name}': {artist_error}")
                    continue
        
        print(f"  ✅ Generated {len(recommendations)} advanced recommendations")
        return recommendations
    
    def get_bias_notice(self) -> str:
        """Return information about potential biases in this recommendation approach"""
        return ("Advanced Pattern-Based recommendations may have biases toward: "
                "1) Popular genres and time periods in search results, 2) English-language content, "
                "3) Artists with strong search optimization, 4) Recent releases (2020-2024), "
                "5) User's existing genre preferences. May underrepresent niche or non-Western music.")
