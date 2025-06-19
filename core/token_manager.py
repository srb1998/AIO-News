import json
import os
from datetime import datetime, date
from typing import Dict, Any
import functools
from config.settings import settings


class TokenManager:
    def __init__(self):
        self.usage_file = "data/token_usage.json"
        self.daily_usage = self._load_daily_usage()
        
    def _load_daily_usage(self) -> Dict:
        """Load today's token usage from file"""
        if os.path.exists(self.usage_file):
            try:
                with open(self.usage_file, 'r') as f:
                    data = json.load(f)
                    today = str(date.today())
                    return data.get(today, {})
            except:
                pass
        return {}
    
    def _save_daily_usage(self):
        """Save token usage to file"""
        os.makedirs("data", exist_ok=True)
        
        # Load existing data
        all_data = {}
        if os.path.exists(self.usage_file):
            try:
                with open(self.usage_file, 'r') as f:
                    all_data = json.load(f)
            except:
                pass
        
        # Update today's data
        today = str(date.today())
        all_data[today] = self.daily_usage
        
        # Save back
        with open(self.usage_file, 'w') as f:
            json.dump(all_data, f, indent=2)
    
    def track_usage(self, agent_name: str, model: str, tokens: int, cost: float):
        """Track token usage for an agent"""
        if agent_name not in self.daily_usage:
            self.daily_usage[agent_name] = {
                "total_tokens": 0,
                "total_cost": 0.0,
                "calls": 0,
                "models_used": {}
            }
        
        agent_data = self.daily_usage[agent_name]
        agent_data["total_tokens"] += tokens
        agent_data["total_cost"] += cost
        agent_data["calls"] += 1
        
        if model not in agent_data["models_used"]:
            agent_data["models_used"][model] = {"tokens": 0, "cost": 0.0}
        
        agent_data["models_used"][model]["tokens"] += tokens
        agent_data["models_used"][model]["cost"] += cost
        
        self._save_daily_usage()
        
        # Log the usage
        print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] {agent_name}: {tokens} tokens (${cost:.4f}) - {model}")
    
    def get_daily_summary(self) -> Dict:
        """Get summary of today's usage"""
        total_tokens = sum(agent["total_tokens"] for agent in self.daily_usage.values())
        total_cost = sum(agent["total_cost"] for agent in self.daily_usage.values())
        
        return {
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "agents": self.daily_usage,
            "budget_remaining": settings.DAILY_TOKEN_BUDGET - total_tokens
        }
    
    def can_afford_tokens(self, estimated_tokens: int) -> bool:
        """Check if we can afford to use more tokens today"""
        current_usage = sum(agent["total_tokens"] for agent in self.daily_usage.values())
        return (current_usage + estimated_tokens) <= settings.DAILY_TOKEN_BUDGET

# Global token manager instance
token_manager = TokenManager()

def track_tokens(agent_name: str):
    """Decorator to track token usage for agent functions"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not token_manager.can_afford_tokens(1000):  # Rough estimate
                print(f"⚠️ Daily token budget exceeded! Skipping {agent_name}")
                return {"error": "Daily token budget exceeded"}
            
            result = func(*args, **kwargs)
            
            # Extract token usage from result if available
            if isinstance(result, dict) and "token_usage" in result:
                usage = result["token_usage"]
                token_manager.track_usage(
                    agent_name=agent_name,
                    model=usage["model"],
                    tokens=usage["tokens"], 
                    cost=usage["cost"]
                )
            
            return result
        return wrapper
    return decorator