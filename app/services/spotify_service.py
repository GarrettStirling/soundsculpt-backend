import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
from typing import List, Dict, Optional
import pandas as pd
from dotenv import load_dotenv

load_dotenv()  # This will load variables from .env if not already loaded

class SpotifyService:
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

        print("SpotifyService initialized with client ID:", self.client_id)

        # Define the scope of permissions we need
        self.scope = "user-read-recently-played user-library-read playlist-read-private user-top-read playlist-read-collaborative user-read-playback-state user-read-currently-playing"
        
        # Initialize Spotify OAuth
        self.sp_oauth = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope
        )
    
    def get_auth_url(self) -> str:
        """Get the authorization URL for Spotify login"""
        return self.sp_oauth.get_authorize_url()
    
    def get_access_token(self, code: str) -> Optional[Dict]:
        """Exchange authorization code for access token"""
        try:
            token_info = self.sp_oauth.get_access_token(code)
            return token_info
        except Exception as e:
            print(f"Error getting access token: {e}")
            return None
    
    def create_spotify_client(self, access_token: str) -> spotipy.Spotify:
        """Create authenticated Spotify client"""
        return spotipy.Spotify(auth=access_token)
    
    def get_user_profile(self, sp: spotipy.Spotify) -> Dict:
        """Get user's basic profile information"""
        try:
            return sp.current_user()
        except Exception as e:
            print(f"Error getting user profile: {e}")
            return {}
    
    def get_user_top_tracks(self, sp: spotipy.Spotify, limit: int = 50, time_range: str = "medium_term") -> List[Dict]:
        """Get user's top tracks"""
        try:
            results = sp.current_user_top_tracks(limit=limit, time_range=time_range)
            return results['items']
        except Exception as e:
            print(f"Error getting top tracks: {e}")
            return []
    
    def get_user_playlists(self, sp: spotipy.Spotify) -> List[Dict]:
        """Get user's playlists"""
        try:
            playlists = []
            results = sp.current_user_playlists(limit=50)
            playlists.extend(results['items'])
            
            # Handle pagination
            while results['next']:
                results = sp.next(results)
                playlists.extend(results['items'])
            
            return playlists
        except Exception as e:
            print(f"Error getting playlists: {e}")
            return []
    
    def get_playlist_tracks(self, sp: spotipy.Spotify, playlist_id: str) -> List[Dict]:
        """Get tracks from a specific playlist"""
        try:
            tracks = []
            results = sp.playlist_tracks(playlist_id)
            tracks.extend([item['track'] for item in results['items'] if item['track']])
            
            # Handle pagination
            while results['next']:
                results = sp.next(results)
                tracks.extend([item['track'] for item in results['items'] if item['track']])
            
            return tracks
        except Exception as e:
            print(f"Error getting playlist tracks: {e}")
            return []
    
    def get_audio_features(self, sp: spotipy.Spotify, track_ids: List[str]) -> List[Dict]:
        """Get audio features for a list of tracks"""
        try:
            # Spotify API allows max 100 tracks per request
            all_features = []
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i:i+100]
                features = sp.audio_features(batch)
                all_features.extend([f for f in features if f])  # Filter out None values
            
            return all_features
        except Exception as e:
            print(f"Error getting audio features: {e}")
            return []
    
    def get_recently_played(self, sp: spotipy.Spotify, limit: int = 50) -> List[Dict]:
        """Get user's recently played tracks"""
        try:
            results = sp.current_user_recently_played(limit=limit)
            return [item['track'] for item in results['items']]
        except Exception as e:
            print(f"Error getting recently played: {e}")
            return []
    
    def search_tracks(self, sp: spotipy.Spotify, query: str, limit: int = 20) -> List[Dict]:
        """Search for tracks"""
        try:
            results = sp.search(q=query, type='track', limit=limit)
            return results['tracks']['items']
        except Exception as e:
            print(f"Error searching tracks: {e}")
            return []