import numpy as np
import pandas as pd
import spotipy
from typing import List, Dict, Optional
from .spotify_service import SpotifyService
from .spotify_service import SpotifyService

class MLRecommendationService:
    def __init__(self):
        self.spotify_service = SpotifyService()
        self.user_profile = None
        self.feature_weights = {
            'danceability': 1.0,
            'energy': 1.0,
            'valence': 1.0,
            'acousticness': 0.8,
            'instrumentalness': 0.7,
            'speechiness': 0.6,
            'tempo': 0.5,
            'loudness': 0.4,
            'liveness': 0.3
        }
        
    def extract_audio_features(self, tracks_data: List[Dict]) -> pd.DataFrame:
        """Extract and normalize audio features from track data"""
        features = []
        for track in tracks_data:
            if track and track.get('id'):
                feature_dict = {
                    'id': track['id'],
                    'danceability': track.get('danceability', 0),
                    'energy': track.get('energy', 0),
                    'valence': track.get('valence', 0),
                    'acousticness': track.get('acousticness', 0),
                    'instrumentalness': track.get('instrumentalness', 0),
                    'speechiness': track.get('speechiness', 0),
                    'tempo': track.get('tempo', 120) / 200.0,  # Normalize tempo
                    'loudness': (track.get('loudness', -10) + 60) / 60.0,  # Normalize loudness
                    'liveness': track.get('liveness', 0),
                    'popularity': track.get('popularity', 50) / 100.0  # Normalize popularity
                }
                features.append(feature_dict)
        
        return pd.DataFrame(features)
    
    def build_user_profile(self, sp: spotipy.Spotify, user_controls: Optional[Dict] = None) -> Dict:
        """Build a detailed user taste profile from their listening history"""
        print("Building user taste profile...")
        
        # Get user's top tracks (different time ranges for comprehensive profile)
        short_term = sp.current_user_top_tracks(limit=50, time_range='short_term')['items']
        medium_term = sp.current_user_top_tracks(limit=50, time_range='medium_term')['items']
        long_term = sp.current_user_top_tracks(limit=50, time_range='long_term')['items']
        
        # Get recently played tracks
        recent = sp.current_user_recently_played(limit=50)['items']
        recent_tracks = [item['track'] for item in recent]
        
        # Combine all tracks with weights (more recent = higher weight)
        all_tracks = []
        weights = []
        
        # Add tracks with time-based weights
        for track in short_term:
            all_tracks.append(track)
            weights.append(3.0)  # Highest weight for current favorites
            
        for track in medium_term:
            if track['id'] not in [t['id'] for t in all_tracks]:
                all_tracks.append(track)
                weights.append(2.0)
                
        for track in long_term:
            if track['id'] not in [t['id'] for t in all_tracks]:
                all_tracks.append(track)
                weights.append(1.5)
                
        for track in recent_tracks:
            if track['id'] not in [t['id'] for t in all_tracks]:
                all_tracks.append(track)
                weights.append(1.0)
        
        # Get audio features for all tracks
        track_ids = [track['id'] for track in all_tracks]
        audio_features = sp.audio_features(track_ids)
        
        # Combine track info with audio features
        enhanced_tracks = []
        for i, track in enumerate(all_tracks):
            if audio_features[i]:
                combined = {**track, **audio_features[i]}
                enhanced_tracks.append(combined)
        
        # Extract features and calculate weighted profile
        df = self.extract_audio_features(enhanced_tracks)
        
        if df.empty:
            raise ValueError("No audio features found for user tracks")
        
        # Calculate weighted average of user's preferences
        feature_cols = ['danceability', 'energy', 'valence', 'acousticness', 
                       'instrumentalness', 'speechiness', 'tempo', 'loudness', 'liveness']
        
        user_profile = {}
        valid_weights = weights[:len(df)]  # Match weights to actual data
        
        for feature in feature_cols:
            if feature in df.columns:
                weighted_avg = np.average(df[feature], weights=valid_weights)
                user_profile[feature] = weighted_avg
        
        # Add user preference controls if provided
        if user_controls:
            for control, value in user_controls.items():
                if control in user_profile:
                    # Blend user control with learned preference (70% learned, 30% control)
                    user_profile[control] = 0.7 * user_profile[control] + 0.3 * (value / 100.0)
        
        # Calculate diversity preferences (how varied the user's taste is)
        user_profile['diversity'] = np.std([df[col] for col in feature_cols if col in df.columns])
        
        self.user_profile = user_profile
        print(f"User profile built with {len(enhanced_tracks)} tracks")
        return user_profile
    
    def get_candidate_tracks(self, sp: spotipy.Spotify, user_tracks: List[str], 
                           max_candidates: int = 500) -> List[Dict]:
        """Get candidate tracks from multiple sources efficiently"""
        candidates = []
        seen_ids = set(user_tracks)
        
        # Get user's top artists and their related artists
        top_artists = sp.current_user_top_artists(limit=20)['items']
        artist_pool = []
        
        for artist in top_artists:
            artist_pool.append(artist['id'])
            # Get related artists (but limit to avoid explosion)
            try:
                related = sp.artist_related_artists(artist['id'])
                for rel_artist in related['artists'][:2]:  # Only top 2 related
                    artist_pool.append(rel_artist['id'])
            except:
                continue
        
        # Get tracks from artist pool (more targeted)
        for artist_id in artist_pool[:15]:  # Limit artists to process
            try:
                # Get artist's top tracks
                top_tracks = sp.artist_top_tracks(artist_id)
                for track in top_tracks['tracks']:
                    if track['id'] not in seen_ids and len(candidates) < max_candidates:
                        candidates.append(track)
                        seen_ids.add(track['id'])
                
                # Get some album tracks (but limit)
                albums = sp.artist_albums(artist_id, limit=2, album_type='album')
                for album in albums['items']:
                    tracks = sp.album_tracks(album['id'], limit=5)
                    for track in tracks['items']:
                        if track['id'] not in seen_ids and len(candidates) < max_candidates:
                            # Get full track info
                            full_track = sp.track(track['id'])
                            candidates.append(full_track)
                            seen_ids.add(track['id'])
                            
            except Exception as e:
                continue
                
            if len(candidates) >= max_candidates:
                break
        
        print(f"Collected {len(candidates)} candidate tracks")
        return candidates
    
    def calculate_recommendation_score(self, candidate_features: Dict, 
                                     user_profile: Dict, user_controls: Dict) -> float:
        """Calculate how well a track matches user preferences"""
        score = 0.0
        total_weight = 0.0
        
        # Apply user control preferences
        popularity_preference = user_controls.get('popularity', 50) / 100.0
        energy_preference = user_controls.get('energy', 50) / 100.0
        instrumentalness_preference = user_controls.get('instrumentalness', 50) / 100.0
        
        # Calculate feature-based similarity
        for feature, weight in self.feature_weights.items():
            if feature in candidate_features and feature in user_profile:
                candidate_val = candidate_features[feature]
                user_pref = user_profile[feature]
                
                # Apply user controls
                if feature == 'energy':
                    user_pref = 0.6 * user_pref + 0.4 * energy_preference
                elif feature == 'instrumentalness':
                    user_pref = 0.6 * user_pref + 0.4 * instrumentalness_preference
                
                # Calculate similarity (1 - absolute difference)
                similarity = 1 - abs(candidate_val - user_pref)
                score += similarity * weight
                total_weight += weight
        
        # Popularity adjustment
        if 'popularity' in candidate_features:
            pop_score = candidate_features['popularity']
            # Apply popularity preference
            pop_diff = abs(pop_score - popularity_preference)
            pop_penalty = 1 - pop_diff
            score = score * (0.8 + 0.2 * pop_penalty)  # 20% popularity influence
        
        # Diversity bonus (prefer tracks that add variety)
        diversity_bonus = user_profile.get('diversity', 0.1)
        if diversity_bonus > 0.2:  # User likes variety
            score *= 1.1
        
        return score / total_weight if total_weight > 0 else 0
    
    def get_recommendations(self, access_token: str, 
                          n_recommendations: int = 30,
                          user_controls: Optional[Dict] = None) -> Dict:
        """
        Get personalized recommendations using ML approach
        
        user_controls: {
            'popularity': 0-100,  # 0=underground, 100=mainstream
            'energy': 0-100,      # 0=chill, 100=energetic  
            'instrumentalness': 0-100  # 0=vocal, 100=instrumental
        }
        """
        try:
            print("=== ML RECOMMENDATION SERVICE ===")
            
            if not user_controls:
                user_controls = {'popularity': 30, 'energy': 50, 'instrumentalness': 30}
            
            sp = self.spotify_service.create_spotify_client(access_token)
            
            # Build user profile
            user_profile = self.build_user_profile(sp, user_controls)
            
            # Get user's existing tracks to avoid duplicates
            user_tracks = set()
            user_playlists = sp.current_user_playlists(limit=50)
            for playlist in user_playlists['items']:
                if playlist['owner']['id'] == sp.me()['id']:
                    tracks = sp.playlist_tracks(playlist['id'])
                    for item in tracks['items']:
                        if item['track'] and item['track']['id']:
                            user_tracks.add(item['track']['id'])
            
            # Get candidate tracks efficiently
            candidates = self.get_candidate_tracks(sp, list(user_tracks), max_candidates=300)
            
            if not candidates:
                return {"error": "No candidate tracks found"}
            
            # Get audio features for candidates
            candidate_ids = [track['id'] for track in candidates]
            audio_features = sp.audio_features(candidate_ids)
            
            # Score each candidate
            scored_tracks = []
            for i, track in enumerate(candidates):
                if audio_features[i]:
                    # Combine track info with audio features
                    enhanced_track = {**track, **audio_features[i]}
                    features_dict = self.extract_audio_features([enhanced_track]).iloc[0].to_dict()
                    
                    score = self.calculate_recommendation_score(features_dict, user_profile, user_controls)
                    scored_tracks.append((track, score))
            
            # Sort by score and return top recommendations
            scored_tracks.sort(key=lambda x: x[1], reverse=True)
            top_tracks = [track for track, score in scored_tracks[:n_recommendations]]
            
            # Format response
            recommendations = []
            for track in top_tracks:
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
                recommendations.append(rec)
            
            print(f"Generated {len(recommendations)} ML-based recommendations")
            return {
                "recommendations": recommendations,
                "user_profile": user_profile,
                "controls_used": user_controls
            }
            
        except Exception as e:
            print(f"Error in ML recommendations: {e}")
            return {"error": str(e)}
