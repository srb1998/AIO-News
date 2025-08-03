# --- START OF FILE telegram_bot.py ---

# telegram_bot.py - Improved media upload with platform-specific buttons

import aiohttp
import asyncio
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from config.settings import settings

class TelegramNotifier:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.social_media_manager = None
        self.polling_offset = 0
        self.max_retries = settings.TELEGRAM_CONFIG["max_retries"]
        self.retry_delay = settings.TELEGRAM_CONFIG["retry_delay_seconds"]
        self.polling_interval = settings.TELEGRAM_CONFIG["polling_interval_seconds"]
        self.chat_id = settings.SERVICE_CONFIG.get("telegram_chat_id", "YOUR_CHAT_ID")
        self._session = None
        self.user_states: Dict[int, Dict] = {}
        self.supported_image_formats = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']
        self.supported_video_formats = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
        self.web_upload_base_url = settings.WEB_UPLOADER_BASE_URL
        self.scheduler_manager = None
        self.manager_agent = None

    def set_social_media_manager(self, social_media_manager):
        self.social_media_manager = social_media_manager

    def set_scheduler_manager(self, scheduler_manager):
        self.scheduler_manager = scheduler_manager

    def set_manager_agent(self, manager_agent):
        self.manager_agent = manager_agent

    def _escape_markdown(self, text: str) -> str:
        """Escape MarkdownV2 special characters"""
        if not isinstance(text, str): 
            return ""
        reserved_chars = r'([_\*\[\]\(\)\~`>#\+\-=|\{\}\.!\\])'
        return re.sub(reserved_chars, r'\\\1', text)
    
    async def send_headlines_notification(self, chat_id: str, top_headlines: List[Dict]) -> Optional[int]:
        """Send headlines notification with fixed emojis"""
        top_headlines = top_headlines or []
        headlines_text = "\n".join(f"• `{self._escape_markdown(headline.get('headline', ''))}`" for headline in top_headlines)
        generated_time = self._escape_markdown(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        batch_message = (
            "📊 *TOP HEADLINES*\n\n"
            f"⏰ *Generated*: {generated_time}\n"
            f"📰 *Top Stories:*\n"
            f"{headlines_text}\n"
            f"📡 *Total Headlines*: {len(top_headlines)}\n"
        )
        return await self._send_message(chat_id, batch_message, None)

    async def send_approval_notification(
        self, story_id: str, workflow_id: str, platforms: List[str], content: str,
        image_suggestions: List[str] = None,
        twitter_content: str = "", instagram_content: str = ""
    ) -> Dict[str, int]:
        """Send approval notification with platform-specific media upload buttons"""
        message_ids = {}
        suggestions_text = "\n".join(f"• {self._escape_markdown(sug)}" for sug in image_suggestions) if image_suggestions else "• AI will generate if none provided"
        
        # Main story approval message
        story_message_text = (
            f"📜 *APPROVAL: Story {story_id}*\n\n"
            f"*Headline:* `{self._escape_markdown(content)}`\n\n"
            f"*Instagram Post:*\n`{self._escape_markdown(instagram_content or 'N/A')}`\n\n"
            f"*Twitter Post:*\n`{self._escape_markdown(twitter_content or 'N/A')}`\n\n"
            f"*Image Suggestions:*\n{suggestions_text}\n"
        )

        story_message_id = await self._send_message(
            self.chat_id, story_message_text,
            {"inline_keyboard": [[
                {"text": "✅ Approve All", "callback_data": f"approve_all_{story_id}"},
                {"text": "❌ Decline All", "callback_data": f"decline_all_{story_id}"}
            ]]}
        )
        
        if not story_message_id:
            print("❌ Failed to send main story approval message. Aborting notification.")
            return {}
            
        message_ids["story"] = story_message_id

        # Platform-specific messages with improved media upload buttons
        for platform in platforms:
            platform_message_text = f"👇 *Actions for {platform.capitalize()} \\(Story {story_id}\\)* 👇"
            message_id = await self._send_message(
                self.chat_id, platform_message_text,
                self._get_platform_buttons(story_id, workflow_id, platform)
            )
            if message_id:
                message_ids[platform] = message_id
            else:
                print(f"⚠️ Failed to send approval message for platform: {platform}")

        return message_ids

    def _get_platform_buttons(self, story_id: str, workflow_id: str, platform: str) -> Dict:
        """Create platform-specific buttons, now with a URL for media upload."""
        # This assumes your manager.py passes the workflow_id down, or you generate one here.
        # For simplicity, let's use the story_id as part of the workflow identifier.

        upload_url = f"{self.web_upload_base_url}/?story_id={story_id}&workflow_id={workflow_id}&platform={platform}"

        return {
            "inline_keyboard": [
                [
                    {"text": f"✅ Approve {platform.capitalize()}", "callback_data": f"approve_{platform}_{story_id}"},
                    {"text": f"❌ Reject {platform.capitalize()}", "callback_data": f"reject_{platform}_{story_id}"}
                ],
                [
                    # Url to upload media directly to the web uploader
                    {"text": f"📁 Upload Media for {platform.capitalize()}", "url": upload_url}
                ]
            ]
        }

    async def _process_update(self, update: Dict):
       """Process incoming updates, now checking for text commands first."""
       try:
           if "message" in update and "text" in update["message"]:
               # Handle text commands before other logic
               is_command_handled = await self.handle_text_command(update["message"])
               if is_command_handled:
                   return
           
           if "callback_query" in update:
               await self.handle_callback_query(update["callback_query"])
       except Exception as e:
           print(f"❌ Error processing update: {e}")

    async def handle_text_command(self, message: Dict) -> bool:
        """Handles text commands for controlling the service."""
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]
        parts = text.split()
        command = parts[0].lower()

        if not self.scheduler_manager or not self.manager_agent:
            # Silently ignore commands if the bot is not fully initialized
            # to prevent user confusion.
            return False

        if command == "/schedule":
            settings_text = self.scheduler_manager.get_current_settings()
            await self._send_message(chat_id, self._escape_markdown(settings_text))
            return True

        elif command == "/setfrequency":
            if len(parts) == 2 and parts[1].isdigit():
                seconds = int(parts[1])
                if self.scheduler_manager.set_frequency(seconds):
                    # --- ADDED CONFIRMATION ---
                    hours = seconds / 3600
                    await self._send_message(chat_id, self._escape_markdown(f"✅ Frequency updated to run every {hours:.1f} hours."))
                else:
                    await self._send_message(chat_id, self._escape_markdown("❌ Invalid frequency. Must be at least 60 seconds."))
            else:
                await self._send_message(chat_id, self._escape_markdown("Usage: `/setfrequency <seconds>` (e.g., 10800 for 3 hours)"))
            return True

        elif command == "/setexclusion":
            if len(parts) == 3:
                start_time, end_time = parts[1], parts[2]
                if self.scheduler_manager.set_exclusion_window(start_time, end_time):

                    await self._send_message(chat_id, self._escape_markdown(f"✅ Exclusion window set to {start_time} - {end_time} IST."))
                else:
                    await self._send_message(chat_id, self._escape_markdown("❌ Invalid format. Use: `/setexclusion HH:MM HH:MM` (e.g., 23:00 08:00)"))
            else:
                await self._send_message(chat_id, self._escape_markdown("Usage: `/setexclusion <start_HH:MM> <end_HH:MM>`"))
            return True
            
        elif command == "/start":
        
            await self._send_message(chat_id, self._escape_markdown("🚀 Instantiating immediate workflow run... Please wait for the results."))
            # Run the workflow in the background so it doesn't block the bot
            asyncio.create_task(self.manager_agent.execute_daily_workflow(posting_mode="hitl"))
            return True
            
        elif command in ["/on", "/off"]:
            is_enabled = command == "/on"
            self.scheduler_manager.toggle_service(is_enabled)
            status = "ENABLED" if is_enabled else "DISABLED"

            await self._send_message(chat_id, self._escape_markdown(f"✅ Scheduled workflows are now **{status}**."))
            return True

        return False 

    async def handle_text_message(self, message: Dict):
        """Handle text messages like /done or /cancel during an upload session"""
        text = message.get("text", "").strip().lower()
        chat_id = message["chat"]["id"]
        state = self.user_states.get(chat_id)

        if not state:
            return

        if text in ["/done", "done", "/finish", "finish"]:
            await self._finish_upload_session(chat_id, state)
        elif text in ["/cancel", "cancel"]:
            await self._cancel_upload_session(chat_id, state)
        else:
            await self._send_message(chat_id, "Please upload your media files or type `/done` to finish, `/cancel` to abort.", None)

    async def send_selection_notification(self, headlines: List[Dict[str, Any]], workflow_id: str) -> Optional[int]:
        """
        Sends a clean, numbered list of headlines, followed by a grid of selection buttons.
        This version correctly escapes all MarkdownV2 special characters.
        """
        if not headlines: return None

        # --- FIX #1: The '!' in the title must be escaped with '\\' ---
        message_text = "📢 **Top Headlines Found\\!**\n\nPlease select stories to investigate:\n\n"
        story_map = {}
        for i, story in enumerate(headlines, 1):
            story_hash = str(abs(hash(story.get('original_title', story.get('headline')))))
            story_map[i] = story_hash
            
            # --- FIX #2: The dynamic headline from the LLM must be escaped ---
            escaped_headline = self._escape_markdown(story['headline'])
            
            # --- FIX #3: The '.' after the number must also be escaped ---
            message_text += f"*{i}\\.* {escaped_headline}\n"
        
        # This first message will now send correctly
        await self._send_message(self.chat_id, message_text)

        # The button grid logic is fine, but we'll escape its title for safety too.
        rows = []
        buttons = []
        for i in range(1, len(headlines) + 1):
            story_hash = story_map[i]
            buttons.append({"text": f"✅ {i}", "callback_data": f"select_{workflow_id}_{story_hash}"})
            if len(buttons) == 5:
                rows.append(buttons)
                buttons = []
        if buttons: rows.append(buttons)
        
        rows.append([{"text": "🚀 Select All", "callback_data": f"select_{workflow_id}_all"}])

        reply_markup = {"inline_keyboard": rows}
        # Escape the title of the second message as well for robustness
        button_grid_title = self._escape_markdown("Select stories for Gate 2:")
        button_grid_title = f"*{button_grid_title}*"
        
        return await self._send_message(self.chat_id, button_grid_title, reply_markup)

    async def send_workflow_summary_notification(self, workflow_id: str, summary_url: str):
        """
        Sends a Telegram message with a direct link to the uploaded workflow summary JSON.
        """
        if not summary_url:
            print("⚠️ Workflow summary URL is empty, skipping Telegram notification.")
            return

        # Create a message with a Markdown-formatted link
        message = (
            f"✅ *Workflow Run Complete*\n\n"
            f"🔗 [Click here to view the full JSON summary]({summary_url})"
        )

        try:
            await self._send_message(self.chat_id, message)
            print(f"📱 Sent workflow summary notification for {workflow_id}")
        except Exception as e:
            print(f"❌ Failed to send workflow summary notification: {e}")


    async def handle_callback_query(self, callback_query: Dict):
        """Handles all button clicks, including the special 'select_all' case."""
        callback_data = callback_query.get("data", "")
        print(f"🔄 Processing callback: {callback_data}")
        try:
            parts = callback_data.split("_")
            action = parts[0]

            if action == "select":
                if not self.manager_agent: return
                
                workflow_id = "_".join(parts[1:-1])
                story_identifier = parts[-1]

                if story_identifier == "all":
                    success = self.manager_agent.register_user_selection(workflow_id, "all")
                    if success:
                        await self.answer_callback_query(callback_query["id"], "✅ All stories selected!")
                    else:
                        await self.answer_callback_query(callback_query["id"], "⚠️ Selection failed.")
                else: # Handle single story selection
                    story_hash = story_identifier
                    if self.manager_agent.register_user_selection(workflow_id, story_hash):
                        await self.answer_callback_query(callback_query["id"], f"✅ Story Selected!")
                    else:
                        await self.answer_callback_query(callback_query["id"], "⚠️ Selection failed.")
                return

            if not self.social_media_manager:
                await self.answer_callback_query(callback_query["id"], "Social Media Manager not initialized")
                return
            
            story_id = parts[-1]
            platform = None
            action_str = "_".join(parts[:-1])
            if action_str in ["approve_all", "decline_all"]:
                action = action_str
            elif parts[0] in ["approve", "reject", "decline"]:
                action, platform = parts[0], parts[1]

            await self.answer_callback_query(callback_query["id"], f"Processing '{action}'...")
            await self.social_media_manager.handle_telegram_callback(story_id, platform, action)

        except Exception as e:
            print(f"❌ Error handling callback query: {e}")
            await self.answer_callback_query(callback_query["id"], "Error processing request")

    async def _start_media_upload_session(self, callback_query: Dict, platform: str, story_id: str):
        """Start a media upload session for a specific platform"""
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]
        
        self.user_states[chat_id] = {
            "platform": platform, "story_id": story_id, "message_id": message_id,
            "uploaded_files": [], "session_start": datetime.now()
        }
        
        instructions = (
            f"📁 *Media Upload for {platform.capitalize()} \\(Story {story_id}\\)*\n\n"
            f"Please send your images, videos, or documents now\\. You can send multiple files\\.\n\n"
            f"Type `/done` or click the button when you are finished\\.\n"
            f"Type `/cancel` to abort\\."
        )
        
        await self.update_message(
            chat_id, message_id, instructions,
            {"inline_keyboard": [[
                {"text": "✅ Done Uploading", "callback_data": f"done_upload_{platform}_{story_id}"},
                {"text": "❌ Cancel Upload", "callback_data": f"cancel_upload_{platform}_{story_id}"}
            ]]}
        )
        await self.answer_callback_query(callback_query["id"], f"Ready for media for {platform.capitalize()}")

    async def _finish_upload_session(self, chat_id: int, state: Dict):
        """Finish the upload session and process the collected files"""
        if not state: return
            
        platform, story_id, msg_id, uploaded_files = state.get("platform"), state.get("story_id"), state.get("message_id"), state.get("uploaded_files", [])
        self.user_states.pop(chat_id, None)
        
        if uploaded_files:
            await self.social_media_manager.handle_telegram_callback(
                story_id, platform, "add_media_batch", uploaded_files
            )
            summary_text = f"✅ *Upload Complete for {platform.capitalize()}* \\({len(uploaded_files)} files\\)\\. Ready for approval\\!"
        else:
            summary_text = f"🤷 *Upload session for {platform.capitalize()} ended*\\. No files were uploaded\\."
        
        await self.update_message(chat_id, msg_id, summary_text, self._get_platform_buttons(story_id, platform))

    async def _cancel_upload_session(self, chat_id: int, state: Dict):
        """Cancel the upload session and clean up"""
        if not state: return
            
        platform, story_id, msg_id = state.get("platform"), state.get("story_id"), state.get("message_id")
        self.user_states.pop(chat_id, None)
        
        # Optionally, delete temp files if any were downloaded before cancelling
        for file_info in state.get("uploaded_files", []):
            if os.path.exists(file_info["path"]):
                os.remove(file_info["path"])

        cancel_text = f"❌ *Upload Cancelled* for {platform.capitalize()} \\(Story {story_id}\\)\\."
        await self.update_message(chat_id, msg_id, cancel_text, self._get_platform_buttons(story_id, platform))

    async def handle_media_upload(self, message: Dict):
        """Handle a single media file upload during a session"""
        chat_id = message["chat"]["id"]
        state = self.user_states.get(chat_id)
        if not state: return

        story_id, platform = state["story_id"], state["platform"]
        file_id, file_name, media_type = None, None, None

        if message.get("photo"):
            file_id = message["photo"][-1]["file_id"]
            media_type = "image"
            file_name = f"image_{file_id}.jpg"
        elif message.get("video"):
            file_id = message["video"]["file_id"]
            media_type = "video"
            file_name = message["video"].get("file_name", f"video_{file_id}.mp4")
        elif message.get("document"):
            doc = message["document"]
            file_id, file_name = doc["file_id"], doc.get("file_name", f"doc_{file_id}")
            if any(file_name.lower().endswith(ext) for ext in self.supported_image_formats): media_type = "image"
            elif any(file_name.lower().endswith(ext) for ext in self.supported_video_formats): media_type = "video"
            else: media_type = "document"

        if file_id and media_type:
            media_path = await self._download_file(file_id, story_id, platform, file_name)
            if media_path:
                state["uploaded_files"].append({"path": media_path, "type": media_type, "name": file_name})
                await self._send_message(chat_id, f"✅ Received `{self._escape_markdown(file_name)}`\\. Send more or type `/done`\\.", None)
            else:
                await self._send_message(chat_id, f"❌ Failed to download `{self._escape_markdown(file_name)}`\\.", None)
        else:
            await self._send_message(chat_id, "❌ Unsupported file type. Please upload standard image or video formats.", None)

    async def _download_file(self, file_id: str, story_id: str, platform: str, file_name: str) -> Optional[str]:
        """Download a file from Telegram's servers to a temporary local path"""
        if not self._session: self._session = aiohttp.ClientSession()
        try:
            async with self._session.get(f"{self.base_url}/getFile", params={"file_id": file_id}) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    print(f"❌ Telegram getFile failed: {result.get('description')}")
                    return None
                
                tg_file_path = result["result"]["file_path"]
                download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{tg_file_path}"
                
                save_dir = os.path.join("temp_media", story_id, platform)
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, file_name)
                
                async with self._session.get(download_url) as file_resp:
                    if file_resp.status == 200:
                        with open(save_path, 'wb') as f:
                            f.write(await file_resp.read())
                        print(f"✅ Downloaded file to {save_path}")
                        return save_path
                    else:
                        print(f"❌ File download failed with status {file_resp.status}")
                        return None
        except Exception as e:
            print(f"❌ Download error: {e}")
            return None
    async def _send_message(self, chat_id: str, text: str, reply_markup: Optional[Dict] = None) -> Optional[int]:
        if not self._session: self._session = aiohttp.ClientSession()
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"}
        if reply_markup: payload["reply_markup"] = reply_markup
        
        try:
            async with self._session.post(f"{self.base_url}/sendMessage", json=payload) as response:
                result = await response.json()
                if result.get("ok"): return result["result"]["message_id"]
                print(f"❌ Telegram send_message failed: {result}")
                return None
        except Exception as e:
            print(f"❌ Telegram send_message error: {e}")
            return None

    async def update_message(self, chat_id: str, message_id: int, text: str, reply_markup: Optional[Dict] = None) -> bool:
        if not self._session: self._session = aiohttp.ClientSession()
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "MarkdownV2"}
        if reply_markup: payload["reply_markup"] = reply_markup
        
        try:
            async with self._session.post(f"{self.base_url}/editMessageText", json=payload) as response:
                result = await response.json()
                if result.get("ok") or "message is not modified" in str(result): return True
                print(f"❌ Telegram update_message failed: {result}")
                return False
        except Exception as e:
            print(f"❌ Telegram update_message error: {e}")
            return False

    async def answer_callback_query(self, callback_query_id: str, text: str):
        if not self._session: self._session = aiohttp.Clien_session()
        try:
            await self._session.post(f"{self.base_url}/answerCallbackQuery", json={"callback_query_id": callback_query_id, "text": text})
        except Exception as e:
            print(f"❌ Failed to answer callback query: {e}")

    async def start_polling(self):
        print("📡 Starting Telegram polling...")
        if not self._session: self._session = aiohttp.ClientSession()
        while True:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self.polling_offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]}
                async with self._session.get(url, params=params) as response:
                    result = await response.json()
                    if result.get("ok"):
                        for update in result.get("result", []):
                            self.polling_offset = update["update_id"] + 1
                            await self._process_update(update)
                    else:
                        print(f"❌ Polling failed: {result}")
            except Exception as e:
                print(f"❌ Telegram polling error: {e}")
                await asyncio.sleep(5)

    async def close(self):
        if self._session: await self._session.close()