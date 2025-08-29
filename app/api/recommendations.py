"""
Recommendation API endpoints - Clean version
"""

from fastapi import APIRouter, HTTPException, Query, Body
from app.services.simple_recommendation_service import SimpleRecommendationService
from typing import List, Optional, Dict

router = APIRouter(prefix="/recommendations", tags=["AI Recommendations"])

# Initialize recommendation service
simple_recommendation_service = SimpleRecommendationService()

@router.post("/ml-recommendations")
async def get_ml_recommendations(
    token: str,
    n_recommendations: int = Query(30, ge=1, le=50, description="Number of songs to recommend"),
    user_controls: Optional[Dict] = Body(None, description="User preference controls")
):
    """
    Get personalized AI recommendations using user's listening history and preferences
    """
    try:
        print(f"=== AI RECOMMENDATIONS ENDPOINT ===")
        print(f"User controls: {user_controls}")
        
        # Use the simple recommendation service with deduplication
        result = simple_recommendation_service.get_simple_recommendations(
            access_token=token,
            n_recommendations=n_recommendations
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Add user controls info to response
        result["user_controls"] = user_controls
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"AI recommendations error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
