"""
AI Song Recommendation Service (Simplified Version)
Uses Spotify's built-in recommendation API and audio features
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
import spotipy
from app.services.spotify_service import SpotifyService


class RecommendationService:
    def __init__(self):
        self.spotify_service = SpotifyService()
    
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
        
        # Add popularity scores
        tracks_info = []
        for i in range(0, len(track_ids), batch_size):
            batch = track_ids[i:i + batch_size]
            tracks = sp.tracks(batch)
            tracks_info.extend(tracks['tracks'])
        
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
                          top_tracks_limit: int = 100) -> Dict:
        """
        Main recommendation function (Simplified version using Spotify's API)
        
        Args:
            access_token: Spotify access token
            seed_track_ids: Optional list of specific track IDs to base recommendations on
            n_recommendations: Number of songs to recommend
            use_top_tracks: Whether to use user's top tracks as seed
            top_tracks_limit: How many top tracks to analyze
        """
        
        try:
            # Create Spotify client
            sp = self.spotify_service.create_spotify_client(access_token)
            
            # Get seed tracks (either provided or user's top tracks)
            if seed_track_ids:
                seed_tracks = seed_track_ids
            elif use_top_tracks:
                top_tracks = sp.current_user_top_tracks(limit=top_tracks_limit, time_range='medium_term')
                seed_tracks = [track['id'] for track in top_tracks['items']]
            else:
                raise ValueError("Must provide either seed_track_ids or set use_top_tracks=True")
            
            # Get user's playlist tracks to avoid duplicates
            user_playlist_tracks = self.get_user_playlist_tracks(sp)
            
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
                        country='US'
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
                        track_info = sp.track(track_id)
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
            
            # Get full track information for recommendations
            recommended_tracks = []
            for track_features in recommended_track_features:
                track_id = track_features['id']
                if track_id in track_id_to_info:
                    track_info = track_id_to_info[track_id]
                    recommended_tracks.append({
                        "id": track_info['id'],
                        "name": track_info['name'],
                        "artist": ", ".join([artist['name'] for artist in track_info['artists']]),
                        "album": track_info.get('album', {}).get('name', 'Unknown'),
                        "popularity": track_info.get('popularity', 0),
                        "preview_url": track_info.get('preview_url'),
                        "external_url": track_info.get('external_urls', {}).get('spotify', ''),
                        "release_date": track_info.get('album', {}).get('release_date', 'Unknown')
                    })
            
            return {
                "recommendations": recommended_tracks,
                "total": len(recommended_tracks),
                "seed_tracks_count": len(seed_tracks),
                "candidates_analyzed": len(candidate_tracks),
                "method": "Spotify API + Audio Feature Similarity"
            }
            
        except Exception as e:
            return {"error": f"Recommendation error: {str(e)}"}
