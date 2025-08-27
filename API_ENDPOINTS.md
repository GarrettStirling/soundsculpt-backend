# Song Recommender API - Clean Endpoints

## 🎵 Available Endpoints

### **Authentication** (`/auth`)
- `GET /auth/login` - Start Spotify OAuth flow
- `GET /auth/callback` - Handle OAuth callback
- `GET /auth/redirect` - Redirect endpoint

### **Spotify Data** (`/spotify`)
- `GET /spotify/top-tracks` - Get user's top tracks
- `GET /spotify/top-artists` - Get user's top artists
- `GET /spotify/profile` - Get user profile info
- `GET /spotify/playlists` - Get user's playlists

### **Recommendations** (`/recommendations`)
- `GET /recommendations/search-based-discovery` ✅ **WORKING** - Novel music discovery using search
- `GET /recommendations/default` ⚠️ - AI recommendations (needs audio features access)
- `GET /recommendations/custom` ⚠️ - Custom track-based recommendations (needs audio features access)
- `GET /recommendations/by-playlist` ⚠️ - Playlist-based recommendations (needs audio features access)

### **System**
- `GET /` - API status
- `GET /health` - Health check
- `GET /callback` - Fallback OAuth callback

---

## 🧹 Cleaned Up (Removed)

### **Removed Endpoints**
- `/recommendations/test-scopes` - Test endpoint
- `/recommendations/basic-test` - Debug endpoint  
- `/recommendations/simple-recommendations` - Failed alternative
- `/recommendations/discover-new-music` - Failed related artists approach
- `/recommendations/alternative-recommendations` - Fallback approach
- `/recommendations/analyze-taste` - Analysis endpoint
- `/test/auth` - Test auth page
- `/test-auth` - Simple test endpoint

### **Removed Files**
- `app/api/test_auth.py` - Test authentication file
- All `__pycache__` directories - Python cache files

---

## 🎯 Primary Working Endpoint

**`/recommendations/search-based-discovery`** is the main working recommendation endpoint that:

- ✅ Analyzes your top 100 tracks and genres
- ✅ Uses search-based discovery to find new music
- ✅ Excludes tracks you already have
- ✅ Filters out artists you already know
- ✅ Provides truly novel music recommendations
- ✅ Works around Spotify API limitations

---

## 📝 Notes

- The AI-powered endpoints (`default`, `custom`, `by-playlist`) may work if Spotify enables audio features access for your app
- The search-based discovery is the most reliable approach for novel music recommendations
- All authentication and data retrieval endpoints are working properly
