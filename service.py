import asyncio
import signal
import sys
import random
import uvicorn
from datetime import datetime
from typing import Dict, Any

from agents.manager import ManagerAgent
from agents.social_media_manager import SocialMediaManagerAgent
from core.approval_queue import ApprovalQueue
from services.telegram_bot import TelegramNotifier
from config.settings import settings
import os

# Import the FastAPI app and the setter function from our webhook server file
from webhook_server import app as webhook_app, set_social_media_manager

class NewsAgencyService:
    """
    The main orchestrator for the AIO-News service. This class manages all
    background tasks, including content generation, user interaction via Telegram,
    and intelligent, paced posting to social media.
    """
    def __init__(self):
        print("Initializing AIO-News Service...")
        # --- 1. Initialize Core Components ---
        self.manager = ManagerAgent()
        self.approval_queue = ApprovalQueue()
        self.telegram_bot = TelegramNotifier(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
        )
        self.social_media_manager = SocialMediaManagerAgent(telegram_bot=self.telegram_bot)

        # --- 2. Wire Components Together ---
        self.telegram_bot.set_social_media_manager(self.social_media_manager)
        set_social_media_manager(self.social_media_manager) # Inject instance into webhook server

        # --- 3. Load Configuration ---
        self.daily_workflow_interval = settings.WORKFLOW_TIMING["daily_workflow_interval"]
        self.breaking_news_interval = settings.WORKFLOW_TIMING["breaking_news_check_interval"]
        self.posting_scheduler_interval = settings.WORKFLOW_TIMING["posting_scheduler_interval_seconds"]
        self.min_posting_delay = settings.WORKFLOW_TIMING["min_posting_delay_seconds"]
        self.max_posting_delay = settings.WORKFLOW_TIMING["max_posting_delay_seconds"]
        self.timeout_check_interval = 60  # Check for timeouts every 60 seconds

        # --- 4. Initialize State ---
        self.is_running = False
        self.background_tasks = set()

    async def start_service(self):
        """Starts all concurrent loops and keeps the service alive."""
        self.is_running = True
        self._setup_signal_handlers()
        print("🚀 Starting all service components...")

        # Configure the Uvicorn server to run our FastAPI app
        uvicorn_config = uvicorn.Config(webhook_app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(uvicorn_config)

        # List of all concurrent tasks to run
        loops_to_run = [
            server.serve(),
            self.telegram_bot.start_polling(),
            self._daily_workflow_loop(),
            self._breaking_news_loop(),
            self._posting_scheduler_loop(),
            self._check_timeouts_loop()
        ]

        # Create and manage these tasks
        for loop in loops_to_run:
            task = asyncio.create_task(loop)
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)

        print(f"✅ Service is now fully operational with {len(self.background_tasks)} components running.")
        
        # This will keep the service running until a shutdown signal is received
        await asyncio.gather(*self.background_tasks)

    async def _daily_workflow_loop(self):
        """Periodically runs the main batch workflow to find multiple stories."""
        print("🔄 Daily Workflow Loop: Started.")
        while self.is_running:
            try:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] DAILY: Kicking off scheduled batch workflow...")
                await self.manager.execute_daily_workflow(posting_mode="hitl")
            except Exception as e:
                print(f"❌ ERROR in Daily Workflow Loop: {e}")
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DAILY: Run complete. Next run in {self.daily_workflow_interval / 3600:.1f} hours.")
            await asyncio.sleep(self.daily_workflow_interval)

    async def _breaking_news_loop(self):
        """Frequently checks for high-priority breaking news."""
        print("🚨 Breaking News Monitor: Started.")
        while self.is_running:
            try:
                # This small sleep prevents the first run from happening at the exact same second as the daily workflow
                await asyncio.sleep(10)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] BREAKING: Checking for urgent stories...")
                await self.manager.execute_breaking_news_workflow(posting_mode="hitl")
            except Exception as e:
                print(f"❌ ERROR in Breaking News Loop: {e}")
            
            await asyncio.sleep(self.breaking_news_interval)

    async def _posting_scheduler_loop(self):
        """The 'Pacer'. Checks for approved posts and publishes them one by one at a natural pace."""
        print("✍️ Posting Scheduler Loop: Started.")
        while self.is_running:
            try:
                next_post = self.approval_queue.get_next_approved_post()
                if next_post:
                    story_id = next_post['story_id']
                    platform = next_post['platform']
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] SCHEDULER: Found approved post to publish: {story_id}/{platform}.")
                    
                    # The SocialMediaManager already contains the logic to post and update status
                    await self.social_media_manager._handle_approval(story_id, platform)
                    
                    delay = random.randint(self.min_posting_delay, self.max_posting_delay)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] SCHEDULER: Post published. Waiting for {delay / 60:.1f} minutes before checking for the next one.")
                    await asyncio.sleep(delay)
                else:
                    # If no posts are waiting, just check again after the standard interval
                    await asyncio.sleep(self.posting_scheduler_interval)
            except Exception as e:
                print(f"❌ ERROR in Posting Scheduler Loop: {e}")
                await asyncio.sleep(60) # Wait a minute before retrying after an error

    async def _check_timeouts_loop(self):
        """Periodically check for PENDING approvals that have timed out."""
        print("⌛ Timeout Checker Loop: Started.")
        while self.is_running:
            try:
                await self.social_media_manager.check_timeouts()
            except Exception as e:
                print(f"❌ ERROR in Timeout Check Loop: {e}")
            await asyncio.sleep(self.timeout_check_interval)

    def _setup_signal_handlers(self):
        """Sets up handlers for graceful shutdown on SIGINT and SIGTERM."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._shutdown(s)))

    async def _shutdown(self, sig: signal.Signals):
        """Gracefully shuts down all running background tasks."""
        print(f"\n🛑 Received shutdown signal: {sig.name}. Shutting down gracefully...")
        self.is_running = False

        # Cancel all running tasks
        tasks = [t for t in self.background_tasks if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()

        print(f"Cancelling {len(tasks)} outstanding tasks...")
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up Telegram aiohttp session
        await self.telegram_bot.close()
        
        print("✅ Service shutdown complete.")
        loop = asyncio.get_running_loop()
        loop.stop()

def run_service():
    """Main entry point to run the service."""
    service = NewsAgencyService()
    try:
        asyncio.run(service.start_service())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Service stopped by user or system.")

if __name__ == "__main__":
    # Ensure the 'data/outputs' directory exists for logging workflow results
    os.makedirs("data/outputs", exist_ok=True)
    run_service()