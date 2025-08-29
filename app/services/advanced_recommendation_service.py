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
from .recommendation_utils import RecommendationUtils
import cProfile
import pstats
from io import StringIO

class AdvancedRecommendationService:
    def __init__(self):
        self.spotify_service = SpotifyService()
        
    def get_recommendations(self, access_token: str, n_recommendations: int = 30, user_preferences: Dict = None, generation_seed: int = 0, excluded_track_ids: set = None) -> Dict:
        """
        Get recommendations using advanced pattern-based discovery (audio features deprecated Nov 2024)
        """
        start_time = time.time()
        
        try:
            print("=== ADVANCED PATTERN-BASED RECOMMENDATION SERVICE ===")
            print("[DEPRECATED NOTICE] Spotify deprecated audio features, related artists, and recommendations APIs on Nov 27, 2024")
            print("[NEW APPROACH] Using advanced search patterns and user behavior analysis")
            
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
            user_patterns = RecommendationUtils.analyze_user_patterns(sp)
            
            # Add variation for subsequent generations
            if generation_seed > 0:
                print(f"  🎲 Applying variation for generation #{generation_seed + 1}...")
                user_patterns = RecommendationUtils.apply_pattern_variation(user_patterns, generation_seed)
                
            print(f"  ⏱️ Step 1 completed in {time.time() - step_time:.2f}s")
            
            step_time = time.time()
            print("STEP 2: Getting your existing tracks for filtering...")
            user_tracks = RecommendationUtils.get_user_tracks_smart(sp)
            
            # Add excluded track IDs to user tracks to avoid recommending them
            if excluded_track_ids:
                print(f"  🚫 Adding {len(excluded_track_ids)} excluded tracks to filter")
                user_tracks.update(excluded_track_ids)
                
            print(f"  ⏱️ Step 2 completed in {time.time() - step_time:.2f}s")
            
            step_time = time.time()
            print("STEP 3: Discovering new music using pattern analysis...")
            recommendations = RecommendationUtils.search_based_discovery(sp, user_patterns, user_tracks, n_recommendations, user_preferences)
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
