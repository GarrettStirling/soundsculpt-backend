# Backend Deployment Guide

## Environment Variables Required

Your backend needs these environment variables. Set them in Railway's environment variables section:

### Required Variables:
```
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
SPOTIFY_REDIRECT_URI=https://your-backend.railway.app/auth/callback
FRONTEND_URL=https://your-frontend.vercel.app
LASTFM_API_KEY=your_lastfm_api_key_here
LASTFM_SHARED_SECRET=your_lastfm_shared_secret_here
YOUTUBE_API_KEY=your_youtube_api_key_here
```

## Important Notes:

1. **SPOTIFY_REDIRECT_URI**: Must match your Railway backend URL + `/auth/callback`
2. **CORS**: Update the CORS origins in `app/main.py` to include your Vercel frontend URL
3. **No .env file needed**: The Dockerfile has been updated to not require a .env file

## CORS Update Required:

In `app/main.py`, update line 25 to include your Vercel frontend URL:

```python
allow_origins=[
    "http://localhost:5173", 
    "http://localhost:5174", 
    "http://127.0.0.1:5173", 
    "http://127.0.0.1:5174",
    "https://your-frontend.vercel.app"  # Add this line
],
```

## Deployment Steps:

1. **Push code to GitHub** (make sure .env is in .gitignore)
2. **Connect Railway to your GitHub repo**
3. **Set environment variables** in Railway dashboard
4. **Deploy** - Railway will automatically build using the Dockerfile
5. **Copy the generated URL** and update your frontend's VITE_API_URL
