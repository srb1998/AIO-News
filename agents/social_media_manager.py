# social_media_manager.py

import asyncio
import os
from aiohttp import request
import cloudinary
import cloudinary.uploader
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from services.telegram_bot import TelegramNotifier
from services.social_platforms import SocialPlatformManager
from core.approval_queue import ApprovalQueue
from config.settings import settings
from services.image_generator import ImageGenerator
from services.placid_generator import PlacidImageGenerator

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

class SocialMediaManagerAgent:
    def __init__(self, telegram_bot: TelegramNotifier):
        self.name = "SocialMediaManager"
        self.telegram_bot = telegram_bot
        self.approval_queue = ApprovalQueue()
        self.image_gen = PlacidImageGenerator()
        self.platforms = ["twitter", "instagram", "youtube"]
        self.chat_id = settings.SERVICE_CONFIG.get("telegram_chat_id", "YOUR_CHAT_ID")
        self.max_media_per_post = 10
        
        self.social_platform_manager = SocialPlatformManager()
        self.story_locks = {}
        self.story_locks_lock = asyncio.Lock()
    
    def _format_post_content(self, platform: str, headline: str, platform_content: str = "", hashtags: List[str] = None) -> str:
        """
        Format the final post content with headline, platform-specific content, and hashtags
        """
        if not hashtags:
            hashtags = []
        
        # Start with platform-specific content if available, otherwise use headline
        if platform_content and platform_content.strip():
            content = platform_content.strip()
        else:
            content = headline.strip()
        
        # Add hashtags at the end
        if hashtags:
            hashtag_string = " ".join([f"#{tag.strip().replace('#', '')}" for tag in hashtags if tag.strip()])
            if hashtag_string:
                content = f"{content}\n\n{hashtag_string}"
        
        return content
    
    async def handle_webhook_upload(self, story_id: str, platform: str, media_url: str, resource_type: str, workflow_id: str):
        """
        Processes an uploaded file with robust, race-condition-safe logic
        that supports multi-image carousels.
        """
        print(f"Handling webhook for {platform}/{story_id}: {media_url}")
        
        lock_key = f"{story_id}_{platform}"

        # The FileLock is essential to prevent race conditions
        async with self.story_locks_lock:
            if lock_key not in self.story_locks:
                self.story_locks[lock_key] = asyncio.Lock()

        story_lock = self.story_locks[lock_key]
        
        async with story_lock:
            request = self.approval_queue.get_request(story_id, platform)
            if not request:
                print(f"⚠️ Webhook Error: No pending request found for {platform}/{story_id}")
                return

            existing_media = request.get("images", []) + request.get("videos", [])
            if media_url in existing_media:
                print(f"Duplicate media URL detected: {media_url}. Skipping.")
                return
            
            is_first_media_claim = (resource_type in ["image", "video"]) and not request.get("headline_applied", False)

            if is_first_media_claim:
                print("This is the first image to be processed. Applying headline overlay...")
                
                background_for_headline = media_url if resource_type == "image" else "URL_TO_A_DEFAULT_BACKGROUND_IMAGE"

                processed_url = await self.image_gen.apply_headline_to_image(
                    image_path_or_url=media_url,
                    story_id=story_id,
                    platform=platform,
                    headline=request["content"],
                    subheadline=request.get("sub_content", ""),
                    workflow_id=workflow_id
                )

                final_url_to_add = processed_url or media_url

                if resource_type == "video":
                    self.approval_queue.update_media(story_id, platform, "videos", media_url)
            
                self.approval_queue.set_processed_first_image(story_id, platform, final_url_to_add)
                print(f"✅ First image processed and PREPENDED for {platform}/{story_id}.")

            else:
                print(f"This is a subsequent media item. Appending to queue...")
                db_media_type = "videos" if resource_type == "video" else "images"
                
                # The standard update_media function APPENDS the media.
                self.approval_queue.update_media(story_id, platform, db_media_type, media_url)
                print(f"✅ Media for {platform}/{story_id} APPENDED to queue.")

    async def process_scripts_for_posting(self, script_packages: List[Dict], workflow_id: str, posting_mode: str = "hitl") -> Dict:
        results = {"success": True, "posts_processed": 0, "posts_pending": 0, "telegram_notifications_sent": 0, "errors": []}
        for script_package in script_packages:
            story_result = await self._process_single_story_package(script_package, workflow_id)
            results["posts_processed"] += story_result.get("platforms_processed", 0)
            results["posts_pending"] += story_result.get("pending_approvals", 0)
            if story_result.get("telegram_sent"): results["telegram_notifications_sent"] += 1
            results["errors"].extend(story_result.get("errors", []))
        return results

    async def _process_single_story_package(self, script_package: Dict, workflow_id: str) -> Dict:
        """Processes a single story, creating approval requests with platform-specific content and hashtags."""
        story_id = str(script_package.get("story_id", f"story_{int(datetime.now().timestamp())}"))
        headline = script_package.get("original_headline", "News Update")
        summary = script_package.get("research_summary", "")
        subheadline = script_package.get("subheadline", "")
        # Extract platform-specific content and hashtags
        twitter_data = script_package.get("twitter", {})
        instagram_data = script_package.get("instagram", {})
        
        twitter_content = twitter_data.get("tweet", "")
        twitter_hashtags = twitter_data.get("hashtags", [])
        
        instagram_content = instagram_data.get("story_content", "")
        instagram_hashtags = instagram_data.get("hashtags", [])

        image_suggestions = list(set(
            twitter_data.get("image_suggestions", []) +
            instagram_data.get("image_suggestions", [])
        ))[:2]

        # Send Telegram notification
        message_ids = await self.telegram_bot.send_approval_notification(
            story_id=story_id,
            workflow_id=workflow_id,
            platforms=self.platforms,
            content=headline,
            image_suggestions=image_suggestions,
            twitter_content=twitter_content,
            instagram_content=instagram_content,
            hashtags=instagram_hashtags
        )

        # Create approval requests with platform-specific data
        for platform in self.platforms:
            platform_content = ""
            platform_hashtags = []
            
            if platform == "twitter":
                platform_content = twitter_content
                platform_hashtags = twitter_hashtags
            elif platform == "instagram":
                platform_content = instagram_content
                platform_hashtags = instagram_hashtags
            # YouTube can be handled similarly when needed
            
            self.approval_queue.add_request(
                story_id=story_id, 
                platform=platform, 
                workflow_id=workflow_id, 
                content=headline,
                sub_content=subheadline,
                images=[], 
                videos=[],
                message_ids=message_ids, 
                created_at=datetime.now(),
                platform_content=platform_content,
                hashtags=platform_hashtags
            )

        return {
            "story_id": story_id, "platforms_processed": len(self.platforms),
            "pending_approvals": len(self.platforms), "telegram_sent": bool(message_ids)
        }

    async def handle_telegram_callback(self, story_id: str, platform: Optional[str], action: str):
        """
        Handles approve/reject actions.
        On approval, it now sets the status to 'APPROVED' for the scheduler to pick up.
        It no longer calls the posting function directly.
        """
        print(f"Handling callback: story_id='{story_id}', platform='{platform}', action='{action}'")

        if action in ["approve_all", "decline_all"]:
            platforms_to_process = self.platforms
        elif platform:
            platforms_to_process = [platform]
        else:
            print(f"⚠️ Could not determine platforms for action '{action}'. Aborting.")
            return

        for p in platforms_to_process:
            request = self.approval_queue.get_request(story_id, p)
            if not request or request["status"] != "PENDING":
                print(f"⚠️ Request for {story_id}/{p} not found or not pending. Ignoring action.")
                continue

            if action.startswith("approve"):
                # 1. Update status to APPROVED
                self.approval_queue.update_status(story_id, p, "APPROVED")
                
                # 2. Notify user that it's scheduled, not posted
                msg_id = request["message_ids"].get(p)
                if msg_id:
                    text = self.telegram_bot._escape_markdown(f"✅ Approved & **scheduled** for posting to {p.capitalize()}!")
                    await self.telegram_bot.update_message(self.chat_id, msg_id, text, {"inline_keyboard": []})
                print(f"✅ Story {story_id}/{p} marked as APPROVED and is now in the posting queue.")

            elif action.startswith("decline") or action.startswith("reject"):
                self.approval_queue.update_status(story_id, p, "REJECTED")
                msg_id = request["message_ids"].get(p)
                if msg_id:
                    text = self.telegram_bot._escape_markdown(f"❌ Rejected {p.capitalize()} (Story {story_id})")
                    await self.telegram_bot.update_message(self.chat_id, msg_id, text, {"inline_keyboard": []})

    async def _handle_media_add(self, story_id: str, platform: str, media_info: Dict, workflow_id: str):
        """Process a single uploaded file: apply headline or upload directly."""
        media_path = media_info["path"]
        media_type = media_info["type"]
        
        request = self.approval_queue.get_request(story_id, platform)
        if not request: return

        # The first uploaded image gets the headline treatment
        is_first_image = media_type == "image" and not request.get("images")
        final_media_url = ""

        try:
            if is_first_image:
                print(f"Applying headline to first image: {media_path}")
                final_media_url = await self.image_gen.apply_headline_to_image(
                    image_path_or_url=media_path, story_id=story_id, platform=platform,
                    headline=request["content"], subheadline=request.get("sub_content", "")
                )
            else:
                print(f"Uploading additional media: {media_path}")
                resource_type = "video" if media_type == "video" else "image"
                upload_result = cloudinary.uploader.upload(
                    media_path, folder=f"news/processed/{workflow_id}/{story_id}/{platform}", resource_type=resource_type
                )
                final_media_url = upload_result.get("secure_url", "")

            if final_media_url:
                db_media_type = "videos" if media_type == "video" else "images"
                self.approval_queue.update_media(story_id, platform, db_media_type, final_media_url)
                print(f"✅ Successfully processed and stored URL: {final_media_url}")

        except Exception as e:
            print(f"❌ Failed to process media {media_path}: {e}")
        finally:
            # Clean up the temporary local file
            if os.path.exists(media_path):
                os.remove(media_path)

    async def _handle_approval(self, story_id: str, platform: str):
        request = self.approval_queue.get_request(story_id, platform)
        if not request: return

        # If no media was provided by the user, generate an AI image as a fallback
        if not request["images"] and not request["videos"]:
            workflow_id = request.get("workflow_id", "unknown_workflow")
            msg = self.telegram_bot._escape_markdown(f"⏳ Approved! No media found. Generating AI image for {platform.capitalize()}...")
            await self.telegram_bot.update_message(self.chat_id, request["message_ids"].get(platform), msg, {"inline_keyboard": []})
            
            ai_image_url = await self.image_gen.generate_social_image(
                headline=request["content"], summary=request.get("sub_content", ""),
                story_id=story_id, platform=platform, workflow_id=workflow_id
            )
            if ai_image_url:
                self.approval_queue.update_media(story_id, platform, "images", ai_image_url)
            else:
                fail_msg = self.telegram_bot._escape_markdown(f"⚠️ AI image generation failed for {platform.capitalize()}. Post not sent.")
                await self.telegram_bot.update_message(self.chat_id, request["message_ids"].get(platform), fail_msg, {"inline_keyboard": []})
                self.approval_queue.update_status(story_id, platform, "FAILED")
                return

        # Proceed with posting
        self.approval_queue.update_status(story_id, platform, "APPROVED")
        await self._execute_approved_post(story_id, platform)
        
        success_msg = self.telegram_bot._escape_markdown(f"✅ Approved and sending to {platform.capitalize()} (Story {story_id})")
        await self.telegram_bot.update_message(self.chat_id, request["message_ids"].get(platform), success_msg, {"inline_keyboard": []})

    async def _execute_approved_post(self, story_id: str, platform: str):
        
        request = self.approval_queue.get_request(story_id, platform)
        print(f"🔍 DEBUG: Executing post for {story_id}/{platform}")
        print(f"   Status: {request.get('status')}")
        print(f"   Images: {request.get('images', [])}")
        print(f"   Videos: {request.get('videos', [])}")
        print(f"   Platform content: {request.get('platform_content', '')[:100]}")
        print(f"   Hashtags: {request.get('hashtags', [])}")
        if not request or request["status"] not in ["APPROVED", "POSTING"]:
            print(f"⚠️ Post {story_id}/{platform} is not in a postable state. Status: {request.get('status')}. Aborting.")
            return

        # Extract content and media
        headline = request["content"]
        platform_content = request.get("platform_content", "")
        hashtags = request.get("hashtags", [])
        images = request.get("images", [])
        videos = request.get("videos", [])

        # Format the final content with hashtags
        final_content = self._format_post_content(platform, headline, platform_content, hashtags)
        print(f"🚀 REAL POSTING to {platform.upper()}:")
        print(f"   Final Content: {final_content[:200]}...")
        print(f"   Images: {len(images)} files")
        print(f"   Videos: {len(videos)} files")
        print(f"   Hashtags: {hashtags}")

        if not final_content or final_content.strip() == "":
            print(f"❌ ERROR: Empty caption for {platform}/{story_id}")
            print(f"   Headline: {headline}")
            print(f"   Platform content: {platform_content}")
            print(f"   Hashtags: {hashtags}")
            return

        try:
            # Use the real social platform manager with formatted content
            success = await self.social_platform_manager.post_to_platform(
                platform=platform,
                images=images,
                videos=videos,
                content=final_content  # Now includes platform content + hashtags
            )
            
            if success:
                self.approval_queue.update_status(story_id, platform, "POSTED")
                print(f"✅ Successfully posted story {story_id} to {platform}")
                
                # Send success notification to Telegram
                msg_id = request["message_ids"].get(platform)
                if msg_id:
                    success_msg = self.telegram_bot._escape_markdown(f"🎉 Successfully posted to {platform.capitalize()}! (Story {story_id})")
                    await self.telegram_bot.update_message(self.chat_id, msg_id, success_msg, {"inline_keyboard": []})
            else:
                self.approval_queue.update_status(story_id, platform, "FAILED")
                print(f"❌ Failed to post story {story_id} to {platform}")
                
                # Send failure notification to Telegram
                msg_id = request["message_ids"].get(platform)
                if msg_id:
                    fail_msg = self.telegram_bot._escape_markdown(f"❌ Failed to post to {platform.capitalize()} (Story {story_id})")
                    await self.telegram_bot.update_message(self.chat_id, msg_id, fail_msg, {"inline_keyboard": []})

        except Exception as e:
            print(f"❌ Exception while posting to {platform}: {e}")
            self.approval_queue.update_status(story_id, platform, "FAILED")
            
            # Send error notification to Telegram
            msg_id = request["message_ids"].get(platform)
            if msg_id:
                error_msg = self.telegram_bot._escape_markdown(f"❌ Error posting to {platform.capitalize()}: {str(e)[:50]}...")
                await self.telegram_bot.update_message(self.chat_id, msg_id, error_msg, {"inline_keyboard": []})

    async def check_timeouts(self):
        for request in self.approval_queue.get_timed_out_requests():
            story_id, platform = request["story_id"], request["platform"]
            msg_id = request["message_ids"].get(platform)
            if not msg_id:
                print(f"🔍 Timeout check error: '{platform}' message ID missing.")
                continue
            print(f"🔍 Timeout detected for Story {story_id} on {platform}. Auto-approving...")
            msg = self.telegram_bot._escape_markdown(f"🔍 Timeout! Auto-approving {platform.capitalize()}.")
            await self.telegram_bot.update_message(self.chat_id, msg_id, msg, {"inline_keyboard": []})
            await self._handle_approval(story_id, platform)

    def get_posting_status(self) -> Dict:
        """Enhanced status including social platform limits"""
        pending = self.approval_queue.get_all_pending()
        
        # Get platform status (async call wrapped)
        platform_status = {}
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, we can't call get_all_status directly
                platform_status = {"note": "Platform limits available via separate API call"}
            else:
                platform_status = loop.run_until_complete(self.social_platform_manager.get_all_status())
        except:
            platform_status = {"error": "Could not fetch platform status"}
        
        return {
            "total_requests": len(self.approval_queue.queue),
            "pending_approval": len(pending),
            "platforms_configured": self.platforms,
            "social_platforms": platform_status
        }

    async def get_story_details(self, story_id: str) -> Optional[Dict]:
        request = self.approval_queue.get_request(story_id, "twitter")
        if request:
            return {"content": request["content"], "sub_content": request.get("sub_content", "")}
        return None
    
    async def get_platform_status(self) -> Dict:
        """Get detailed platform status including posting limits"""
        return await self.social_platform_manager.get_all_status()
    
    async def close(self):
        """Clean up resources"""
        await self.social_platform_manager.close_all_sessions()