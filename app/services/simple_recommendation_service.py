"""
Simple Recommendation Service - Fallback approach without complex API calls
"""

import spotipy
from typing import List, Dict, Optional
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from .spotify_service import SpotifyService

class SimpleRecommendationService:
    def __init__(self):
        self.spotify_service = SpotifyService()
    
    def get_simple_recommendations(self, access_token: str, n_recommendations: int = 30) -> Dict:
        """
        Get recommendations using a simple, reliable approach
        """
        try:
            print("=== SIMPLE RECOMMENDATION SERVICE ===")
            sp = self.spotify_service.create_spotify_client(access_token)
            
            # Get user's existing tracks to avoid duplicates and track artist frequency
            user_tracks = set()
            artist_track_count = {}  # Track how many songs user has per artist
            
            # Get user's saved tracks (Liked Songs) - scan up to 10,000 for full deduplication
            try:
                print("Fetching user's saved tracks (Liked Songs)...")
                saved_tracks_count = 0
                max_liked = 10000
                for offset in range(0, max_liked, 50):
                    saved_tracks = sp.current_user_saved_tracks(limit=50, offset=offset)
                    for item in saved_tracks['items']:
                        if item['track'] and item['track']['id']:
                            user_tracks.add(item['track']['id'])
                            saved_tracks_count += 1
                            # Count tracks per artist
                            for artist in item['track']['artists']:
                                artist_id = artist['id']
                                artist_track_count[artist_id] = artist_track_count.get(artist_id, 0) + 1
                    if len(saved_tracks['items']) < 50:
                        break
                print(f"Found {saved_tracks_count} saved tracks (full scan) to exclude")
            except Exception as e:
                print(f"Error fetching saved tracks: {e}")
                pass
            
            # Get user's playlist tracks - parallelize fetching for speed
            try:
                print("Fetching user's playlist tracks in parallel...")
                playlist_tracks_count = 0
                playlists = sp.current_user_playlists(limit=50)
                user_id = sp.me()['id']
                playlist_limit = 200
                playlist_ids = [pl['id'] for i, pl in enumerate(playlists['items']) if i < playlist_limit and pl['owner']['id'] == user_id]

                def fetch_tracks(playlist_id):
                    tracks_collected = []
                    for offset in range(0, 200, 50):
                        tracks = sp.playlist_tracks(playlist_id, limit=50, offset=offset)
                        tracks_collected.extend(tracks['items'])
                        if len(tracks['items']) < 50:
                            break
                    return tracks_collected

                with ThreadPoolExecutor(max_workers=8) as executor:
                    future_to_playlist = {executor.submit(fetch_tracks, pid): pid for pid in playlist_ids}
                    for future in as_completed(future_to_playlist):
                        try:
                            items = future.result()
                            for item in items:
                                if item['track'] and item['track']['id']:
                                    if item['track']['id'] not in user_tracks:
                                        user_tracks.add(item['track']['id'])
                                        playlist_tracks_count += 1
                                    # Count tracks per artist
                                    for artist in item['track']['artists']:
                                        artist_id = artist['id']
                                        artist_track_count[artist_id] = artist_track_count.get(artist_id, 0) + 1
                        except Exception as e:
                            print(f"Error processing playlist: {e}")
                            continue
                print(f"Found {playlist_tracks_count} additional playlist tracks to exclude (parallel)")
                print(f"Total user tracks to exclude (full scan): {len(user_tracks)}")
                # Find artists with 5+ songs
                # Pre-filter artist IDs for O(1) lookup
                excluded_artists = set([artist_id for artist_id, count in artist_track_count.items() if count >= 5])
                print(f"Excluding {len(excluded_artists)} artists with 5+ songs in user's library (O(1) lookup)")
                
            except Exception as e:
                print(f"Error fetching playlists: {e}")
                excluded_artists = set()
                pass
            
            # Get user's top artists
            top_artists = sp.current_user_top_artists(limit=10)['items']
            print(f"Found {len(top_artists)} top artists")
            
            recommendations = []
            seen_ids = set(user_tracks)  # Start with user's existing tracks
            
            # Get top tracks from each top artist
            for artist in top_artists:
                try:
                    artist_top_tracks = sp.artist_top_tracks(artist['id'])
                    for track in artist_top_tracks['tracks'][:3]:  # Top 3 from each artist
                        # Check if track is already in user's library
                        if track['id'] in seen_ids:
                            continue
                            
                        # Check if any artist on this track is excluded (has 5+ songs in user's library)
                        track_artists = [artist['id'] for artist in track['artists']]
                        if any(artist_id in excluded_artists for artist_id in track_artists):
                            continue
                            
                        if len(recommendations) < n_recommendations:
                            recommendations.append(track)
                            seen_ids.add(track['id'])
                except Exception as e:
                    print(f"Error getting tracks for artist {artist['name']}: {e}")
                    continue
            
            # If we need more recommendations, get from related artists
            if len(recommendations) < n_recommendations:
                print("Getting tracks from related artists...")
                for artist in top_artists[:5]:  # Limit to avoid too many calls
                    try:
                        related_artists = sp.artist_related_artists(artist['id'])
                        for related_artist in related_artists['artists'][:2]:  # Top 2 related
                            try:
                                # Skip if this related artist has 5+ songs in user's library
                                if related_artist['id'] in excluded_artists:
                                    continue
                                    
                                related_top_tracks = sp.artist_top_tracks(related_artist['id'])
                                for track in related_top_tracks['tracks'][:2]:  # Top 2 from each
                                    # Check if track is already in user's library
                                    if track['id'] in seen_ids:
                                        continue
                                        
                                    # Check if any artist on this track is excluded
                                    track_artists = [artist['id'] for artist in track['artists']]
                                    if any(artist_id in excluded_artists for artist_id in track_artists):
                                        continue
                                        
                                    if len(recommendations) < n_recommendations:
                                        recommendations.append(track)
                                        seen_ids.add(track['id'])
                            except:
                                continue
                    except Exception as e:
                        print(f"Error getting related artists for {artist['name']}: {e}")
                        continue
                    
                    if len(recommendations) >= n_recommendations:
                        break
            
            # If still need more, use search for discovery
            if len(recommendations) < n_recommendations:
                print("Using search for additional recommendations...")
                search_terms = ["indie rock", "electronic", "alternative", "indie pop", "synth pop"]
                
                for term in search_terms:
                    try:
                        search_result = sp.search(q=term, type='track', limit=5)
                        for track in search_result['tracks']['items']:
                            # Check if track is already in user's library
                            if track['id'] in seen_ids:
                                continue
                                
                            # Check if any artist on this track is excluded
                            track_artists = [artist['id'] for artist in track['artists']]
                            if any(artist_id in excluded_artists for artist_id in track_artists):
                                continue
                                
                            if len(recommendations) < n_recommendations:
                                recommendations.append(track)
                                seen_ids.add(track['id'])
                    except:
                        continue
                    
                    if len(recommendations) >= n_recommendations:
                        break
            
            # Shuffle for variety
            random.shuffle(recommendations)
            final_recommendations = recommendations[:n_recommendations]
            
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
            
            print(f"Generated {len(formatted_recommendations)} simple recommendations (excluded {len(user_tracks)} existing tracks, {len(excluded_artists)} over-represented artists)")
            return {
                "recommendations": formatted_recommendations,
                "algorithm": "simple_artist_based_filtered",
                "excluded_tracks_count": len(user_tracks),
                "excluded_artists_count": len(excluded_artists),
                "message": f"Found {len(formatted_recommendations)} personalized recommendations"
            }
            
        except Exception as e:
            print(f"Simple recommendation error: {e}")
            return {"error": str(e)}
