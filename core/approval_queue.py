# --- START OF FILE approval_queue.py ---

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from filelock import FileLock
from config.settings import settings

class ApprovalQueue:
    def __init__(self):
        self.storage_path = settings.TELEGRAM_CONFIG["approval_storage_path"]
        self.timeout_minutes = settings.TELEGRAM_CONFIG["approval_timeout_minutes"]
        os.makedirs(self.storage_path, exist_ok=True)

    def add_request(self, story_id: str, platform: str, workflow_id: str, content: str, sub_content: str, images: List[str], videos: List[str], message_ids: Dict[str, int], created_at: datetime) -> None:
        """Add a pending approval request to the queue, including sub_content."""
        request = {
            "story_id": story_id,
            "platform": platform,
            "workflow_id": workflow_id,
            "content": content,
            "sub_content": sub_content,  # <-- Storing the summary for image overlays
            "images": images,
            "videos": videos,
            "message_ids": message_ids,
            "created_at": created_at.isoformat(),
            "timeout_at": (created_at + timedelta(minutes=self.timeout_minutes)).isoformat(),
            "status": "PENDING"
        }
        file_path = os.path.join(self.storage_path, f"{story_id}_{platform}.json")
        with FileLock(f"{file_path}.lock"):
            with open(file_path, 'w') as f:
                json.dump(request, f, indent=2)

    def update_status(self, story_id: str, platform: str, status: str) -> Optional[Dict]:
        """Update the status of an approval request"""
        file_path = os.path.join(self.storage_path, f"{story_id}_{platform}.json")
        if not os.path.exists(file_path): return None
        with FileLock(f"{file_path}.lock"):
            try:
                with open(file_path, 'r+') as f:
                    request = json.load(f)
                    request["status"] = status
                    request["updated_at"] = datetime.now().isoformat()
                    f.seek(0)
                    json.dump(request, f, indent=2)
                    f.truncate()
                return request
            except Exception as e:
                print(f"❌ Failed to update approval status for {story_id}_{platform}: {e}")
                return None

    def update_media(self, story_id: str, platform: str, media_type: str, media_path: str) -> Optional[Dict]:
        """Add a new media URL to a request"""
        file_path = os.path.join(self.storage_path, f"{story_id}_{platform}.json")
        if not os.path.exists(file_path): return None
        with FileLock(f"{file_path}.lock"):
            try:
                with open(file_path, 'r+') as f:
                    request = json.load(f)
                    if media_type == "images":
                        request["images"].append(media_path)
                    elif media_type == "videos":
                        request["videos"].append(media_path)
                    request["updated_at"] = datetime.now().isoformat()
                    f.seek(0)
                    json.dump(request, f, indent=2)
                    f.truncate()
                return request
            except Exception as e:
                print(f"❌ Failed to update {media_type} for {story_id}_{platform}: {e}")
                return None

    def get_request(self, story_id: str, platform: str) -> Optional[Dict]:
        file_path = os.path.join(self.storage_path, f"{story_id}_{platform}.json")
        if not os.path.exists(file_path): return None
        with FileLock(f"{file_path}.lock"):
            try:
                with open(file_path, 'r') as f: return json.load(f)
            except Exception as e:
                print(f"❌ Failed to load approval request for {story_id}_{platform}: {e}")
                return None

    def get_next_approved_post(self) -> Optional[Dict]:
        """
        Finds all APPROVED posts and returns the one that was created earliest.
        This ensures posts are published in the order they were generated.
        """
        approved_posts = []
        for filename in os.listdir(self.storage_path):
            if not filename.endswith(".json"):
                continue
            
            file_path = os.path.join(self.storage_path, filename)
            with FileLock(f"{file_path}.lock"):
                try:
                    with open(file_path, 'r') as f:
                        request = json.load(f)
                    if request.get("status") == "APPROVED":
                        approved_posts.append(request)
                except Exception as e:
                    print(f"❌ Failed to load approved request {filename}: {e}")

        if not approved_posts:
            return None

        # Sort by the 'created_at' timestamp to find the oldest approved post
        approved_posts.sort(key=lambda x: datetime.fromisoformat(x['created_at']))
        return approved_posts[0]


    def get_timed_out_requests(self) -> List[Dict]:
        """Return requests that have timed out."""
        timed_out = []
        current_time = datetime.now()
        for filename in os.listdir(self.storage_path):
            if filename.endswith(".json"):
                file_path = os.path.join(self.storage_path, filename)
                with FileLock(f"{file_path}.lock"):
                    try:
                        with open(file_path, 'r') as f:
                            request = json.load(f)
                        timeout_at = datetime.fromisoformat(request["timeout_at"])
                        if request["status"] == "PENDING" and current_time >= timeout_at:
                            timed_out.append(request)
                    except Exception as e:
                        print(f"❌ Failed to check timeout for {filename}: {e}")
        return timed_out