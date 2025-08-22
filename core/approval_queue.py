# approval_queue.py - Updated with hashtags and platform content support

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from async_filelock import AsyncFileLock
from config.settings import settings

class ApprovalQueue:
    def __init__(self):
        self.storage_path = settings.TELEGRAM_CONFIG["approval_storage_path"]
        self.timeout_minutes = settings.TELEGRAM_CONFIG["approval_timeout_minutes"]
        os.makedirs(self.storage_path, exist_ok=True)

    def add_request(self, story_id: str, platform: str, workflow_id: str, content: str, 
                   sub_content: str, images: List[str], videos: List[str], 
                   message_ids: Dict[str, int], created_at: datetime,
                   platform_content: str = "", hashtags: List[str] = None) -> None:
        request = {
            "story_id": story_id, "platform": platform, "workflow_id": workflow_id,
            "content": content, "sub_content": sub_content, "platform_content": platform_content,
            "hashtags": hashtags or [], "images": images, "videos": videos,
            "message_ids": message_ids, "created_at": created_at.isoformat(),
            "timeout_at": (created_at + timedelta(minutes=self.timeout_minutes)).isoformat(),
            "status": "PENDING", "headline_applied": False
        }
        file_path = os.path.join(self.storage_path, f"{story_id}_{platform}.json")
        with open(file_path, 'w') as f:
            json.dump(request, f, indent=2)
    
    def set_processed_first_image(self, story_id: str, platform: str, media_url: str) -> Optional[Dict]:
        file_path = os.path.join(self.storage_path, f"{story_id}_{platform}.json")
        if not os.path.exists(file_path): return None
        with open(file_path, 'r+') as f:
            request = json.load(f)
            images = request.get("images", [])
            images.insert(0, media_url)
            request["images"] = images
            request["headline_applied"] = True
            request["updated_at"] = datetime.now().isoformat()
            f.seek(0)
            json.dump(request, f, indent=2)
            f.truncate()
        return request

    def update_media(self, story_id: str, platform: str, media_type: str, media_path: str) -> Optional[Dict]:
        file_path = os.path.join(self.storage_path, f"{story_id}_{platform}.json")
        if not os.path.exists(file_path): return None
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

    def get_request(self, story_id: str, platform: str) -> Optional[Dict]:
        file_path = os.path.join(self.storage_path, f"{story_id}_{platform}.json")
        if not os.path.exists(file_path): return None
        with open(file_path, 'r') as f: 
            request = json.load(f)
        if "platform_content" not in request: request["platform_content"] = ""
        if "hashtags" not in request: request["hashtags"] = []
        return request

    def get_next_approved_post(self) -> Optional[Dict]:
       approved_posts = []
       for filename in os.listdir(self.storage_path):
           if not filename.endswith(".json"): continue
           file_path = os.path.join(self.storage_path, filename)
           try:
               with open(file_path, 'r') as f:
                   request = json.load(f)
               if request.get("status") == "APPROVED":
                   approved_posts.append(request)
           except Exception as e:
               print(f"❌ Failed to load approved request {filename}: {e}")

       if not approved_posts: return None
       approved_posts.sort(key=lambda x: datetime.fromisoformat(x['created_at']))
       return approved_posts[0]

    def get_all_pending(self) -> List[Dict]:
        pending = []
        for filename in os.listdir(self.storage_path):
            if not filename.endswith(".json"): continue
            file_path = os.path.join(self.storage_path, filename)
            try:
                with open(file_path, 'r') as f:
                    request = json.load(f)
                if request.get("status") == "PENDING":
                    pending.append(request)
            except Exception as e:
                print(f"❌ Failed to check pending for {filename}: {e}")
        return pending

    def get_timed_out_requests(self) -> List[Dict]:
        timed_out = []
        current_time = datetime.now()
        for filename in os.listdir(self.storage_path):
            if not filename.endswith(".json"): continue
            file_path = os.path.join(self.storage_path, filename)
            try:
                with open(file_path, 'r') as f:
                    request = json.load(f)
                timeout_at = datetime.fromisoformat(request["timeout_at"])
                if request["status"] == "PENDING" and current_time >= timeout_at:
                    timed_out.append(request)
            except Exception as e:
                print(f"❌ Failed to check timeout for {filename}: {e}")
        return timed_out

    @property
    def queue(self) -> List[Dict]:
        all_requests = []
        for filename in os.listdir(self.storage_path):
            if not filename.endswith(".json"): continue
            file_path = os.path.join(self.storage_path, filename)
            try:
                with open(file_path, 'r') as f:
                    all_requests.append(json.load(f))
            except Exception as e:
                print(f"❌ Failed to load request {filename}: {e}")
        return all_requests