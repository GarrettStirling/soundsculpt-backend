from dotenv import load_dotenv
load_dotenv()
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

class DiscoveryRecommendationService:
    def __init__(self):
        self.spotify_service = SpotifyService()
    
    def get_recommendations(self, access_token: str, n_recommendations: int = 30) -> Dict:
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
            
            # Get user's existing tracks to avoid duplicates and track artist frequency
            user_tracks = set()
            artist_track_count = {}  # Track how many songs user has per artist
            
            print("📊 Getting user's music collection for analysis...")
            try:
                # Get saved tracks more efficiently with larger batches
                offset = 0
                batch_size = 50
                total_processed = 0
                
                while total_processed < 2000:  # Limit to prevent excessive processing
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
            
            # Get user's top artists and genres  
            print("🎯 Analyzing user's music preferences...")
            top_artists = []
            top_genres = []
            
            try:
                # Get top artists
                top_artists_data = sp.current_user_top_artists(limit=50, time_range='medium_term')
                top_artists = [artist['name'] for artist in top_artists_data['items']]
                
                # Extract genres from top artists
                genre_count = {}
                for artist in top_artists_data['items']:
                    for genre in artist.get('genres', []):
                        genre_count[genre] = genre_count.get(genre, 0) + 1
                
                # Sort genres by frequency
                top_genres = [genre for genre, count in sorted(genre_count.items(), key=lambda x: x[1], reverse=True)]
                
                print(f"   🎸 Top {len(top_artists)} artists identified")
                print(f"   🎵 Top {len(top_genres)} genres: {top_genres[:5]}")
                
            except Exception as prefs_error:
                print(f"⚠️ Error getting user preferences: {prefs_error}")
                top_artists = []
                top_genres = []
            
            # Generate recommendations using search patterns
            print(f"🔍 Generating {n_recommendations} discovery recommendations...")
            recommendations = []
            seen_track_ids = set(user_tracks)
            seen_artist_names = set()
            
            # Search strategies
            search_strategies = []
            
            # Strategy 1: Use user's top genres
            for genre in top_genres[:10]:
                search_strategies.extend([
                    f'genre:"{genre}" year:2020-2024',
                    f'genre:"{genre}" year:2018-2022',
                    f'{genre} indie discover'
                ])
            
            # Strategy 2: Discovery searches
            search_strategies.extend([
                'indie rock discover year:2020-2024',
                'electronic discover year:2021-2024', 
                'alternative discover year:2019-2024',
                'indie pop discover year:2020-2024'
            ])
            
            # Strategy 3: Based on user's artists but find similar artists
            for artist in top_artists[:5]:
                search_strategies.extend([
                    f'similar to "{artist}" discover',
                    f'like "{artist}" indie'
                ])
            
            print(f"   🎯 Using {len(search_strategies)} search strategies")
            
            # Execute searches
            for i, query in enumerate(search_strategies):
                if len(recommendations) >= n_recommendations:
                    break
                
                try:
                    print(f"   Search {i+1}/{len(search_strategies)}: {query[:50]}...")
                    results = sp.search(q=query, type='track', limit=15)
                    
                    for track in results['tracks']['items']:
                        if len(recommendations) >= n_recommendations:
                            break
                        
                        # Skip if already seen
                        if track['id'] in seen_track_ids:
                            continue
                        
                        # Skip if we already have too many from this artist
                        artist_name = track['artists'][0]['name'] if track['artists'] else 'Unknown'
                        if artist_name in seen_artist_names and len([r for r in recommendations if r['artist'] == artist_name]) >= 2:
                            continue
                        
                        # Filter out overly popular tracks for discovery
                        if track['popularity'] > 80:
                            continue
                        
                        # Add the track
                        recommendation = {
                            'id': track['id'],
                            'name': track['name'],
                            'artist': ', '.join([a['name'] for a in track['artists']]),
                            'album': track['album']['name'],
                            'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
                            'preview_url': track.get('preview_url'),
                            'external_url': track['external_urls']['spotify'],
                            'popularity': track.get('popularity', 0),
                            'discovery_method': f'search_pattern_{i+1}',
                            'note': 'Preview may be unavailable due to Spotify API restrictions for new apps'
                        }
                        
                        recommendations.append(recommendation)
                        seen_track_ids.add(track['id'])
                        seen_artist_names.add(artist_name)
                        
                        print(f"      ✅ Added: {track['name']} by {artist_name} (pop: {track.get('popularity', 0)})")
                        
                except Exception as search_error:
                    print(f"   ⚠️ Search error for '{query}': {search_error}")
                    continue
            
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
    
    def get_bias_notice(self) -> str:
        """Return information about potential biases in this recommendation approach"""
        return ("Discovery Genre-Based recommendations may have biases toward: "
                "1) Popular genres on Spotify, 2) English-language tracks, "
                "3) Artists with good SEO/searchability, 4) Tracks with moderate popularity (20-80 range). "
                "Less popular or niche artists may be underrepresented.")
