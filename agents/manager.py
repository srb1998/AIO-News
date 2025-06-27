# FILE: agents/manager.py (UPDATED VERSION)

from agents.news_hunter import NewsHunterAgent
from agents.detective_agent import DetectiveAgent
from core.token_manager import token_manager
from typing import Dict, Any, List
from datetime import datetime

class ManagerAgent:
    def __init__(self):
        self.name = "NewsManager"
        self.agents = {
            "news_hunter": NewsHunterAgent(),
            "detective": DetectiveAgent()
        }
        self.workflow_state = {}

    def execute_daily_workflow(self) -> Dict[str, Any]:
        """Execute complete daily news workflow with Detective Agent"""
        print("🎯 Manager: Starting daily news workflow with Detective Agent...")
        print("=" * 70)

        workflow_result = {
            "workflow_id": f"daily_{datetime.now().strftime('%Y%m%d_%H%M')}",
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "final_output": {},
            "total_cost": 0.0,
            "total_tokens": 0
        }

        try:
            # Step 1: News Hunter - Get structured headlines
            print("\n🔄 Step 1: News Hunter - Gathering articles...")
            hunter_result = self.agents["news_hunter"].hunt_daily_news(max_articles=12)
            print(f"News Hunter result: {hunter_result}")
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
            print(f"📊 News Hunter found {final_headlines} headlines")
            
            # Step 2: Detective Agent - Investigate top stories
            print("\n🔄 Step 2: Detective Agent - Investigating top stories...")
            detective_result = self.agents["detective"].investigate_top_stories(
                final_headlines, max_stories=3
            )
            print(f"Detective investigation result: {detective_result}")

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
                print(f"✅ Detective completed investigation of {len(investigation_reports)} stories")
            else:
                print(f"⚠️ Detective investigation failed: {detective_result.get('error', 'Unknown error')}")

            # Prepare final output
            top_stories = [h for h in final_headlines if h.get("priority", 0) >= 7]

            workflow_result["final_output"] = {
                "total_headlines": len(final_headlines),
                "top_stories": len(top_stories),
                "investigated_stories": len(investigation_reports),
                "categories": self._get_category_breakdown(final_headlines),
                "headlines": final_headlines,
                "investigation_reports": investigation_reports,
                "breaking_news": hunter_result.get("breaking_news", []),
                "breaking_news_count": hunter_result.get("breaking_news_count", 0),
                "ready_for_script_writer": detective_result.get("ready_for_script_writer", False)
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
            print(f"📊 Final stats: {len(final_headlines)} headlines, {len(investigation_reports)} investigated, ${total_cost:.4f} cost")

            return workflow_result

        except Exception as e:
            workflow_result["error"] = str(e)
            workflow_result["success"] = False
            print(f"❌ Manager: Workflow failed - {e}")
            return workflow_result

    def execute_breaking_news_workflow(self) -> Dict[str, Any]:
        """Execute breaking news workflow (fast response)"""
        print("🚨 Manager: Breaking news workflow...")

        try:
            hunter_result = self.agents["news_hunter"].hunt_breaking_news()

            if not hunter_result.get("success") or not hunter_result.get("breaking_news_found"):
                return {
                    "success": True,
                    "message": "No breaking news found",
                    "breaking_alerts": []
                }

            # For breaking news, do quick investigation
            breaking_stories = hunter_result.get("processed_breaking_news", [])
            if breaking_stories:
                print("🔍 Quick investigation of breaking news...")
                detective_result = self.agents["detective"].investigate_top_stories(
                    breaking_stories, max_stories=2  # Limit for speed
                )
                
                investigation_reports = detective_result.get("investigation_reports", []) if detective_result.get("success") else []
            else:
                investigation_reports = []

            return {
                "success": True,
                "breaking_news_count": hunter_result.get("breaking_news_found", 0),
                "breaking_alerts": breaking_stories,
                "investigation_reports": investigation_reports,
                "requires_immediate_action": hunter_result.get("breaking_news_found", 0) > 0
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_workflow_status(self) -> Dict[str, Any]:
        """Get current workflow status and agent health"""
        token_summary = token_manager.get_daily_summary()

        return {
            "manager_status": "active",
            "agents_available": list(self.agents.keys()),
            "token_budget": {
                "used": token_summary["total_tokens"],
                "remaining": token_summary["budget_remaining"],
                "cost_today": token_summary["total_cost"]
            },
            "last_workflow": self.workflow_state.get("last_execution"),
            "ready_for_workflow": token_summary["budget_remaining"] > 1000
        }

    def _get_category_breakdown(self, headlines: List[Dict]) -> Dict[str, int]:
        """Get breakdown of headlines by category"""
        categories = {}
        for headline in headlines:
            cat = headline.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1
        return categories