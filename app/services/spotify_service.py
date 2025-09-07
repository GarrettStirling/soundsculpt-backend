import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
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

        # Define the scope of permissions we need (expanded for recommendations and playlists)
        self.scope = (
            "user-read-recently-played user-library-read playlist-read-private "
            "user-top-read playlist-read-collaborative user-read-email "
            "playlist-modify-public playlist-modify-private"
        )
        
        # Initialize Spotify OAuth
        self.sp_oauth = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope
        )
    
    def get_auth_url(self) -> str:
        """Get the authorization URL for Spotify login"""
        return self.sp_oauth.get_authorize_url(state="state")
    
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
    
    def create_client_credentials_client(self) -> spotipy.Spotify:
        """Create Spotify client using Client Credentials flow (no user auth needed)"""
        client_credentials_manager = SpotifyClientCredentials(
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        return spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    
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
    
    def create_playlist(self, sp: spotipy.Spotify, name: str, description: str = "", public: bool = False) -> Optional[Dict]:
        """Create a new playlist for the user"""
        try:
            user_id = sp.current_user()['id']
            playlist = sp.user_playlist_create(
                user=user_id,
                name=name,
                public=public,
                description=description
            )
            return playlist
        except Exception as e:
            print(f"Error creating playlist: {e}")
            return None
    
    def add_tracks_to_playlist(self, sp: spotipy.Spotify, playlist_id: str, track_ids: List[str]) -> bool:
        """Add tracks to an existing playlist"""
        try:
            print(f"Adding {len(track_ids)} tracks to playlist {playlist_id}")  # DEBUG
            # Spotify API allows max 100 tracks per request
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i:i+100]
                track_uris = [f"spotify:track:{track_id}" for track_id in batch]
                sp.playlist_add_items(playlist_id, track_uris)
            return True
        except Exception as e:
            print(f"Error adding tracks to playlist: {e}")
            return False
    
    def create_playlist_from_recommendations(self, sp: spotipy.Spotify, recommendations: List[Dict], playlist_name: str, description: str = "") -> Optional[Dict]:
        """Create a playlist and add recommended tracks to it"""
        try:
            # Create the playlist
            playlist = self.create_playlist(sp, playlist_name, description, public=False)
            if not playlist:
                return None
            
            # Extract track IDs from recommendations
            track_ids = [track['id'] for track in recommendations if track.get('id')]
            
            # Add tracks to the playlist
            if track_ids:
                success = self.add_tracks_to_playlist(sp, playlist['id'], track_ids)
                if success:
                    return playlist
            
            return None
        except Exception as e:
            print(f"Error creating playlist from recommendations: {e}")
            return None