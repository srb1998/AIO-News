# social_media_manager.py

import asyncio
import os
import cloudinary
import cloudinary.uploader
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from services.telegram_bot import TelegramNotifier
from core.approval_queue import ApprovalQueue
from config.settings import settings
from services.image_generator import ImageGenerator

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
        self.image_gen = ImageGenerator()
        self.platforms = ["twitter", "instagram", "youtube"]
        self.chat_id = settings.SERVICE_CONFIG.get("telegram_chat_id", "YOUR_CHAT_ID")
        self.max_media_per_post = 10
    
    async def handle_webhook_upload(self, story_id: str, platform: str, media_url: str, resource_type: str, workflow_id: str):
        """
        Processes a file uploaded via the web widget and notified via webhook.
        Applies headline to the first image and updates the approval queue.
        """
        print(f"Handling webhook upload for {platform}/{story_id}: {media_url} in workflow {workflow_id}")
        request = self.approval_queue.get_request(story_id, platform)
        if not request:
            print(f"⚠️ Webhook Error: No pending request found for {platform}/{story_id}")
            return
    
        final_media_url = media_url
        is_first_image = resource_type == "image" and not request.get("images")
    
        if is_first_image:
            print(f"This is the first image. Applying headline overlay...")
            # The image is already in Cloudinary, so we pass its URL to the generator
            processed_url = await self.image_gen.apply_headline_to_image(
                image_path_or_url=media_url,
                story_id=story_id,
                platform=platform,
                headline=request["content"],
                subheadline=request.get("sub_content", ""),
                workflow_id=workflow_id
            )
            if processed_url:
                final_media_url = processed_url
            else:
                print("⚠️ Headline overlay failed. Using original image.")
    
        # Update the approval queue with the final URL
        db_media_type = "videos" if resource_type == "video" else "images"
        self.approval_queue.update_media(story_id, platform, db_media_type, final_media_url)
        print(f"✅ Media for {platform}/{story_id} updated in queue.")

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
        """Processes a single story, creating approval requests with the correct workflow_id."""
        story_id = str(script_package.get("story_id", f"story_{int(datetime.now().timestamp())}"))
        headline = script_package.get("original_headline", "News Update")
        summary = script_package.get("research_summary", "")

        image_suggestions = list(set(
            script_package.get("twitter", {}).get("image_suggestions", []) +
            script_package.get("instagram", {}).get("image_suggestions", [])
        ))[:3]

        message_ids = await self.telegram_bot.send_approval_notification(
            story_id=story_id,
            workflow_id=workflow_id,
            platforms=self.platforms,
            content=headline,
            image_suggestions=image_suggestions,
            twitter_content=script_package.get("twitter", {}).get("tweet", ""),
            instagram_content=script_package.get("instagram", {}).get("story_content", "")
        )

        for platform in self.platforms:
            self.approval_queue.add_request(
                story_id=story_id, platform=platform, workflow_id=workflow_id, content=headline,
                sub_content=summary, images=[], videos=[],
                message_ids=message_ids, created_at=datetime.now()
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
        if request and request["status"] == "APPROVED":
            success = await self._post_to_platform(platform, request["content"], request["images"], request["videos"])
            status = "POSTED" if success else "FAILED"
            self.approval_queue.update_status(story_id, platform, status)
            print(f"Post execution for {story_id} on {platform} finished with status: {status}")

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

    async def _post_to_platform(self, platform: str, content: str, images: List[str], videos: List[str]) -> bool:
        print(f"POSTING to {platform.upper()}:\nContent: {content[:100]}...\nImages: {images}\nVideos: {videos}")
        await asyncio.sleep(2)
        print(f"Successfully posted to {platform}.")
        return True

    def get_posting_status(self) -> Dict:
        pending = self.approval_queue.get_all_pending()
        return {
            "total_requests": len(self.approval_queue.queue),
            "pending_approval": len(pending),
            "platforms_configured": self.platforms,
        }

    async def get_story_details(self, story_id: str) -> Optional[Dict]:
        request = self.approval_queue.get_request(story_id, "twitter")
        if request:
            return {"content": request["content"], "sub_content": request.get("sub_content", "")}
        return None