from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, ValidationError
from typing import Dict, Any, Optional
import json

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
async def handle_cloudinary_webhook(request: Request):
    """Enhanced webhook handler with better error handling and debugging."""
    
    # Get raw request data for debugging
    try:
        raw_body = await request.body()
        webhook_data = await request.json()
    except Exception as e:
        print(f"❌ Failed to parse webhook request: {e}")
        return {"status": "error", "error": "Invalid JSON"}, 400
    
    try:
        notification = CloudinaryUploadNotification(**webhook_data)
    except ValidationError as e:
        print(f"❌ Pydantic validation failed: {e}")
        print(f"❌ Raw data that failed validation: {webhook_data}")
        
        # Let's try to handle it manually for debugging
        public_id = webhook_data.get("public_id", "unknown")
        
        print(f"📸 Manual parsing - Public ID: {public_id}")
        
        # If it's a workflow summary, ignore it
        if "workflow_summary" in public_id:
            print(f"🔄 Ignoring workflow summary file: {public_id}")
            return {"status": "ignored", "reason": "workflow_summary_file"}
            
        # Return error for other validation failures
        return {"status": "error", "error": f"Validation failed: {str(e)}"}, 422
        
    if not social_media_manager_instance:
        return {"status": "error", "error": "Social Media Manager not initialized"}, 503

    # Check if this is a workflow summary file or any file without proper context
    if not notification.context or not notification.context.custom:
        if "workflow_summary" in notification.public_id:
            print(f"🔄 Ignoring workflow summary file: {notification.public_id}")
            return {"status": "ignored", "reason": "workflow_summary_file"}
        else:
            print(f"⚠️ File uploaded without required context: {notification.public_id}")
            return {"status": "ignored", "reason": "missing_context"}
        
    custom_context = notification.context.custom
    story_id = custom_context.get("story_id")
    platform = custom_context.get("platform")
    workflow_id = custom_context.get("workflow_id")
    
    if not story_id:
        print("❌ Missing story_id in context")
        return {"status": "error", "error": "Missing story_id in custom context"}, 400
        
    if not platform:
        print("❌ Missing platform in context")
        return {"status": "error", "error": "Missing platform in custom context"}, 400
    
    expected_platforms = ["twitter", "instagram", "youtube", "linkedin"]
    if platform not in expected_platforms:
        print(f"⚠️ Unexpected platform: {platform}")
        return {"status": "ignored", "reason": f"unexpected_platform_{platform}"}

    print(f"✅ Processing webhook for Story: {story_id}, Platform: {platform}")

    try:
        await social_media_manager_instance.handle_webhook_upload(
            story_id=story_id,
            platform=platform,
            media_url=notification.secure_url,
            resource_type=notification.resource_type,
            workflow_id=workflow_id
        )
        
        return {"status": "success", "message": f"Successfully processed {notification.public_id}"}
        
    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        return {"status": "error", "error": f"Processing failed: {str(e)}"}, 500

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "manager_initialized": social_media_manager_instance is not None}