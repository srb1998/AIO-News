from agents.news_hunter import NewsHunterAgent
from agents.headline_wizard import HeadlineWizardAgent
from core.token_manager import token_manager
from typing import Dict, Any, List
import json
from datetime import datetime

class ManagerAgent:
    def __init__(self):
        self.name = "NewsManager"
        self.agents = {
            "news_hunter": NewsHunterAgent(),
            # "headline_wizard": HeadlineWizardAgent()
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
            # Step 1: News Hunter - Get raw articles
            print("\n🔄 Step 1: News Hunter - Gathering articles...")
            hunter_result = self.agents["news_hunter"].hunt_daily_news(max_articles=12)
            print("hunter_result : ",hunter_result)
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
            
            # Step 2: Headline Wizard - Create engaging headlines
            # print("\n🔄 Step 2: Headline Wizard - Creating headlines...")
            # wizard_result = self.agents["headline_wizard"].create_headlines(hunter_result)
            
            # workflow_result["steps"].append({
            #     "step": 2,
            #     "agent": "headline_wizard", 
            #     "status": "success" if wizard_result.get("success") else "failed",
            #     "token_usage": wizard_result.get("token_usage", {}),
            #     "headlines_created": wizard_result.get("output_headlines", 0)
            # })
            
            # if not wizard_result.get("success"):
            #     workflow_result["error"] = "Headline Wizard failed"
            #     return workflow_result
            
            # Step 3: Compile final output
            final_headlines = hunter_result.get("headlines", [])
            top_stories = [h for h in final_headlines if h.get("priority", 0) >= 7]
            
            workflow_result["final_output"] = {
                "total_headlines": len(final_headlines),
                "top_stories": len(top_stories),
                "categories": self._get_category_breakdown(final_headlines),
                "headlines": final_headlines,
                "ready_for_next_agent": True
            }
            
            # Calculate total cost
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
            # Quick breaking news check
            hunter_result = self.agents["news_hunter"].hunt_breaking_news()
            print("hunter_result : ", hunter_result)
            if not hunter_result.get("success") or not hunter_result.get("breaking_news_found"):
                return {
                    "success": True,
                    "message": "No breaking news found",
                    "breaking_alerts": []
                }
            
            # Process breaking news through headline wizard
            wizard_result = self.agents["headline_wizard"].create_headlines(hunter_result)
            
            if wizard_result.get("success"):
                breaking_headlines = [h for h in wizard_result.get("headlines", []) 
                                    if h.get("urgency") == "high"]
                
                return {
                    "success": True,
                    "breaking_news_count": len(breaking_headlines),
                    "breaking_alerts": breaking_headlines,
                    "requires_immediate_action": len(breaking_headlines) > 0
                }
            
            return {"success": False, "error": "Failed to process breaking news"}
            
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