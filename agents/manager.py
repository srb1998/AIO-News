from agents.news_hunter import NewsHunterAgent
from agents.detective_agent import DetectiveAgent
from agents.script_writer import ScriptWriterAgent
from agents.social_media_manager import SocialMediaManagerAgent
from core.token_manager import token_manager
from services.telegram_bot import TelegramNotifier
from typing import Dict, Any, List
from datetime import datetime
import asyncio
import os
import json

class ManagerAgent:
    def __init__(self):
        self.name = "NewsManager"
        # Initialize TelegramNotifier
        telegram_bot = TelegramNotifier(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
        )
        self.agents = {
            "news_hunter": NewsHunterAgent(),
            "detective": DetectiveAgent(),
            "script_writer": ScriptWriterAgent(),
            "social_media_manager": SocialMediaManagerAgent(telegram_bot=telegram_bot)
        }
        # Set SocialMediaManagerAgent on TelegramNotifier
        telegram_bot.set_social_media_manager(self.agents["social_media_manager"])
        self.workflow_state = {}
        self.telegram_bot = telegram_bot  # Store for direct access

    async def execute_daily_workflow(self, posting_mode: str = "hitl") -> Dict[str, Any]:
        """Execute complete daily news workflow with Script Writer and Social Media Manager"""
        print("🎯 Manager: Starting daily news workflow with Script Writer and Social Media Manager...")
        print("=" * 70)
         
        workflow_id = f"daily_{datetime.now().strftime('%d-%m-%y_%H-%M-%S')}"
        workflow_result = {
            "workflow_id": workflow_id,
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "final_output": {},
            "total_cost": 0.0,
            "total_tokens": 0
        }

        try:
            # Step 1: News Hunter - Get structured headlines
            print("\n🔄 Step 1: News Hunter - Gathering articles...")
            hunter_result = await self.agents["news_hunter"].hunt_daily_news(max_articles=5)
            
            workflow_result["steps"].append({
                "step": 1,
                "agent": "news_hunter",
                "status": "success" if hunter_result.get("success") else "failed",
                "token_usage": hunter_result.get("token_usage", {}),
                "articles_found": hunter_result.get("articles_processed", 0)
            })

            if not hunter_result.get("success"):
                workflow_result["error"] = "News Hunter failed"
                return workflow_result

            final_headlines = hunter_result.get("top_headlines", [])
            print(f"📊 News Hunter found {len(final_headlines)} headlines")
            print(f"Top Headlines: {final_headlines}")
            
            # Send standalone Telegram notification for top headlines
            if final_headlines:
                message_id = await self.telegram_bot.send_headlines_notification(
                    self.telegram_bot.chat_id,
                    final_headlines
                )
                if message_id:
                    print(f"📱 Sent Telegram notification for {len(final_headlines)} top headlines")
                    workflow_result["steps"].append({
                        "step": 1.5,
                        "agent": "telegram_notifier",
                        "status": "success",
                        "description": "Sent standalone top headlines notification",
                        "message_id": message_id
                    })
                else:
                    print("❌ Failed to send Telegram notification for top headlines")
                    workflow_result["steps"].append({
                        "step": 1.5,
                        "agent": "telegram_notifier",
                        "status": "failed",
                        "description": "Failed to send standalone top headlines notification"
                    })
            else:
                print("⚠️ No headlines available for Telegram notification")
                workflow_result["steps"].append({
                    "step": 1.5,
                    "agent": "telegram_notifier",
                    "status": "skipped",
                    "description": "No headlines available for notification"
                })

            # Step 2: Detective Agent - Investigate top stories
            print("\n🔄 Step 2: Detective Agent - Investigating top stories...")
            detective_result = await self.agents["detective"].investigate_top_stories(
                final_headlines, max_stories=3
            )

            workflow_result["steps"].append({
                "step": 2,
                "agent": "detective",
                "status": "success" if detective_result.get("success") else "failed",
                "token_usage": detective_result.get("token_usage", {}),
                "stories_investigated": detective_result.get("stories_investigated", 0)
            })

            investigation_reports = []
            if detective_result.get("success"):
                investigation_reports = detective_result.get("investigation_reports", [])
                print(f"🔍 Detective investigation {investigation_reports} stories")
                print(f"✅ Detective completed investigation of {len(investigation_reports)} stories")
            else:
                print(f"⚠️ Detective investigation failed: {detective_result.get('error', 'Unknown error')}")

            # Step 3: Script Writer Agent - Generate multi-platform scripts
            print("\n🔄 Step 3: Script Writer - Generating multi-platform scripts...")
            script_result = {"success": False, "platform_scripts": []}
            
            if investigation_reports:
                script_result = await self.agents["script_writer"].generate_multi_platform_scripts(
                    investigation_reports, max_stories=3
                )
                
                workflow_result["steps"].append({
                    "step": 3,
                    "agent": "script_writer",
                    "status": "success" if script_result.get("success") else "failed",
                    "token_usage": script_result.get("token_usage", {}),
                    "scripts_generated": script_result.get("scripts_generated", 0)
                })

                if script_result.get("success"):
                    print(f"✅ Script Writer generated {script_result.get('scripts_generated', 0)} script packages")
                else:
                    print(f"⚠️ Script Writer failed: {script_result.get('error', 'Unknown error')}")
            else:
                print("⚠️ No investigation reports available for script generation")
                workflow_result["steps"].append({
                    "step": 3,
                    "agent": "script_writer",
                    "status": "skipped",
                    "reason": "No investigation reports available"
                })

            # Step 4: Social Media Manager - Process scripts for posting
            print("\n🔄 Step 4: Social Media Manager - Processing scripts for posting...")
            social_media_result = {"success": False, "posts_processed": 0}
            
            platform_scripts = script_result.get("platform_scripts", [])
            if platform_scripts:
                social_media_result = await self.agents["social_media_manager"].process_scripts_for_posting(
                    platform_scripts, top_headlines=final_headlines, posting_mode=posting_mode
                )
                
                workflow_result["steps"].append({
                    "step": 4,
                    "agent": "social_media_manager",
                    "status": "success" if social_media_result.get("success") else "failed",
                    "posts_processed": social_media_result.get("posts_processed", 0),
                    "posts_pending": social_media_result.get("posts_pending", 0),
                    "telegram_notifications": social_media_result.get("telegram_notifications_sent", 0)
                })

                if social_media_result.get("success"):
                    print(f"✅ Social Media Manager processed {social_media_result.get('posts_processed', 0)} posts")
                    if posting_mode == "hitl":
                        print(f"📱 Telegram notifications sent: {social_media_result.get('telegram_notifications_sent', 0)}")
                else:
                    print(f"⚠️ Social Media Manager failed: {social_media_result.get('error', 'Unknown error')}")
            else:
                print("⚠️ No platform scripts available for social media posting")
                workflow_result["steps"].append({
                    "step": 4,
                    "agent": "social_media_manager",
                    "status": "skipped",
                    "reason": "No platform scripts available"
                })

            # Prepare final output
            top_stories = [h for h in final_headlines if h.get("priority", 0) >= 7]

            workflow_result["final_output"] = {
                "total_headlines": len(final_headlines),
                "top_stories": len(top_stories),
                "investigated_stories": len(investigation_reports),
                "script_packages_generated": len(platform_scripts),
                "social_media_posts_processed": social_media_result.get("posts_processed", 0),
                "posts_pending_approval": social_media_result.get("posts_pending", 0),
                "posting_mode": posting_mode,
                "categories": self._get_category_breakdown(final_headlines),
                "headlines": final_headlines,
                "investigation_reports": investigation_reports,
                "platform_scripts": platform_scripts,
                "social_media_result": social_media_result,
                "breaking_news": hunter_result.get("breaking_news", []),
                "breaking_news_count": hunter_result.get("breaking_news_count", 0),
                "ready_for_social_media_manager": script_result.get("ready_for_social_media_manager", False),
                "content_ready_for_publishing": len(platform_scripts) > 0,
                "telegram_notifications_sent": social_media_result.get("telegram_notifications_sent", 0) + (1 if final_headlines and message_id else 0),
                "awaiting_user_approval": posting_mode == "hitl" and social_media_result.get("posts_pending", 0) > 0
            }

            # Calculate total costs
            total_cost = 0
            total_tokens = 0
            for step in workflow_result["steps"]:
                if "token_usage" in step and step["token_usage"]:
                    total_cost += step["token_usage"].get("cost", 0)
                    total_tokens += step["token_usage"].get("tokens", 0)

            workflow_result["total_cost"] = total_cost
            workflow_result["total_tokens"] = total_tokens
            workflow_result["success"] = True

            print(f"\n✅ Manager: Daily workflow completed!")
            print(f"📊 Final stats: {len(final_headlines)} headlines, {len(investigation_reports)} investigated, {len(platform_scripts)} script packages")
            print(f"📱 Social Media: {social_media_result.get('posts_processed', 0)} posts processed in {posting_mode.upper()} mode")
            if posting_mode == "hitl":
                print(f"⏳ Awaiting approval for {social_media_result.get('posts_pending', 0)} posts via Telegram")
            print(f"💰 Total cost: ${total_cost:.4f} ({total_tokens} tokens)")
            print(f"📈 Workflow Result: {json.dumps(workflow_result, indent=2)}")
            return workflow_result

        except Exception as e:
            workflow_result["error"] = str(e)
            workflow_result["success"] = False
            print(f"❌ Manager: Workflow failed - {e}")
            return workflow_result

    async def execute_breaking_news_workflow(self, posting_mode: str = "auto") -> Dict[str, Any]:
        """Execute breaking news workflow with immediate script generation and posting"""
        print("🚨 Manager: Breaking news workflow with script generation and posting...")

        try:
            # Get breaking news
            hunter_result = await self.agents["news_hunter"].hunt_breaking_news()

            if not hunter_result.get("success") or not hunter_result.get("breaking_news_found"):
                return {
                    "success": True,
                    "message": "No breaking news found",
                    "breaking_alerts": []
                }

            breaking_stories = hunter_result.get("processed_breaking_news", [])
            investigation_reports = []
            breaking_scripts = []
            social_media_result = {"success": False}

            if breaking_stories:
                print("🔍 Quick investigation of breaking news...")
                detective_result = self.agents["detective"].investigate_top_stories(
                    breaking_stories, max_stories=1
                )
                
                if detective_result.get("success"):
                    investigation_reports = detective_result.get("investigation_reports", [])
                    
                    if investigation_reports:
                        print("📝 Generating breaking news scripts...")
                        for report in investigation_reports:
                            script_result = self.agents["script_writer"].generate_breaking_news_scripts(report)
                            if script_result.get("success"):
                                breaking_scripts.extend(script_result.get("breaking_scripts", []))

                        if breaking_scripts:
                            print("📱 Processing breaking news for social media posting...")
                            social_media_result = await self.agents["social_media_manager"].process_scripts_for_posting(
                                breaking_scripts, posting_mode=posting_mode
                            )

            return {
                "success": True,
                "breaking_news_count": hunter_result.get("breaking_news_found", 0),
                "breaking_alerts": breaking_stories,
                "investigation_reports": investigation_reports,
                "breaking_scripts": breaking_scripts,
                "social_media_result": social_media_result,
                "posts_processed": social_media_result.get("posts_processed", 0),
                "requires_immediate_action": len(breaking_scripts) > 0,
                "ready_for_immediate_publishing": len(breaking_scripts) > 0,
                "posting_mode": posting_mode,
                "posted_immediately": posting_mode == "auto" and social_media_result.get("success", False)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_workflow_status(self) -> Dict[str, Any]:
        """Get current workflow status and agent health"""
        token_summary = token_manager.get_daily_summary()
        social_media_status = self.agents["social_media_manager"].get_posting_status()

        return {
            "manager_status": "active",
            "agents_available": list(self.agents.keys()),
            "workflow_capabilities": [
                "news_collection",
                "story_investigation", 
                "multi_platform_script_generation",
                "social_media_posting",
                "telegram_notifications",
                "human_in_the_loop_approval",
                "breaking_news_response"
            ],
            "token_budget": {
                "used": token_summary["total_tokens"],
                "remaining": token_summary["budget_remaining"],
                "cost_today": token_summary["total_cost"]
            },
            "social_media_status": social_media_status,
            "last_workflow": self.workflow_state.get("last_execution"),
            "ready_for_workflow": token_summary["budget_remaining"] > 2000
        }

    def get_content_summary(self, workflow_result: Dict[str, Any]) -> Dict[str, Any]:
        """Get summary of generated content for publishing"""
        if not workflow_result.get("success"):
            return {"error": "No successful workflow to summarize"}

        final_output = workflow_result.get("final_output", {})
        platform_scripts = final_output.get("platform_scripts", [])
        social_media_result = final_output.get("social_media_result", {})
        
        content_summary = {
            "ready_for_publishing": len(platform_scripts) > 0,
            "total_script_packages": len(platform_scripts),
            "platforms_covered": [],
            "content_breakdown": {
                "instagram_posts": 0,
                "twitter_threads": 0,
                "youtube_scripts": 0,
                "linkedin_posts": 0
            },
            "social_media_processing": {
                "posts_processed": social_media_result.get("posts_processed", 0),
                "posts_pending_approval": social_media_result.get("posts_pending", 0),
                "posts_approved": social_media_result.get("posts_approved", 0),
                "telegram_notifications_sent": social_media_result.get("telegram_notifications_sent", 0),
                "posting_mode": final_output.get("posting_mode", "unknown")
            },
            "priority_content": [],
            "estimated_publishing_time": "15-20 minutes" if social_media_result.get("posts_pending", 0) > 0 else "Immediate"
        }

        for script_package in platform_scripts:
            if "instagram" in script_package:
                content_summary["content_breakdown"]["instagram_posts"] += 1
            if "twitter" in script_package:
                content_summary["content_breakdown"]["twitter_threads"] += 1
            if "youtube" in script_package:
                content_summary["content_breakdown"]["youtube_scripts"] += 1
            if "linkedin" in script_package:
                content_summary["content_breakdown"]["linkedin_posts"] += 1
            
            if script_package.get("importance_score", 0) >= 8:
                content_summary["priority_content"].append({
                    "headline": script_package.get("original_headline", ""),
                    "platforms": [p for p in ["instagram", "twitter", "youtube", "linkedin"] if p in script_package],
                    "priority": "high",
                    "ready_for_posting": True
                })

        content_summary["platforms_covered"] = [
            platform for platform, count in content_summary["content_breakdown"].items() 
            if count > 0
        ]

        return content_summary

    async def handle_social_media_callback(self, callback_data: str, user_message: str = "") -> Dict[str, Any]:
        """Handle social media approval callbacks from Telegram"""
        try:
            return await self.agents["social_media_manager"].handle_telegram_callback(callback_data, user_message)
        except Exception as e:
            return {"success": False, "error": f"Failed to handle callback: {str(e)}"}

    def get_social_media_status(self) -> Dict[str, Any]:
        """Get current social media posting status"""
        return self.agents["social_media_manager"].get_posting_status()

    def _get_category_breakdown(self, headlines: List[Dict]) -> Dict[str, int]:
        """Get breakdown of headlines by category"""
        categories = {}
        for headline in headlines:
            cat = headline.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1
        return categories