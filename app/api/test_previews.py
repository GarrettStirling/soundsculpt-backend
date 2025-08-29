from fastapi import APIRouter, HTTPException, Depends
from app.api.auth import get_current_user
import spotipy

router = APIRouter()

@router.get("/test-previews")
async def test_preview_urls(current_user: dict = Depends(get_current_user)):
    """Test endpoint to check if we can get preview URLs for known popular tracks"""
    try:
        sp = spotipy.Spotify(auth=current_user['access_token'])
        
        # Test with some known popular tracks that should have previews
        test_track_ids = [
            '4iV5W9uYEdYUVa79Axb7Rh',  # Never Gonna Give You Up - Rick Astley
            '0VjIjW4GlULA7QX7UoMPD',   # Blinding Lights - The Weeknd  
            '11dFghVXANMlKmJXsNCbNl',  # Shape of You - Ed Sheeran
            '7qiZfU4dY1lWllzX7mPBI3',  # As It Was - Harry Styles
            '4uLU6hMCjMI75M1A2tKUQC'   # Anti-Hero - Taylor Swift
        ]
        
        results = []
        
        # Try without market
        print("Testing preview URLs without market restriction...")
        tracks = sp.tracks(test_track_ids)
        
        for track in tracks['tracks']:
            preview_info = {
                'name': track['name'],
                'artist': ', '.join([artist['name'] for artist in track['artists']]),
                'preview_url': track.get('preview_url'),
                'has_preview': bool(track.get('preview_url')),
                'popularity': track.get('popularity'),
                'available_markets_count': len(track.get('available_markets', []))
            }
            results.append(preview_info)
            print(f"Track: {preview_info['name']} - Has Preview: {preview_info['has_preview']}")
        
        return {
            'test_results': results,
            'summary': {
                'total_tracks': len(results),
                'tracks_with_previews': sum(1 for r in results if r['has_preview']),
                'preview_percentage': round((sum(1 for r in results if r['has_preview']) / len(results)) * 100, 1)
            }
        }
        
    except Exception as e:
        print(f"Test preview error: {e}")
        raise HTTPException(status_code=500, detail=f"Error testing previews: {str(e)}")
