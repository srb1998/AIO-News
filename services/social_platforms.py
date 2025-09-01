# services/social_platforms.py 

import aiohttp
import asyncio
import os
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
import json
from config.settings import settings

class InstagramService:
    def __init__(self):
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        self.instagram_account_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
        self.base_url = "https://graph.facebook.com/v19.0"
        self.session = None
        
        # Rate limiting tracking
        self.daily_posts = 0
        self.last_reset = datetime.now().date()
        self.max_daily_posts = 25  # Instagram API limit
        
    async def get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None
    
    def _reset_daily_counter(self):
        """Reset daily post counter if it's a new day"""
        current_date = datetime.now().date()
        if current_date > self.last_reset:
            self.daily_posts = 0
            self.last_reset = current_date
    
    def _clean_instagram_caption(self, caption: str) -> str:
        """Clean and validate Instagram caption"""
        if not caption:
            return ""
        
        # Remove problematic characters
        cleaned = caption.encode('utf-8', 'ignore').decode('utf-8')
        
        # Instagram limits: 2200 characters
        if len(cleaned) > 2200:
            
            truncated = cleaned[:2190]
            last_period = truncated.rfind('.')
            last_space = truncated.rfind(' ')
            
            if last_period > 1900:  
                cleaned = truncated[:last_period + 1]
            elif last_space > 1900:
                cleaned = truncated[:last_space]
            else: 
                cleaned = truncated + "..."
        
        print(f"📱 Instagram caption: {len(cleaned)} characters")
        return cleaned
    
    async def check_posting_limit(self) -> Dict[str, Union[bool, int]]:
        """Check current posting limits from Instagram API"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{self.instagram_account_id}/content_publishing_limit"
            params = {"access_token": self.access_token}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    quota_usage = data.get("data", [{}])[0].get("quota_usage", 0)
                    config = data.get("data", [{}])[0].get("config", {})
                    quota_total = config.get("quota_total", 25)
                    
                    return {
                        "can_post": quota_usage < quota_total,
                        "posts_used": quota_usage,
                        "posts_remaining": quota_total - quota_usage,
                        "quota_total": quota_total
                    }
                else:
                    print(f"❌ Failed to check posting limit: {response.status}")
                    return {"can_post": self.daily_posts < self.max_daily_posts, "posts_used": self.daily_posts, "posts_remaining": self.max_daily_posts - self.daily_posts}
        except Exception as e:
            print(f"❌ Error checking posting limit: {e}")
            return {"can_post": self.daily_posts < self.max_daily_posts, "posts_used": self.daily_posts, "posts_remaining": self.max_daily_posts - self.daily_posts}
    
    async def create_media_container(self, media_url: str, media_type: str = "IMAGE", caption: str = "") -> Optional[str]:
        """Create a media container for single image/video - FIXED to include caption"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{self.instagram_account_id}/media"
            
            data = {
                "access_token": self.access_token,
            }
            
            if caption:
                cleaned_caption = self._clean_instagram_caption(caption)
                data["caption"] = cleaned_caption
                print(f"📱 Adding caption to media container: {len(cleaned_caption)} chars")
            
            if media_type == "IMAGE":
                data["image_url"] = media_url
            elif media_type == "VIDEO":
                data["video_url"] = media_url
                data["media_type"] = "REELS"
            
            print(f"🔄 Creating Instagram media container with caption: {bool(caption)}")
            
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    container_id = result.get("id")
                    print(f"✅ Media container created: {container_id}")
                    return container_id
                else:
                    error_text = await response.text()
                    print(f"❌ Failed to create media container: {response.status} - {error_text}")
                    return None
        except Exception as e:
            print(f"❌ Error creating media container: {e}")
            return None
    
    async def create_carousel_container(self, media_urls: List[str], caption: str = "") -> Optional[str]:
        """Create a carousel container for multiple images/videos - FIXED"""
        try:
            # First, create individual media containers WITHOUT captions
            media_containers = []
            session = await self.get_session()
            
            print(f"🔄 Creating {len(media_urls)} media containers for carousel")
            
            for i, media_url in enumerate(media_urls[:10]):  # Instagram carousel limit is 10
                # Determine media type based on URL extension
                media_type = "VIDEO" if any(ext in media_url.lower() for ext in ['.mp4', '.mov', '.avi']) else "IMAGE"
                # Don't add caption to individual containers - only to the main carousel
                container_id = await self.create_media_container(media_url, media_type, caption="")
                if container_id:
                    media_containers.append(container_id)
                    print(f"✅ Container {i+1}/{len(media_urls)}: {container_id}")
            
            if not media_containers:
                print("❌ No media containers created for carousel")
                return None
            
            print(f"🔄 Creating carousel container with {len(media_containers)} items")
            
            # Create carousel container with caption
            url = f"{self.base_url}/{self.instagram_account_id}/media"
            data = {
                "access_token": self.access_token,
                "media_type": "CAROUSEL",
                "children": ",".join(media_containers)
            }
            
            if caption:
                cleaned_caption = self._clean_instagram_caption(caption)
                data["caption"] = cleaned_caption
                print(f"📱 Adding caption to carousel: {len(cleaned_caption)} chars")
            
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    carousel_id = result.get("id")
                    print(f"✅ Carousel container created: {carousel_id}")
                    return carousel_id
                else:
                    error_text = await response.text()
                    print(f"❌ Failed to create carousel container: {response.status} - {error_text}")
                    return None
        except Exception as e:
            print(f"❌ Error creating carousel container: {e}")
            return None
    
    async def publish_container(self, container_id: str) -> bool:
        """Publish a media container"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{self.instagram_account_id}/media_publish"
            data = {
                "access_token": self.access_token,
                "creation_id": container_id
            }
            
            print(f"🚀 Publishing container: {container_id}")
            
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    media_id = result.get("id")
                    if media_id:
                        self.daily_posts += 1
                        print(f"✅ Successfully published to Instagram: {media_id}")
                        return True
                else:
                    error_text = await response.text()
                    print(f"❌ Failed to publish container: {response.status} - {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Error publishing container: {e}")
            return False
    
    async def post_single_media(self, media_url: str, caption: str = "", media_type: str = "IMAGE") -> bool:
        """Post single image or video - FIXED to include caption during creation"""
        self._reset_daily_counter()
        
        # Check posting limits
        limit_check = await self.check_posting_limit()
        if not limit_check["can_post"]:
            print(f"❌ Daily posting limit reached: {limit_check['posts_used']}/{limit_check.get('quota_total', 25)}")
            return False
        
        print(f"📱 Posting single {media_type.lower()} to Instagram")
        print(f"   Media: {media_url}")
        print(f"   Caption length: {len(caption) if caption else 0}")
        
        # Create media container WITH caption
        container_id = await self.create_media_container(media_url, media_type, caption)
        if not container_id:
            print("❌ Failed to create media container")
            return False
        
        return await self.publish_container(container_id)
    
    async def post_carousel(self, media_urls: List[str], caption: str = "") -> bool:
        """Post carousel with multiple media - FIXED"""
        self._reset_daily_counter()
        
        # Check posting limits
        limit_check = await self.check_posting_limit()
        if not limit_check["can_post"]:
            print(f"❌ Daily posting limit reached: {limit_check['posts_used']}/{limit_check.get('quota_total', 25)}")
            return False
        
        if len(media_urls) < 2:
            print("❌ Carousel requires at least 2 media items")
            return False
        
        if len(media_urls) > 10:
            print("⚠️ Instagram carousel limited to 10 items, truncating")
            media_urls = media_urls[:10]
        
        print(f"📱 Posting carousel to Instagram ({len(media_urls)} items)")
        print(f"   Caption length: {len(caption) if caption else 0}")
        
        # Create carousel container WITH caption
        container_id = await self.create_carousel_container(media_urls, caption)
        if not container_id:
            print("❌ Failed to create carousel container")
            return False
        
        # Publish
        return await self.publish_container(container_id)
    
    async def post_story_content(self, images: List[str], videos: List[str], caption: str = "") -> bool:
        """Intelligently post story content based on available media - FIXED"""
        all_media = images + videos
        
        if not all_media:
            print("❌ No media provided for Instagram post")
            return False
        
        print(f"📱 Instagram post strategy: {len(all_media)} media items")
        
        # Strategy: Use carousel for multiple items, single post for one item
        if len(all_media) == 1:
            media_url = all_media[0]
            media_type = "VIDEO" if media_url in videos else "IMAGE"
            print(f"📱 Using single post strategy: {media_type}")
            return await self.post_single_media(media_url, caption, media_type)
        else:
            print(f"📱 Using carousel strategy: {len(all_media)} items")
            return await self.post_carousel(all_media, caption)
    
    def get_status(self) -> Dict:
        """Get current service status"""
        self._reset_daily_counter()
        return {
            "service": "instagram",
            "authenticated": bool(self.access_token and self.instagram_account_id),
            "daily_posts_used": self.daily_posts,
            "daily_posts_remaining": self.max_daily_posts - self.daily_posts,
            "can_post": self.daily_posts < self.max_daily_posts,
            "last_reset": self.last_reset.isoformat()
        }


class SocialPlatformManager:
    """Manager class for all social platforms"""
    
    def __init__(self):
        self.instagram = InstagramService()
        self.platforms = {
            "instagram": self.instagram
        }
        # Future platforms can be added here
        # self.twitter = TwitterService()
        # self.linkedin = LinkedInService()
    
    async def post_to_platform(self, platform: str, images: List[str], videos: List[str], content: str) -> bool:
        """Post content to specified platform"""
        if platform not in self.platforms:
            print(f"❌ Platform {platform} not implemented")
            return False
        
        service = self.platforms[platform]
        
        try:
            if platform == "instagram":
                return await service.post_story_content(images, videos, content)
            # Add other platforms here
            else:
                print(f"❌ Posting logic for {platform} not implemented")
                return False
        except Exception as e:
            print(f"❌ Error posting to {platform}: {e}")
            return False
    
    async def get_all_status(self) -> Dict:
        """Get status of all platforms"""
        status = {}
        for platform_name, service in self.platforms.items():
            try:
                status[platform_name] = service.get_status()
            except Exception as e:
                status[platform_name] = {"error": str(e)}
        return status
    
    async def close_all_sessions(self):
        """Close all platform sessions"""
        for service in self.platforms.values():
            if hasattr(service, 'close_session'):
                await service.close_session()