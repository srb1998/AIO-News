import cloudinary
import cloudinary.uploader
import json
import os
import asyncio
import tempfile
from typing import Dict

# Ensure Cloudinary is configured (it will be by the time this is called)
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

async def upload_json_to_cloudinary(data: Dict, workflow_id: str) -> str:
    """
    Uploads a dictionary as a JSON file to a specific Cloudinary folder.

    Args:
        data: The dictionary to upload.
        workflow_id: The unique ID for this workflow run.

    Returns:
        The secure URL of the uploaded JSON file, or an empty string on failure.
    """
    print(f"☁️ Uploading workflow result for {workflow_id} to Cloudinary...")
    try:
        # Use a temporary file to securely handle the JSON data
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".json", encoding='utf-8') as temp_f:
            json.dump(data, temp_f, indent=2)
            temp_filepath = temp_f.name
        
        folder_path = f"news/processed/{workflow_id}"
        public_id = "workflow_summary"

        # Cloudinary's upload is a synchronous (blocking) call,
        # so we run it in a separate thread to keep our service non-blocking.
        upload_result = await asyncio.to_thread(
            cloudinary.uploader.upload,
            temp_filepath,
            folder=folder_path,
            public_id=public_id,
            resource_type="raw" # Use "raw" for non-media files like JSON
        )
        
        # Clean up the temporary file
        os.remove(temp_filepath)
        
        secure_url = upload_result.get("secure_url")
        print(f"✅ Workflow result saved to Cloudinary: {secure_url}")
        return secure_url

    except Exception as e:
        print(f"❌ Failed to upload workflow result to Cloudinary: {e}")
        # Clean up temp file in case of error
        if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        return ""