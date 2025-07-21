from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

# This will be initialized and passed from the main service.py
social_media_manager_instance = None

app = FastAPI()

def set_social_media_manager(manager_instance):
    """Allows the main service.py to inject the real manager instance."""
    global social_media_manager_instance
    social_media_manager_instance = manager_instance

class CloudinaryContext(BaseModel):
    custom: Dict[str, str]

class CloudinaryUploadNotification(BaseModel):
    public_id: str
    resource_type: str
    secure_url: str
    context: Optional[CloudinaryContext] = None
    
@app.post("/cloudinary-notification")
async def handle_cloudinary_webhook(notification: CloudinaryUploadNotification):
    """This endpoint receives notifications from Cloudinary after a successful upload."""
    print(f"📸 Webhook received for: {notification.public_id}")
    
    if not social_media_manager_instance:
        raise HTTPException(status_code=503, detail="Social Media Manager not initialized")

    if not notification.context or not notification.context.custom:
        raise HTTPException(status_code=400, detail="Missing custom context in notification")
        
    custom_context = notification.context.custom
    story_id = custom_context.get("story_id")
    platform = custom_context.get("platform")
    
    if not all([story_id, platform]):
        raise HTTPException(status_code=400, detail="Missing required fields (story_id, platform) in custom context")

    print(f"Delegating processing for Story: {story_id}, Platform: {platform}")

    # Delegate the complex logic to the real SocialMediaManager instance
    await social_media_manager_instance.handle_webhook_upload(
        story_id=story_id,
        platform=platform,
        media_url=notification.secure_url,
        resource_type=notification.resource_type
    )
    
    return {"status": "ok", "message": f"Processing initiated for {notification.public_id}"}