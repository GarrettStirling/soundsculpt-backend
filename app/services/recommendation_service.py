"""
AI Song Recommendation Service (Simplified Version)
Uses Spotify's built-in recommendation API and audio features
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
import spotipy
from app.services.spotify_service import SpotifyService
# from app.services.youtube_service import YouTubeService  # Temporarily disabled


class RecommendationService:
    def __init__(self):
        self.spotify_service = SpotifyService()
        # self.youtube_service = YouTubeService()  # Temporarily disabled
    
    def get_audio_features(self, sp: spotipy.Spotify, track_ids: List[str]) -> pd.DataFrame:
        """Get audio features for a list of tracks"""
        # Get audio features in batches (Spotify API limit is 100)
        all_features = []
        batch_size = 100
        
        for i in range(0, len(track_ids), batch_size):
            batch = track_ids[i:i + batch_size]
            features = sp.audio_features(batch)
            all_features.extend([f for f in features if f is not None])
        
        # Convert to DataFrame
        df = pd.DataFrame(all_features)
        
        # Add popularity scores - try without market restriction first
        tracks_info = []
        for i in range(0, len(track_ids), batch_size):
            batch = track_ids[i:i + batch_size]
            try:
                # Try without market first (global access)
                tracks = sp.tracks(batch)
                tracks_info.extend(tracks['tracks'])
            except Exception as e:
                print(f"Error fetching tracks without market: {e}")
                try:
                    # Fallback to US market
                    tracks = sp.tracks(batch, market='US')
                    tracks_info.extend(tracks['tracks'])
                except Exception as e2:
                    print(f"Error fetching tracks with US market: {e2}")
                    continue
        
        popularity_map = {track['id']: track['popularity'] for track in tracks_info}
        df['popularity'] = df['id'].map(popularity_map)
        
        return df
    
    def get_user_playlist_tracks(self, sp: spotipy.Spotify) -> set:
        """Get all track IDs from user's playlists to avoid recommending duplicates"""
        playlist_tracks = set()
        
        # Get user's playlists
        playlists = sp.current_user_playlists(limit=50)
        
        for playlist in playlists['items']:
            if playlist['owner']['id'] == sp.me()['id']:  # Only user's own playlists
                # Get tracks from playlist
                tracks = sp.playlist_tracks(playlist['id'])
                for item in tracks['items']:
                    if item['track'] and item['track']['id']:
                        playlist_tracks.add(item['track']['id'])
        
        return playlist_tracks
    
    def calculate_similarity(self, track1_features: dict, track2_features: dict) -> float:
        """Calculate similarity between two tracks using audio features"""
        features_to_compare = ['danceability', 'energy', 'valence', 'acousticness', 'speechiness', 'tempo']
        
        # Weights for different features
        weights = {
            'danceability': 1.0,
            'energy': 1.0,
            'valence': 1.0,
            'acousticness': 0.8,
            'speechiness': 0.6,
            'tempo': 0.5
        }
        
        similarity_score = 0
        total_weight = 0
        
        for feature in features_to_compare:
            if feature in track1_features and feature in track2_features:
                # Normalize tempo to 0-1 scale
                if feature == 'tempo':
                    val1 = min(track1_features[feature] / 200.0, 1.0)
                    val2 = min(track2_features[feature] / 200.0, 1.0)
                else:
                    val1 = track1_features[feature]
                    val2 = track2_features[feature]
                
                # Calculate normalized difference (0 = identical, 1 = completely different)
                difference = abs(val1 - val2)
                similarity = 1 - difference
                
                weight = weights.get(feature, 1.0)
                similarity_score += similarity * weight
                total_weight += weight
        
        return similarity_score / total_weight if total_weight > 0 else 0
    
    def find_similar_tracks_simple(self, 
                                 seed_features: List[dict], 
                                 candidate_tracks: List[dict],
                                 n_recommendations: int = 30) -> List[dict]:
        """Find tracks similar to user's taste using simple similarity calculation"""
        
        # Calculate average features of seed tracks
        avg_features = {}
        feature_names = ['danceability', 'energy', 'valence', 'acousticness', 'speechiness', 'tempo']
        
        for feature in feature_names:
            values = [track.get(feature, 0) for track in seed_features if track.get(feature) is not None]
            avg_features[feature] = sum(values) / len(values) if values else 0
        
        # Calculate similarity for each candidate track
        track_similarities = []
        for track in candidate_tracks:
            similarity = self.calculate_similarity(avg_features, track)
            track_similarities.append((track, similarity))
        
        # Sort by similarity and return top recommendations
        track_similarities.sort(key=lambda x: x[1], reverse=True)
        return [track for track, similarity in track_similarities[:n_recommendations]]
    
    def get_recommendations(self, 
                          access_token: str,
                          seed_track_ids: Optional[List[str]] = None,
                          n_recommendations: int = 30,
                          use_top_tracks: bool = True,
                          top_tracks_limit: int = 50,
                          custom_track_ids: Optional[List[str]] = None) -> Dict:
        """
        IMPROVED Fast recommendation function focused on personalization over popularity
        
        Args:
            access_token: Spotify access token
            seed_track_ids: Optional list of specific track IDs to base recommendations on
            n_recommendations: Number of songs to recommend
            use_top_tracks: Whether to use user's top tracks as seed
            top_tracks_limit: How many top tracks to analyze (reduced for speed)
            custom_track_ids: Custom track IDs for playlist-based recommendations
        """
        
        try:
            print("=== IMPROVED RECOMMENDATION SERVICE ===")
            print(f"Number of recommendations requested: {n_recommendations}")
            
            # Create Spotify client
            sp = self.spotify_service.create_spotify_client(access_token)
            
            # Get seed tracks - prioritize recent and top tracks
            if custom_track_ids:
                seed_tracks = custom_track_ids[:10]  # Limit for speed
            elif seed_track_ids:
                seed_tracks = seed_track_ids[:10]
            elif use_top_tracks:
                # Get both recent and top tracks for better personalization
                print("Getting user's listening history...")
                short_term = sp.current_user_top_tracks(limit=20, time_range='short_term')['items']
                medium_term = sp.current_user_top_tracks(limit=15, time_range='medium_term')['items']
                recent = sp.current_user_recently_played(limit=15)['items']
                
                # Combine with weights (recent = more important)
                seed_tracks = []
                for track in short_term:
                    seed_tracks.append(track['id'])
                for track in medium_term:
                    if track['id'] not in seed_tracks:
                        seed_tracks.append(track['id'])
                for item in recent:
                    if item['track']['id'] not in seed_tracks:
                        seed_tracks.append(item['track']['id'])
                
                seed_tracks = seed_tracks[:15]  # Limit for speed
            else:
                raise ValueError("Must provide seed tracks")
            
            print(f"Using {len(seed_tracks)} seed tracks")
            
            # Get user's saved tracks to avoid duplicates
            user_saved_tracks = set()
            try:
                saved_tracks = sp.current_user_saved_tracks(limit=50)
                for item in saved_tracks['items']:
                    if item['track']:
                        user_saved_tracks.add(item['track']['id'])
            except:
                pass
            
            # FASTER approach: Use Spotify's recommendation API efficiently
            recommendations = []
            seen_ids = set(seed_tracks + list(user_saved_tracks))
            
            # Get recommendations in batches from different seed combinations
            batch_size = 5
            for i in range(0, min(len(seed_tracks), 15), batch_size):
                batch_seeds = seed_tracks[i:i + batch_size]
                try:
                    # Use more personalized parameters
                    recs = sp.recommendations(
                        seed_tracks=batch_seeds,
                        limit=min(50, n_recommendations * 2),  # Get extra for filtering
                        min_popularity=5,    # LOWER popularity = more personalized, less mainstream
                        max_popularity=70,   # Avoid super mainstream hits
                        target_energy=0.6,   # Slight preference for energetic
                        target_valence=0.5   # Balanced mood
                    )
                    
                    for track in recs['tracks']:
                        if (track['id'] not in seen_ids and 
                            len(recommendations) < n_recommendations * 2):
                            recommendations.append(track)
                            seen_ids.add(track['id'])
                            
                except Exception as e:
                    print(f"Batch {i} failed: {e}")
                    continue
                
                if len(recommendations) >= n_recommendations * 2:
                    break
            
            # If we need more, get from related artists (but limit to avoid slowness)
            if len(recommendations) < n_recommendations * 1.5:
                print("Getting additional tracks from related artists...")
                try:
                    # Get top artists from seed tracks
                    artist_ids = set()
                    for track_id in seed_tracks[:8]:  # Limit for speed
                        track_info = sp.track(track_id)
                        for artist in track_info['artists'][:2]:  # Max 2 artists per track
                            artist_ids.add(artist['id'])
                    
                    # Get tracks from related artists
                    for artist_id in list(artist_ids)[:5]:  # Limit to 5 artists
                        try:
                            related = sp.artist_related_artists(artist_id)
                            for related_artist in related['artists'][:2]:  # Top 2 related
                                top_tracks = sp.artist_top_tracks(related_artist['id'])
                                for track in top_tracks['tracks'][:3]:  # Top 3 tracks
                                    if (track['id'] not in seen_ids and 
                                        len(recommendations) < n_recommendations * 2):
                                        recommendations.append(track)
                                        seen_ids.add(track['id'])
                        except:
                            continue
                            
                        if len(recommendations) >= n_recommendations * 2:
                            break
                except Exception as e:
                    print(f"Related artists failed: {e}")
            
            if not recommendations:
                return {"error": "No suitable recommendations found"}
            
            # Sort by a combination of factors for personalization
            print(f"Ranking {len(recommendations)} candidates...")
            scored_recommendations = []
            
            for track in recommendations:
                score = 0
                
                # Lower popularity = higher score (more personalized)
                popularity = track.get('popularity', 50)
                popularity_score = (100 - popularity) / 100.0  # Invert popularity
                score += popularity_score * 0.4
                
                # Artist diversity bonus
                track_artists = [artist['id'] for artist in track['artists']]
                if not any(artist_id in [a['id'] for rec in scored_recommendations for a in rec[0]['artists']] 
                          for artist_id in track_artists):
                    score += 0.3  # Diversity bonus
                
                # Random factor for discovery
                import random
                score += random.random() * 0.3
                
                scored_recommendations.append((track, score))
            
            # Sort by score and take top recommendations
            scored_recommendations.sort(key=lambda x: x[1], reverse=True)
            final_recommendations = [track for track, score in scored_recommendations[:n_recommendations]]
            
            # Format response
            formatted_recommendations = []
            for track in final_recommendations:
                rec = {
                    'id': track['id'],
                    'name': track['name'],
                    'artist': ', '.join([artist['name'] for artist in track['artists']]),
                    'album': track['album']['name'],
                    'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'preview_url': track.get('preview_url'),
                    'external_url': track['external_urls']['spotify'],
                    'popularity': track.get('popularity', 0)
                }
                formatted_recommendations.append(rec)
            
            print(f"Generated {len(formatted_recommendations)} personalized recommendations")
            return {
                "recommendations": formatted_recommendations,
                "seed_tracks_used": len(seed_tracks),
                "total_candidates": len(recommendations),
                "algorithm": "improved_personalized"
            }
            
        except Exception as e:
            print(f"Recommendation error: {e}")
            return {"error": str(e)}
            
            # Get audio features for seed tracks (for taste analysis)
            seed_features_df = self.get_audio_features(sp, seed_tracks)
            seed_features = seed_features_df.to_dict('records')
            
            # Get recommendations from Spotify based on seed tracks
            recommendations = []
            
            # Get recommendations in batches (max 5 seed tracks per request)
            batch_size = 5
            for i in range(0, min(len(seed_tracks), 20), batch_size):  # Use max 20 seeds
                batch_seeds = seed_tracks[i:i + batch_size]
                try:
                    recs = sp.recommendations(
                        seed_tracks=batch_seeds,
                        limit=50,  # Get more than needed for filtering
                        min_popularity=30,  # Prefer popular tracks (more likely to have previews)
                        # Remove country restriction for global recommendations
                    )
                    recommendations.extend(recs['tracks'])
                except Exception as e:
                    # Skip if error with this batch
                    continue
            
            # Remove duplicates and filter out tracks already in playlists
            candidate_tracks = []
            seen_ids = set()
            
            for track in recommendations:
                track_id = track['id']
                if (track_id not in seen_ids and 
                    track_id not in user_playlist_tracks and 
                    track_id not in seed_tracks):
                    candidate_tracks.append(track)
                    seen_ids.add(track_id)
            
            # If we don't have enough candidates, get more using related artists
            if len(candidate_tracks) < n_recommendations * 2:
                # Use related artists to find more tracks
                artist_ids = set()
                for track_id in seed_tracks[:10]:  # Use top 10 seed tracks
                    try:
                        track_info = sp.track(track_id)  # Remove market restriction
                        for artist in track_info['artists']:
                            artist_ids.add(artist['id'])
                    except:
                        continue
                
                for artist_id in list(artist_ids)[:5]:  # Limit to 5 artists
                    try:
                        related = sp.artist_related_artists(artist_id)
                        for related_artist in related['artists'][:3]:  # Top 3 related artists
                            albums = sp.artist_albums(related_artist['id'], limit=2)
                            for album in albums['items']:
                                tracks = sp.album_tracks(album['id'], limit=10)
                                for track in tracks['items']:
                                    if (track['id'] not in seen_ids and 
                                        track['id'] not in user_playlist_tracks and 
                                        track['id'] not in seed_tracks):
                                        candidate_tracks.append(track)
                                        seen_ids.add(track['id'])
                    except:
                        continue
            
            # Get audio features for candidate tracks
            candidate_ids = [track['id'] for track in candidate_tracks]
            if not candidate_ids:
                return {"error": "No suitable candidate tracks found"}
            
            candidate_features_df = self.get_audio_features(sp, candidate_ids)
            candidate_features = candidate_features_df.to_dict('records')
            
            # Create mapping from ID to track info
            track_id_to_info = {track['id']: track for track in candidate_tracks}
            
            # Find most similar tracks using our simple similarity function
            recommended_track_features = self.find_similar_tracks_simple(
                seed_features, 
                candidate_features, 
                n_recommendations
            )
            
            # Get full track information for recommendations with preview URLs
            # Use Client Credentials for fetching track data (including preview URLs)
            print("Creating Client Credentials client for preview URLs...")
            try:
                sp_client_creds = self.spotify_service.create_client_credentials_client()
                print("Client Credentials client created successfully")
            except Exception as e:
                print(f"Error creating Client Credentials client: {e}")
                sp_client_creds = None
            
            recommended_tracks = []
            for track_features in recommended_track_features:
                track_id = track_features['id']
                if track_id in track_id_to_info:
                    track_info = track_id_to_info[track_id]
                    
                    # Fetch detailed track info with Client Credentials to get preview URL
                    preview_url = None
                    if sp_client_creds:
                        try:
                            print(f"Fetching detailed track info for: {track_info['name']}")
                            detailed_track = sp_client_creds.track(track_id)
                            preview_url = detailed_track.get('preview_url')
                            print(f"Got preview URL: {preview_url}")
                        except Exception as e:
                            print(f"Error fetching detailed track info for {track_id}: {e}")
                            preview_url = track_info.get('preview_url')
                    else:
                        print("No Client Credentials client available, using original preview URL")
                        preview_url = track_info.get('preview_url')
                    
                    # YouTube functionality temporarily disabled
                    # youtube_video_id = None
                    # if not preview_url:
                    #     youtube_video_id = self.youtube_service.search_track_preview(
                    #         track_info['name'], 
                    #         ", ".join([artist['name'] for artist in track_info['artists']])
                    #     )
                    
                    recommended_tracks.append({
                        "id": track_info['id'],
                        "name": track_info['name'],
                        "artist": ", ".join([artist['name'] for artist in track_info['artists']]),
                        "album": track_info.get('album', {}).get('name', 'Unknown'),
                        "popularity": track_info.get('popularity', 0),
                        "preview_url": preview_url,
                        # "youtube_id": youtube_video_id,
                        # "youtube_url": self.youtube_service.get_watch_url(youtube_video_id) if youtube_video_id else None,
                        "external_url": track_info.get('external_urls', {}).get('spotify', ''),
                        "album_cover": track_info.get('album', {}).get('images', [{}])[0].get('url') if track_info.get('album', {}).get('images') else None,
                        "release_date": track_info.get('album', {}).get('release_date', 'Unknown')
                    })
                    
                    # Debug logging for preview URLs - more detailed
                    preview_status = "HAS PREVIEW" if preview_url else "NO PREVIEW"
                    print(f"Track: {track_info['name']} by {', '.join([artist['name'] for artist in track_info['artists']])}")
                    print(f"  - Preview Status: {preview_status}")
                    print(f"  - Preview URL: {preview_url}")
                    print(f"  - Market: {track_info.get('available_markets', ['N/A'])[:3]}...")  # Show first 3 markets
                    print(f"  - Album: {track_info.get('album', {}).get('name', 'Unknown')}")
                    print("---")
            
            # Sort to prioritize tracks with preview URLs
            recommended_tracks.sort(key=lambda x: (x['preview_url'] is not None, x['popularity']), reverse=True)
            
            return {
                "recommendations": recommended_tracks,
                "total": len(recommended_tracks),
                "seed_tracks_count": len(seed_tracks),
                "candidates_analyzed": len(candidate_tracks),
                "method": "Spotify API + Audio Feature Similarity"
            }
            
        except Exception as e:
            return {"error": f"Recommendation error: {str(e)}"}
