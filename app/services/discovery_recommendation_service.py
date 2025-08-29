"""
Discovery Recommendation Service - Genre-based music discovery approach
"""

import spotipy
from typing import List, Dict, Optional
import random
import time
import cProfile
import pstats
from concurrent.futures import ThreadPoolExecutor, as_completed
from .spotify_service import SpotifyService
from .recommendation_utils import RecommendationUtils
from dotenv import load_dotenv
load_dotenv()

class DiscoveryRecommendationService:
    def __init__(self):
        self.spotify_service = SpotifyService()
    
    def get_recommendations(self, access_token: str, n_recommendations: int = 30, user_preferences: Dict = None, generation_seed: int = 0, excluded_track_ids: set = None) -> Dict:
        """
        Get recommendations using a genre-based discovery approach with performance profiling
        """
        start_time = time.time()
        profiler = cProfile.Profile()
        profiler.enable()
        
        try:
            print("=== DISCOVERY RECOMMENDATION SERVICE (WITH PROFILING) ===")
            print(f"Start time: {time.strftime('%H:%M:%S')}")
            print(f"Access token length: {len(access_token) if access_token else 0}")
            if user_preferences:
                print(f"User preferences: {user_preferences}")
            print("[BIAS NOTICE] This model may favor tracks with higher Spotify popularity and artists with more market exposure due to random selection from available tracks. Market and popularity biases may be present.")
            
            if not access_token:
                return {"error": "No access token provided"}
            
            sp = self.spotify_service.create_spotify_client(access_token)
            
            # Test the Spotify client
            try:
                user_info = sp.me()
                print(f"Successfully authenticated user: {user_info.get('display_name', 'Unknown')}")
            except Exception as auth_error:
                print(f"Authentication failed: {auth_error}")
                return {"error": f"Invalid or expired access token: {str(auth_error)}"}
            
            # Get user's existing tracks and analyze patterns using shared utilities
            print("📊 Getting user's music collection for analysis...")
            user_tracks, artist_track_count = RecommendationUtils.get_user_tracks_simple(sp, max_tracks=2000)
            
            # Add excluded track IDs to user tracks to avoid recommending them
            if excluded_track_ids:
                print(f"  🚫 Adding {len(excluded_track_ids)} excluded tracks to filter")
                user_tracks.update(excluded_track_ids)
            
            # Get user's top artists and genres using shared utility
            print("🎯 Analyzing user's music preferences...")
            user_patterns = RecommendationUtils.analyze_user_patterns(sp)
            
            # Add variation for subsequent generations
            if generation_seed > 0:
                print(f"  🎲 Applying variation for generation #{generation_seed + 1}...")
                user_patterns = RecommendationUtils.apply_pattern_variation(user_patterns, generation_seed)
            
            top_artists = user_patterns.get('favorite_artists', [])
            top_genres = user_patterns.get('top_genres', [])
            
            print(f"   🎸 Top {len(top_artists)} artists identified")
            print(f"   🎵 Top {len(top_genres)} genres: {top_genres[:5]}")
            
            # Generate recommendations using search patterns
            print(f"🔍 Generating {n_recommendations} discovery recommendations...")
            recommendations = []
            seen_track_ids = set(user_tracks)
            seen_artist_names = set()
            
            # Use shared search-based discovery with user patterns
            recommendations = RecommendationUtils.search_based_discovery(
                sp, user_patterns, user_tracks, n_recommendations, user_preferences
            )
            
            # Performance profiling
            profiler.disable()
            stats = pstats.Stats(profiler)
            stats.sort_stats('cumulative')
            
            execution_time = time.time() - start_time
            print(f"✅ Generated {len(recommendations)} recommendations in {execution_time:.2f} seconds")
            
            return {
                "recommendations": recommendations,
                "execution_time_seconds": execution_time,
                "algorithm": "Discovery Genre-Based Search",
                "total_candidates_analyzed": len(seen_track_ids),
                "user_profile": {
                    "saved_tracks_count": len(user_tracks),
                    "top_artists_count": len(top_artists),
                    "top_genres": top_genres[:10],
                    "preferences": {
                        "diversity_focus": "High artist diversity",
                        "popularity_filter": "Filtered out tracks with >80 popularity for discovery"
                    }
                }
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"❌ Error in discovery recommendations: {str(e)}")
            return {
                "error": str(e),
                "execution_time_seconds": execution_time,
                "recommendations": []
            }
    