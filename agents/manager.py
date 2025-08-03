from agents.news_hunter import NewsHunterAgent
from agents.detective_agent import DetectiveAgent
from agents.script_writer import ScriptWriterAgent
from agents.social_media_manager import SocialMediaManagerAgent
from core.token_manager import token_manager
from services.telegram_bot import TelegramNotifier
from typing import Dict, Any, List
from datetime import datetime
from config.settings import settings
from utils.cloudinary_uploader import upload_json_to_cloudinary
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
        telegram_bot.set_manager_agent(self)
        self.telegram_bot = telegram_bot  # Store for direct access
        self.pending_workflows = {}
        
    def register_user_selection(self, workflow_id: str, story_hash: str) -> bool:
        """
        Called by the Telegram bot. Handles both single and 'all' story selections.
        """
        if workflow_id not in self.pending_workflows:
            return False

        if story_hash == "all":
            all_stories = self.pending_workflows[workflow_id]['stories'].values()
            self.pending_workflows[workflow_id]['selected'] = list(all_stories)
            print(f"✅ User selected all {len(all_stories)} stories.")
            return True

        # Handle single story selection
        if story_hash in self.pending_workflows[workflow_id]['stories']:
            story = self.pending_workflows[workflow_id]['stories'][story_hash]
            if story not in self.pending_workflows[workflow_id]['selected']:
                self.pending_workflows[workflow_id]['selected'].append(story)
                print(f"✅ User selected story: '{story['headline'][:50]}...'")
                return True
        
        return False
    
    async def execute_daily_workflow(self, posting_mode: str = "hitl") -> Dict[str, Any]:
        """Executes a two-gate HITL workflow with full, detailed reporting."""
        print("🎯 Manager: Starting Two-Gate daily news workflow...")
        workflow_id = f"workflow_{datetime.now().strftime('%d-%b-%Y_%H-%M-%S')}"
        workflow_result = { "workflow_id": workflow_id, "started_at": datetime.now().isoformat(), "steps": [], "final_output": {}, "total_cost": 0.0, "total_tokens": 0 }

        # --- Initialize variables to store results from each stage ---
        final_headlines, selected_stories, investigation_reports, platform_scripts = [], [], [], []
        hunter_result, detective_result, script_result, social_media_result = {}, {}, {}, {}
        
        try:
            # --- GATE 1: STORY SELECTION ---
            print("\n🔄 Step 1: News Hunter - Gathering articles for selection...")
            hunter_result = await self.agents["news_hunter"].hunt_daily_news(max_articles_to_fetch=40)
            final_headlines = hunter_result.get("top_headlines", [])
            
            if not final_headlines:
                print("GATE 1: News Hunter found no new headlines. Workflow ending.")
                return workflow_result

            self.pending_workflows[workflow_id] = { 'stories': {str(abs(hash(h.get('original_title', h.get('headline'))))): h for h in final_headlines}, 'selected': [] }

            timeout = settings.WORKFLOW_TIMING["hitl_selection_timeout_seconds"]
            print(f"GATE 1: Presenting {len(final_headlines)} headlines for selection. Waiting for {timeout} seconds...")
            await self.telegram_bot.send_selection_notification(final_headlines[:4], workflow_id)
            await asyncio.sleep(timeout)
            selected_stories = self.pending_workflows[workflow_id].get('selected', [])
            
            if not selected_stories:
                print("GATE 1: No stories selected by the user. Workflow ending.")
                return workflow_result

            print(f"GATE 1: User selected {len(selected_stories)} stories. Proceeding...")

            # --- GATE 2: SCRIPTING & FINAL APPROVAL ---
            print("\n🔄 Step 2: Detective Agent - Investigating selected stories...")
            detective_result = await self.agents["detective"].investigate_top_stories(selected_stories, max_stories=len(selected_stories))
            investigation_reports = detective_result.get("investigation_reports", [])

            print("\n🔄 Step 3: Script Writer - Generating scripts...")
            script_result = await self.agents["script_writer"].generate_multi_platform_scripts(investigation_reports, max_stories=len(investigation_reports))
            platform_scripts = script_result.get("platform_scripts", [])

            print("\n🔄 Step 4: Social Media Manager - Sending final scripts for approval...")
            if platform_scripts:
                social_media_result = await self.agents["social_media_manager"].process_scripts_for_posting(platform_scripts, workflow_id=workflow_id, posting_mode=posting_mode)

            # --- RE-ADDED: Construct the detailed final output object ---
            workflow_result["steps"] = [
                {"step": 1, "agent": "news_hunter", "status": "success", "token_usage": hunter_result.get("token_usage", {}), "articles_found": hunter_result.get("articles_processed", 0)},
                {"step": 2, "agent": "detective", "status": "success", "token_usage": detective_result.get("token_usage", {}), "stories_investigated": detective_result.get("stories_investigated", 0)},
                {"step": 3, "agent": "script_writer", "status": "success", "token_usage": script_result.get("token_usage", {}), "scripts_generated": script_result.get("scripts_generated", 0)},
                {"step": 4, "agent": "social_media_manager", "status": "success", "posts_processed": social_media_result.get("posts_processed", 0), "posts_pending": social_media_result.get("posts_pending", 0)}
            ]

            total_cost = sum(step["token_usage"].get("cost", 0) for step in workflow_result["steps"] if step.get("token_usage"))
            total_tokens = sum(step["token_usage"].get("tokens", 0) for step in workflow_result["steps"] if step.get("token_usage"))
            workflow_result["total_cost"] = total_cost
            workflow_result["total_tokens"] = total_tokens
            workflow_result["success"] = True

            top_stories = [h for h in final_headlines if h.get("priority", 0) >= 8]

            workflow_result["final_output"] = {
                "total_headlines": len(final_headlines),
                "top_stories": len(top_stories),
                "stories_selected_by_user": len(selected_stories),
                "investigated_stories": len(investigation_reports),
                "script_packages_generated": len(platform_scripts),
                "social_media_posts_processed": social_media_result.get("posts_processed", 0),
                "posts_pending_approval": social_media_result.get("posts_pending", 0),
                "posting_mode": posting_mode,
                "headlines": final_headlines,
                "investigation_reports": investigation_reports,
                "platform_scripts": platform_scripts,
                "social_media_result": social_media_result,
                "telegram_notifications_sent": social_media_result.get("telegram_notifications_sent", 0),
                "awaiting_user_approval": social_media_result.get("posts_pending", 0) > 0
            }

            print(f"\n✅ Manager: Two-Gate workflow completed!")
            print(f"📊 Final stats: {len(final_headlines)} headlines found, {len(selected_stories)} selected, {len(platform_scripts)} scripted.")
            print(f"💰 Total cost for this run: ${total_cost:.4f} ({total_tokens} tokens)")
            
            return workflow_result

        except Exception as e:
            workflow_result["error"] = str(e)
            workflow_result["success"] = False
            print(f"❌ Manager: Workflow failed - {e}")
            return workflow_result
        finally:
            if workflow_id in self.pending_workflows:
                del self.pending_workflows[workflow_id]
            
            # --- NEW: Upload the final result to Cloudinary, on success or failure ---
            summary_url = await upload_json_to_cloudinary(workflow_result, workflow_id)
            if summary_url:
                await self.telegram_bot.send_workflow_summary_notification(workflow_id, summary_url)
                

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