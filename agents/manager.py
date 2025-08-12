# manager.py

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
        telegram_bot = TelegramNotifier(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
        )
        self.agents = {
            "news_hunter": NewsHunterAgent(),
            "detective": DetectiveAgent(),
            "script_writer": ScriptWriterAgent(),
            "social_media_manager": SocialMediaManagerAgent(telegram_bot=telegram_bot)
        }
        telegram_bot.set_social_media_manager(self.agents["social_media_manager"])
        telegram_bot.set_manager_agent(self)
        self.telegram_bot = telegram_bot
        self.pending_workflows = {}
        
    def register_user_selection(self, workflow_id: str, story_hash: str) -> bool:
        """Handle user story selections from Telegram"""
        if workflow_id not in self.pending_workflows:
            return False

        if story_hash == "all":
            all_stories = self.pending_workflows[workflow_id]['stories'].values()
            self.pending_workflows[workflow_id]['selected'] = list(all_stories)
            print(f"✅ User selected all {len(all_stories)} stories.")
            return True

        if story_hash in self.pending_workflows[workflow_id]['stories']:
            story = self.pending_workflows[workflow_id]['stories'][story_hash]
            if story not in self.pending_workflows[workflow_id]['selected']:
                self.pending_workflows[workflow_id]['selected'].append(story)
                print(f"✅ User selected: '{story['headline'][:50]}...'")
                return True
        
        return False
    
    async def execute_daily_workflow(self, posting_mode: str = "hitl") -> Dict[str, Any]:
        """
        IMPROVED: Execute workflow with better cache integration and debugging
        """
        print("🎯 Manager: Starting IMPROVED daily workflow with pre-filtering...")
        workflow_id = f"workflow_{datetime.now().strftime('%d-%b-%Y_%H-%M-%S')}"
        workflow_result = {
            "workflow_id": workflow_id,
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "final_output": {},
            "total_cost": 0.0,
            "total_tokens": 0
        }

        final_headlines, selected_stories, investigation_reports, platform_scripts = [], [], [], []
        hunter_result, detective_result, script_result, social_media_result = {}, {}, {}, {}
        
        try:
            # --- GATE 1: IMPROVED STORY SELECTION WITH PRE-FILTERING ---
            print("\n🔄 Step 1: News Hunter - Gathering and filtering articles...")
            hunter_result = await self.agents["news_hunter"].hunt_daily_news(
                max_articles_to_fetch=50,  # Fetch more since we're filtering early
                top_n_to_process=6  # Process more to ensure we get good variety
            )
            final_headlines = hunter_result.get("top_headlines", [])
            
            # Enhanced logging for debugging
            articles_fetched = hunter_result.get("articles_fetched", 0)
            articles_after_filtering = hunter_result.get("articles_after_filtering", 0)
            filtered_out = articles_fetched - articles_after_filtering
            
            if not final_headlines:
                workflow_result["steps"].append({
                    "step": 1, "agent": "news_hunter", "status": "no_new_content",
                    "articles_fetched": articles_fetched,
                    "articles_filtered": articles_after_filtering,
                    "message": "No new unique headlines found after filtering"
                })
                print("GATE 1: No new unique headlines found. Workflow ending.")
                return workflow_result

            # Store stories for user selection with better mapping
            story_mapping = {}
            for headline in final_headlines:
                story_hash = str(abs(hash(headline.get('original_title', headline.get('headline')))))
                story_mapping[story_hash] = headline
            
            self.pending_workflows[workflow_id] = {
                'stories': story_mapping,
                'selected': []
            }

            # Send selection notification (limit to top 4 for clean UI)
            display_headlines = final_headlines[:5]
            timeout = settings.WORKFLOW_TIMING["hitl_selection_timeout_seconds"]
            print(f"GATE 1: Presenting {len(display_headlines)} headlines for selection. Waiting {timeout}s...")
            
            await self.telegram_bot.send_selection_notification(display_headlines, workflow_id)
            await asyncio.sleep(timeout)
            
            selected_stories = self.pending_workflows[workflow_id].get('selected', [])
            
            if not selected_stories:
                workflow_result["steps"].append({
                    "step": 1, "agent": "user_selection", "status": "no_selection",
                    "headlines_presented": len(display_headlines)
                })
                print("GATE 1: No stories selected by user. Workflow ending.")
                return workflow_result

            print(f"GATE 1: User selected {len(selected_stories)} stories. Proceeding...")

            # --- GATE 2: INVESTIGATION & SCRIPTING ---
            print(f"\n🔄 Step 2: Detective - Investigating {len(selected_stories)} selected stories...")
            detective_result = await self.agents["detective"].investigate_top_stories(
                selected_stories, 
                max_stories=len(selected_stories)
            )
            investigation_reports = detective_result.get("investigation_reports", [])

            print(f"\n🔄 Step 3: Script Writer - Generating scripts for {len(investigation_reports)} stories...")
            if investigation_reports:
                script_result = await self.agents["script_writer"].generate_multi_platform_scripts(
                    investigation_reports, 
                    max_stories=len(investigation_reports)
                )
                platform_scripts = script_result.get("platform_scripts", [])
            
            print(f"\n🔄 Step 4: Social Media Manager - Processing {len(platform_scripts)} script packages...")
            if platform_scripts:
                social_media_result = await self.agents["social_media_manager"].process_scripts_for_posting(
                    platform_scripts, 
                    workflow_id=workflow_id, 
                    posting_mode=posting_mode
                )

            # Calculate totals
            total_cost = sum(
                step["token_usage"].get("cost", 0) 
                for step in workflow_result["steps"] 
                if step.get("token_usage")
            )
            total_tokens = sum(
                step["token_usage"].get("tokens", 0) 
                for step in workflow_result["steps"] 
                if step.get("token_usage")
            )
            
            workflow_result["total_cost"] = total_cost
            workflow_result["total_tokens"] = total_tokens
            workflow_result["success"] = True

            # Final output with filtering statistics
            workflow_result["final_output"] = {
                "filtering_stats": {
                    "raw_articles_fetched": articles_fetched,
                    "unique_articles_processed": articles_after_filtering,
                    "duplicate_articles_filtered": filtered_out,
                    "filtering_efficiency": f"{(filtered_out/articles_fetched*100):.1f}%" if articles_fetched > 0 else "0%"
                },
                "content_stats": {
                    "headlines_generated": len(final_headlines),
                    "headlines_presented_to_user": len(display_headlines),
                    "stories_selected_by_user": len(selected_stories),
                    "stories_investigated": len(investigation_reports),
                    "script_packages_generated": len(platform_scripts)
                },
                "social_media_stats": {
                    "posts_processed": social_media_result.get("posts_processed", 0),
                    "posts_pending_approval": social_media_result.get("posts_pending", 0),
                    "telegram_notifications_sent": social_media_result.get("telegram_notifications_sent", 0)
                },
                "workflow_config": {
                    "posting_mode": posting_mode,
                    "selection_timeout_seconds": timeout,
                    "max_articles_fetched": 50
                },
                # Data for potential reprocessing or analysis
                "generated_content": {
                    "headlines": final_headlines,
                    "investigation_reports": investigation_reports,
                    "platform_scripts": platform_scripts
                },
                "social_media_result": social_media_result,
                "awaiting_user_approval": social_media_result.get("posts_pending", 0) > 0
            }
            
            return workflow_result

        except Exception as e:
            workflow_result["error"] = str(e)
            workflow_result["success"] = False
            print(f"❌ Manager: Workflow failed - {e}")
            return workflow_result
        finally:
            if workflow_id in self.pending_workflows:
                del self.pending_workflows[workflow_id]
            
            # Upload workflow result to Cloudinary
            summary_url = await upload_json_to_cloudinary(workflow_result, workflow_id)
            if summary_url:
                await self.telegram_bot.send_workflow_summary_notification(workflow_id, summary_url)

    def get_workflow_status(self) -> Dict[str, Any]:
        """Get enhanced workflow status with cache statistics"""
        token_summary = token_manager.get_daily_summary()
        social_media_status = self.agents["social_media_manager"].get_posting_status()
        
        # Get cache statistics
        cache_stats = {}
        try:
            story_cache = self.agents["news_hunter"].story_cache
            semantic_cache = self.agents["news_hunter"].semantic_cache
            
            cache_stats = {
                "story_cache": story_cache.get_cache_stats(),
                "semantic_cache": semantic_cache.get_cache_stats()
            }
        except Exception as e:
            cache_stats = {"error": f"Could not get cache stats: {e}"}

        return {
            "manager_status": "active",
            "agents_available": list(self.agents.keys()),
            "workflow_capabilities": [
                "pre_filtered_news_collection",
                "duplicate_prevention",
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
            "cache_statistics": cache_stats,
            "social_media_status": social_media_status,
            "ready_for_workflow": token_summary["budget_remaining"] > 2000
        }

    async def cleanup_caches(self):
        """NEW: Manual cache cleanup method"""
        try:
            print("🧹 Starting cache cleanup...")
            
            # Clean story cache
            self.agents["news_hunter"].story_cache.prune_cache()
            
            # Clean semantic cache
            self.agents["news_hunter"].semantic_cache.cleanup_old_entries()
            
            print("✅ Cache cleanup completed")
            
        except Exception as e:
            print(f"❌ Cache cleanup failed: {e}")

    def get_content_summary(self, workflow_result: Dict[str, Any]) -> Dict[str, Any]:
        """Get summary of generated content for publishing"""
        if not workflow_result.get("success"):
            return {"error": "No successful workflow to summarize"}

        final_output = workflow_result.get("final_output", {})
        platform_scripts = final_output.get("generated_content", {}).get("platform_scripts", [])
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
                "posting_mode": final_output.get("workflow_config", {}).get("posting_mode", "unknown")
            },
            "filtering_efficiency": final_output.get("filtering_stats", {}).get("filtering_efficiency", "0%"),
            "priority_content": []
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