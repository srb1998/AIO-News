from agents.news_hunter import NewsHunterAgent
from agents.manager import ManagerAgent
from core.token_manager import token_manager
import json

def test_manager_workflow():
    """Test the complete manager workflow"""
    print("🚀 Testing Manager Agent - Complete Workflow")
    print("=" * 60)
    
    # Initialize Manager
    manager = ManagerAgent()
    
    # Check manager status
    status = manager.get_workflow_status()
    print(f"🔍 Manager Status: {status['manager_status']}")
    print(f"💰 Token Budget: {status['token_budget']['remaining']} remaining")
    print(f"🤖 Agents Available: {', '.join(status['agents_available'])}")
    
    if not status['ready_for_workflow']:
        print("⚠️ Not enough tokens for workflow!")
        return
    
    # Execute daily workflow
    result = manager.execute_daily_workflow()
    print("result is :", result)
    if result.get("success"):
        print("\n✅ WORKFLOW SUCCESSFUL!")
        print(f"📊 Workflow ID: {result['workflow_id']}")
        
        # Show step-by-step results
        print("\n📋 Workflow Steps:")
        for step in result["steps"]:
            status_emoji = "✅" if step["status"] == "success" else "❌"
            print(f"  {status_emoji} Step {step['step']}: {step['agent']}")
            if "token_usage" in step and step["token_usage"]:
                tokens = step["token_usage"].get("tokens", 0)
                cost = step["token_usage"].get("cost", 0)
                print(f"    💰 {tokens} tokens (${cost:.4f})")
        
        # Show final output
        final = result["final_output"]
        print(f"\n🎯 Final Results:")
        print(f"  📰 Total Headlines: {final['total_headlines']}")
        print(f"  ⭐ Top Stories: {final['top_stories']}")
        print(f"  📊 Categories: {final['categories']}")

        # Show breaking news
        print(f"\n🚨 Breaking News: {len(final['breaking_news'])}")
        for i, headline in enumerate(final["breaking_news"], 1):
            print(f"  {i}. {headline['headline']}")
            print(f"     🔥 Priority: {headline['priority']} | Urgency: {headline['urgency']}")
            print(f"     📝 {headline['summary']}")

        # Show top 12 headlines
        print(f"\n🔥 TOP 12 HEADLINES:")
        for i, headline in enumerate(final["headlines"][:12], 1):
            print(f"  {i}. {headline['headline']}")
            print(f"     📁 {headline['category']} | 🔥 Priority: {headline['priority']}")
            print(f"     📝 {headline['summary']}")
            print()
        
        print(f"💸 Total Cost: ${result['total_cost']:.4f}")
        print(f"🎯 Total Tokens: {result['total_tokens']}")
        
    else:
        print("❌ WORKFLOW FAILED!")
        print(f"Error: {result.get('error', 'Unknown error')}")

def test_breaking_news_workflow():
    """Test breaking news workflow"""
    print("\n🚨 Testing Breaking News Workflow")
    print("=" * 50)
    
    manager = ManagerAgent()
    result = manager.execute_breaking_news_workflow()
    print("result is :", result)
    if result.get("success"):
        if result.get("breaking_news_count", 0) > 0:
            print(f"🚨 {result['breaking_news_count']} BREAKING NEWS ALERTS!")
            
            for i, alert in enumerate(result["breaking_alerts"], 1):
                print(f"  {i}. {alert['headline']}")
                print(f"     🔥 Priority: {alert['priority']} | Urgency: {alert['urgency']}")
                print(f"     📝 {alert['summary']}")
                print()
        else:
            print("✅ No breaking news (good!)")
    else:
        print(f"❌ Breaking news check failed: {result.get('error')}")

if __name__ == "__main__":
    # Test complete manager workflow
    test_manager_workflow()
    
    # Test breaking news
    # test_breaking_news_workflow()
    
    # Show final token summary
    print("\n💰 Final Token Usage Summary:")
    summary = token_manager.get_daily_summary()
    print(f"Total tokens used today: {summary['total_tokens']}")
    print(f"Total cost today: ${summary['total_cost']:.4f}")
    print(f"Budget remaining: {summary['budget_remaining']} tokens")
    
    print("\n🎉 Manager Agent Testing Completed!")