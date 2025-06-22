from agents.news_hunter import NewsHunterAgent
from core.token_manager import token_manager
from typing import Dict, Any, List
from datetime import datetime

class ManagerAgent:
    def __init__(self):
        self.name = "NewsManager"
        self.agents = {
            "news_hunter": NewsHunterAgent()
        }
        self.workflow_state = {}

    def execute_daily_workflow(self) -> Dict[str, Any]:
        """Execute complete daily news workflow"""
        print("🎯 Manager: Starting daily news workflow...")
        print("=" * 60)

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
            print("hunter_result : ", hunter_result)

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
            top_stories = [h for h in final_headlines if h.get("priority", 0) >= 7]

            workflow_result["final_output"] = {
                "total_headlines": len(final_headlines),
                "top_stories": len(top_stories),
                "categories": self._get_category_breakdown(final_headlines),
                "headlines": final_headlines,
                "breaking_news": hunter_result.get("breaking_news", []),
                "breaking_news_count": hunter_result.get("breaking_news_count", 0),
                "ready_for_next_agent": True
            }

            # Cost calculation
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
            print(f"📊 Final stats: {len(final_headlines)} headlines, ${total_cost:.4f} cost")

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
            print("hunter_result : ", hunter_result)

            if not hunter_result.get("success") or not hunter_result.get("breaking_news_found"):
                return {
                    "success": True,
                    "message": "No breaking news found",
                    "breaking_alerts": []
                }

            return {
                "success": True,
                "breaking_news_count": hunter_result.get("breaking_news_found", 0),
                "breaking_alerts": hunter_result.get("processed_breaking_news", []),
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
