import asyncio
import uvicorn  # <-- Import uvicorn
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Any
from agents.manager import ManagerAgent
from agents.social_media_manager import SocialMediaManagerAgent
from core.token_manager import token_manager
from services.telegram_bot import TelegramNotifier
from core.approval_queue import ApprovalQueue
from config.settings import settings
import json
import time
import os

# Import the FastAPI app and the setter function from our new file
from webhook_server import app as webhook_app, set_social_media_manager

class NewsAgencyService:
    def __init__(self):
        # This part remains mostly the same
        self.manager = ManagerAgent()
        self.approval_queue = ApprovalQueue()
        self.telegram_bot = TelegramNotifier(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
        )
        self.social_media_manager = SocialMediaManagerAgent(telegram_bot=self.telegram_bot)
        self.telegram_bot.set_social_media_manager(self.social_media_manager)
        
        set_social_media_manager(self.social_media_manager)
        
        self.is_running = False
        self.workflow_interval = settings.WORKFLOW_TIMING["daily_workflow_interval"]
        self.breaking_news_interval = settings.WORKFLOW_TIMING["breaking_news_check_interval"]
        self.timeout_check_interval = 1800
        self.last_workflow_run = None
        self.last_breaking_news_run = None
        self.background_tasks = set()
        self.heartbeat_interval = 3600
        os.makedirs(settings.TELEGRAM_CONFIG["videos_storage_path"], exist_ok=True)

    async def start_service(self):
        """Start the service, including the integrated webhook server."""
        print("🚀 Starting News Agency Service...")
        print(f"📡 Telegram polling interval: {settings.TELEGRAM_CONFIG['polling_interval_seconds']} seconds")
        print("=" * 60)
        
        self.is_running = True
        self._setup_signal_handlers()
        
        # Start Telegram polling task
        polling_task = asyncio.create_task(self.telegram_bot.start_polling())
        self.background_tasks.add(polling_task)
        polling_task.add_done_callback(self.background_tasks.discard)
        
        # Start timeout check task
        timeout_task = asyncio.create_task(self._check_timeouts_loop())
        self.background_tasks.add(timeout_task)
        timeout_task.add_done_callback(self.background_tasks.discard)
        
        # --- NEW: Configure and start the Uvicorn/FastAPI server as a background task ---
        config = uvicorn.Config(webhook_app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        webhook_task = asyncio.create_task(server.serve())
        self.background_tasks.add(webhook_task)
        webhook_task.add_done_callback(self.background_tasks.discard)
        print("🚀 Webhook listener started on http://0.0.0.0:8000")
        
        await self._schedule_next_workflow()
        await self._service_loop()

    async def _service_loop(self):
        """Main service event loop"""
        print("🔄 Service loop started - Press Ctrl+C to stop")
        last_heartbeat = datetime.now()
        
        try:
            while self.is_running:
                current_time = datetime.now()
                
                if (current_time - last_heartbeat).total_seconds() >= self.heartbeat_interval:
                    print(f"💓 Service heartbeat: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    last_heartbeat = current_time
                
                if self._should_run_workflow():
                    await self._execute_workflow()  # Run directly to ensure last_workflow_run is updated
                    await self._schedule_next_workflow()
                
                # if self._should_run_breaking_news():
                #     await self._execute_breaking_news()
                #     await self._schedule_next_breaking_news()
                
                await asyncio.sleep(60)
                
        except KeyboardInterrupt:
            print("\n🛑 Received shutdown signal: User interrupt")
        except Exception as e:
            print(f"❌ Service error: {e}")
        finally:
            await self._shutdown()

    async def _check_timeouts_loop(self):
        """Periodically check for timed-out approvals"""
        while self.is_running:
            try:
                await self.social_media_manager.check_timeouts()
            except Exception as e:
                print(f"❌ Timeout check error: {e}")
            await asyncio.sleep(self.timeout_check_interval)

    def _should_run_workflow(self) -> bool:
        """Check if it's time to run the daily workflow"""
        if self.last_workflow_run is None:
            return True
        time_since_last = (datetime.now() - self.last_workflow_run).total_seconds()
        return time_since_last >= self.workflow_interval

    async def _execute_workflow(self):
        """Execute the daily workflow"""
        print(f"\n⏰ {datetime.now().strftime('%H:%M:%S')} - Starting daily workflow")
        print("=" * 50)
        
        try:
            result = await self.manager.execute_daily_workflow(posting_mode="hitl")
            self._log_workflow_result(result, workflow_type="daily")
            self.last_workflow_run = datetime.now()  # Update after execution
        except Exception as e:
            print(f"❌ Daily workflow execution failed: {e}")
            self.last_workflow_run = datetime.now()  # Update even on failure to prevent immediate retry

    def _log_workflow_result(self, result: Dict[str, Any], workflow_type: str):
        """Log workflow results"""
        if result.get("success"):
            final = result.get("final_output", {})
            print(f"✅ {workflow_type.capitalize()} workflow completed successfully!")
            if workflow_type == "daily":
                print(f"📰 Headlines: {final.get('total_headlines', 0)}")
                print(f"🔍 Investigated: {final.get('investigated_stories', 0)}")
                print(f"📝 Scripts: {final.get('script_packages_generated', 0)}")
                print(f"📱 Posts processed: {final.get('social_media_posts_processed', 0)}")
            else:
                print(f"🚨 Breaking news alerts: {result.get('breaking_news_count', 0)}")
                print(f"📝 Scripts: {len(result.get('breaking_scripts', []))}")
                print(f"📱 Posts processed: {result.get('posts_processed', 0)}")
            print(f"💰 Cost: ${result.get('total_cost', 0):.4f}")
            self._save_workflow_result(result, workflow_type)
        else:
            print(f"❌ {workflow_type.capitalize()} workflow failed: {result.get('error', 'Unknown error')}")

    def _save_workflow_result(self, result: Dict[str, Any], workflow_type: str):
        """Save workflow result to file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"data/outputs/{workflow_type}_workflow_{timestamp}.json"
            with open(filename, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"💾 {workflow_type.capitalize()} workflow result saved to {filename}")
        except Exception as e:
            print(f"⚠️ Failed to save {workflow_type} workflow result: {e}")

    async def _schedule_next_workflow(self):
        """Schedule next daily workflow run"""
        next_run = datetime.now() + timedelta(seconds=self.workflow_interval)
        print(f"📅 Next daily workflow scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    async def _schedule_next_breaking_news(self):
        """Schedule next breaking news check"""
        next_run = datetime.now() + timedelta(seconds=self.breaking_news_interval)
        print(f"📅 Next breaking news check scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            reason = "User interrupt (Ctrl+C)" if signum == signal.SIGINT else "System termination"
            print(f"\n🛑 Received signal {signum}: {reason}")
            self.is_running = False
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def _shutdown(self):
        """Graceful shutdown"""
        print("🔄 Shutting down service...")
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        # Close aiohttp sessions in TelegramNotifier
        if hasattr(self.telegram_bot, '_session') and self.telegram_bot._session:
            await self.telegram_bot._session.close()
        print("✅ Service shutdown complete")

    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status"""
        return {
            "service_running": self.is_running,
            "last_workflow_run": self.last_workflow_run.isoformat() if self.last_workflow_run else None,
            "next_workflow_in_seconds": self.workflow_interval - (
                (datetime.now() - self.last_workflow_run).total_seconds() 
                if self.last_workflow_run else 0
            ),
            "last_breaking_news_run": self.last_breaking_news_run.isoformat() if self.last_breaking_news_run else None,
            "next_breaking_news_in_seconds": self.breaking_news_interval - (
                (datetime.now() - self.last_breaking_news_run).total_seconds()
                if self.last_breaking_news_run else 0
            ),
            "pending_approvals": len(self.approval_queue.get_all_pending()),
            "workflow_interval_hours": self.workflow_interval / 3600,
            "breaking_news_interval_minutes": self.breaking_news_interval / 60,
            "manager_status": self.manager.get_workflow_status()
        }

async def main():
    """Main entry point for the service"""
    print("🎯 News Agency Service - Phase 2")
    print("=" * 40)
    
    service = NewsAgencyService()
    
    try:
        await service.start_service()
    except KeyboardInterrupt:
        print("\n👋 Service stopped by user")
    except Exception as e:
        print(f"❌ Service failed: {e}")
    finally:
        print("🔚 Service terminated")

def run_service():
    """Run the service with proper error handling"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_service()