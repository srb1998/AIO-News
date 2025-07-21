# FILE: services/social_platforms.py

import asyncio
import aiohttp
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import tweepy
import requests
from pathlib import Path

@dataclass
class PlatformCredentials:
    platform: str
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    access_token_secret: str = ""
    bearer_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""
    active: bool = False

class SocialPlatformManager:
    def __init__(self):
        self.platforms = {}
        self.credentials = {}
        self._initialize_platforms()
        
    def _initialize_platforms(self):
        """Initialize platform connections based on environment variables"""
        print("🔗 Initializing social platform connections...")
        
        # Twitter/X Configuration
        twitter_creds = PlatformCredentials(
            platform="twitter",
            api_key=os.getenv("TWITTER_API_KEY", ""),
            api_secret=os.getenv("TWITTER_API_SECRET", ""),
            access_token=os.getenv("TWITTER_ACCESS_TOKEN", ""),
            access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET", ""),
            bearer_token=os.getenv("TWITTER_BEARER_TOKEN", "")
        )
        
        if all([twitter_creds.api_key, twitter_creds.api_secret, 
                twitter_creds.access_token, twitter_creds.access_token_secret]):
            twitter_creds.active = True
            self.credentials["twitter"] = twitter_creds
            self._setup_twitter_client()
            print("✅ Twitter/X configured")
        else:
            print("⚠️ Twitter/X not configured - missing credentials")
            
        # Instagram Configuration (Meta Business API)
        instagram_creds = PlatformCredentials(
            platform="instagram",
            access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
            client_id=os.getenv("INSTAGRAM_CLIENT_ID", ""),
            client_secret=os.getenv("INSTAGRAM_CLIENT_SECRET", "")
        )
        
        if instagram_creds.access_token:
            instagram_creds.active = True
            self.credentials["instagram"] = instagram_creds
            print("✅ Instagram configured")
        else:
            print("⚠️ Instagram not configured - missing access token")
            
        # LinkedIn Configuration
        linkedin_creds = PlatformCredentials(
            platform="linkedin",
            access_token=os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
            client_id=os.getenv("LINKEDIN_CLIENT_ID", ""),
            client_secret=os.getenv("LINKEDIN_CLIENT_SECRET", "")
        )
        
        if linkedin_creds.access_token:
            linkedin_creds.active = True
            self.credentials["linkedin"] = linkedin_creds
            print("✅ LinkedIn configured")
        else:
            print("⚠️ LinkedIn not configured - missing access token")
            
        # YouTube Configuration (Google API)
        youtube_creds = PlatformCredentials(
            platform="youtube",
            api_key=os.getenv("YOUTUBE_API_KEY", ""),
            client_id=os.getenv("YOUTUBE_CLIENT_ID", ""),
            client_secret=os.getenv("YOUTUBE_CLIENT_SECRET", ""),
            access_token=os.getenv("YOUTUBE_ACCESS_TOKEN", "")
        )
        
        if youtube_creds.api_key and youtube_creds.access_token:
            youtube_creds.active = True
            self.credentials["youtube"] = youtube_creds
            print("✅ YouTube configured")
        else:
            print("⚠️ YouTube not configured - missing credentials")
            
    def _setup_twitter_client(self):
        """Setup Twitter API client"""
        try:
            creds = self.credentials["twitter"]
            
            # Setup Tweepy client for API v2
            self.platforms["twitter"] = tweepy.Client(
                bearer_token=creds.bearer_token,
                consumer_key=creds.api_key,
                consumer_secret=creds.api_secret,
                access_token=creds.access_token,
                access_token_secret=creds.access_token_secret,
                wait_on_rate_limit=True
            )
            
            # Test connection
            try:
                user = self.platforms["twitter"].get_me()
                print(f"✅ Twitter connected as @{user.data.username}")
            except Exception as e:
                print(f"⚠️ Twitter connection test failed: {e}")
                self.credentials["twitter"].active = False
                
        except Exception as e:
            print(f"❌ Twitter setup failed: {e}")
            self.credentials["twitter"].active = False

    async def post_content(self, platform: str, content: Dict[str, Any], 
                          images: List[str] = None, scheduled_time: datetime = None) -> Dict[str, Any]:
        """Post content to specified platform"""
        
        if platform not in self.credentials or not self.credentials[platform].active:
            return {
                "success": False,
                "error": f"{platform} not configured or inactive",
                "platform": platform
            }
            
        try:
            if platform == "twitter":
                return await self._post_to_twitter(content, images, scheduled_time)
            elif platform == "instagram":
                return await self._post_to_instagram(content, images, scheduled_time)
            elif platform == "linkedin":
                return await self._post_to_linkedin(content, images, scheduled_time)
            elif platform == "youtube":
                return await self._post_to_youtube(content, images, scheduled_time)
            else:
                return {
                    "success": False,
                    "error": f"Platform {platform} not supported",
                    "platform": platform
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "platform": platform
            }

    async def _post_to_twitter(self, content: Dict[str, Any], images: List[str] = None, 
                              scheduled_time: datetime = None) -> Dict[str, Any]:
        """Post to Twitter/X"""
        try:
            client = self.platforms["twitter"]
            
            # Handle thread posting
            if "thread" in content and content["thread"]:
                return await self._post_twitter_thread(content["thread"], images)
            
            # Single tweet
            tweet_text = content.get("tweet", content.get("text", ""))
            hashtags = content.get("hashtags", [])
            
            # Add hashtags if they fit
            if hashtags:
                hashtag_text = " " + " ".join(hashtags)
                if len(tweet_text + hashtag_text) <= 280:
                    tweet_text += hashtag_text
            
            # Upload images if provided
            media_ids = []
            if images:
                media_ids = await self._upload_twitter_images(images[:4])  # Max 4 images
            
            # Post tweet
            if scheduled_time and scheduled_time > datetime.now():
                # Twitter API v2 doesn't support scheduling directly
                # Would need to implement with a scheduler
                print(f"⚠️ Twitter scheduling not implemented - posting immediately")
            
            response = client.create_tweet(
                text=tweet_text,
                media_ids=media_ids if media_ids else None
            )
            
            return {
                "success": True,
                "platform": "twitter",
                "post_id": response.data["id"],
                "post_url": f"https://twitter.com/user/status/{response.data['id']}",
                "posted_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "platform": "twitter",
                "error": str(e)
            }

    async def _post_twitter_thread(self, thread: List[str], images: List[str] = None) -> Dict[str, Any]:
        """Post a Twitter thread"""
        try:
            client = self.platforms["twitter"]
            thread_ids = []
            
            # Upload images for first tweet if provided
            media_ids = []
            if images:
                media_ids = await self._upload_twitter_images(images[:4])
            
            # Post first tweet
            response = client.create_tweet(
                text=thread[0],
                media_ids=media_ids if media_ids else None
            )
            thread_ids.append(response.data["id"])
            
            # Post subsequent tweets as replies
            for tweet_text in thread[1:]:
                response = client.create_tweet(
                    text=tweet_text,
                    in_reply_to_tweet_id=thread_ids[-1]
                )
                thread_ids.append(response.data["id"])
                
                # Small delay between tweets
                await asyncio.sleep(1)
            
            return {
                "success": True,
                "platform": "twitter",
                "thread_ids": thread_ids,
                "post_url": f"https://twitter.com/user/status/{thread_ids[0]}",
                "thread_length": len(thread_ids),
                "posted_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "platform": "twitter",
                "error": f"Thread posting failed: {str(e)}"
            }

    async def _upload_twitter_images(self, image_paths: List[str]) -> List[str]:
        """Upload images to Twitter and return media IDs"""
        # Note: This would require tweepy v1.1 API for media upload
        # For now, return empty list
        print("⚠️ Twitter image upload not fully implemented")
        return []

    async def _post_to_instagram(self, content: Dict[str, Any], images: List[str] = None, 
                                scheduled_time: datetime = None) -> Dict[str, Any]:
        """Post to Instagram using Meta Business API"""
        try:
            creds = self.credentials["instagram"]
            
            # Instagram requires images for posts
            if not images:
                return {
                    "success": False,
                    "platform": "instagram",
                    "error": "Instagram posts require at least one image"
                }
            
            # Handle carousel posts
            if len(images) > 1:
                return await self._post_instagram_carousel(content, images, scheduled_time)
            
            # Single image post
            caption = content.get("caption", content.get("story_content", ""))
            hashtags = content.get("hashtags", [])
            
            if hashtags:
                caption += "\n\n" + " ".join(hashtags)
            
            # This is a simplified version - actual implementation would use Meta Business API
            print(f"📸 Would post to Instagram: {caption[:50]}... with {len(images)} images")
            
            return {
                "success": True,
                "platform": "instagram",
                "post_id": f"ig_{int(datetime.now().timestamp())}",
                "post_url": "https://instagram.com/p/simulated_post",
                "posted_at": datetime.now().isoformat(),
                "note": "Simulated post - implement Meta Business API for actual posting"
            }
            
        except Exception as e:
            return {
                "success": False,
                "platform": "instagram",
                "error": str(e)
            }

    async def _post_instagram_carousel(self, content: Dict[str, Any], images: List[str], 
                                      scheduled_time: datetime = None) -> Dict[str, Any]:
        """Post Instagram carousel"""
        try:
            slides = content.get("carousel_slides", [])
            caption = content.get("caption", "")
            hashtags = content.get("hashtags", [])
            
            if hashtags:
                caption += "\n\n" + " ".join(hashtags)
            
            print(f"📸 Would post Instagram carousel with {len(images)} images")
            
            return {
                "success": True,
                "platform": "instagram",
                "post_type": "carousel",
                "post_id": f"ig_carousel_{int(datetime.now().timestamp())}",
                "post_url": "https://instagram.com/p/simulated_carousel",
                "slide_count": len(images),
                "posted_at": datetime.now().isoformat(),
                "note": "Simulated carousel - implement Meta Business API for actual posting"
            }
            
        except Exception as e:
            return {
                "success": False,
                "platform": "instagram",
                "error": f"Carousel posting failed: {str(e)}"
            }

    async def _post_to_linkedin(self, content: Dict[str, Any], images: List[str] = None, 
                               scheduled_time: datetime = None) -> Dict[str, Any]:
        """Post to LinkedIn"""
        try:
            post_content = content.get("post_content", content.get("text", ""))
            hashtags = content.get("hashtags", [])
            
            if hashtags:
                post_content += "\n\n" + " ".join(hashtags)
            
            print(f"💼 Would post to LinkedIn: {post_content[:50]}...")
            
            return {
                "success": True,
                "platform": "linkedin",
                "post_id": f"linkedin_{int(datetime.now().timestamp())}",
                "post_url": "https://linkedin.com/posts/simulated_post",
                "posted_at": datetime.now().isoformat(),
                "note": "Simulated post - implement LinkedIn API for actual posting"
            }
            
        except Exception as e:
            return {
                "success": False,
                "platform": "linkedin",
                "error": str(e)
            }

    async def _post_to_youtube(self, content: Dict[str, Any], images: List[str] = None, 
                              scheduled_time: datetime = None) -> Dict[str, Any]:
        """Post to YouTube (typically as community post or scheduled video)"""
        try:
            title = content.get("title", "News Update")
            description = content.get("description", content.get("full_script", ""))
            tags = content.get("hashtags", [])
            
            print(f"🎥 Would post to YouTube: {title}")
            
            return {
                "success": True,
                "platform": "youtube",
                "post_id": f"yt_{int(datetime.now().timestamp())}",
                "post_url": "https://youtube.com/watch?v=simulated_video",
                "post_type": "community_post",  # or "video"
                "posted_at": datetime.now().isoformat(),
                "note": "Simulated post - implement YouTube API for actual posting"
            }
            
        except Exception as e:
            return {
                "success": False,
                "platform": "youtube",
                "error": str(e)
            }

    def get_active_platforms(self) -> List[str]:
        """Get list of active/configured platforms"""
        return [platform for platform, creds in self.credentials.items() if creds.active]

    def get_platform_status(self) -> Dict[str, Any]:
        """Get status of all platforms"""
        status = {}
        
        for platform, creds in self.credentials.items():
            status[platform] = {
                "configured": creds.active,
                "has_credentials": bool(creds.api_key or creds.access_token),
                "last_test": "Not tested"  # Could implement connection testing
            }
            
        return {
            "total_platforms": len(self.credentials),
            "active_platforms": len(self.get_active_platforms()),
            "platform_details": status,
            "supported_platforms": ["twitter", "instagram", "linkedin", "youtube"]
        }

    async def test_platform_connection(self, platform: str) -> Dict[str, Any]:
        """Test connection to a specific platform"""
        if platform not in self.credentials:
            return {"success": False, "error": f"Platform {platform} not configured"}
            
        try:
            if platform == "twitter" and "twitter" in self.platforms:
                user = self.platforms["twitter"].get_me()
                return {
                    "success": True,
                    "platform": platform,
                    "username": user.data.username,
                    "user_id": user.data.id
                }
            else:
                # For other platforms, simulate test
                return {
                    "success": True,
                    "platform": platform,
                    "status": "Connection simulated - implement actual API test"
                }
                
        except Exception as e:
            return {
                "success": False,
                "platform": platform,
                "error": str(e)
            }

    def get_posting_limits(self, platform: str) -> Dict[str, Any]:
        """Get posting limits for platform"""
        limits = {
            "twitter": {
                "posts_per_day": 2400,  # API limit
                "posts_per_hour": 300,
                "character_limit": 280,
                "images_per_post": 4,
                "video_length_seconds": 140
            },
            "instagram": {
                "posts_per_day": 100,  # Unofficial limit
                "posts_per_hour": 10,
                "character_limit": 2200,
                "images_per_carousel": 10,
                "video_length_seconds": 3600
            },
            "linkedin": {
                "posts_per_day": 150,  # Unofficial limit
                "posts_per_hour": 25,
                "character_limit": 3000,
                "images_per_post": 9,
                "video_length_seconds": 600
            },
            "youtube": {
                "uploads_per_day": 6,  # For regular accounts
                "character_limit_title": 100,
                "character_limit_description": 5000,
                "video_length_seconds": 43200,  # 12 hours for verified
                "community_posts_per_day": 50
            }
        }
        
        return limits.get(platform, {"error": f"Limits not defined for {platform}"})