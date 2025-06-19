from agents.news_hunter import NewsHunterAgent
from core.token_manager import token_manager
import json

def test_daily_news_hunt():
    """Test the daily news hunting functionality"""
    print("🚀 Starting AI News Agency - Daily News Test")
    print("=" * 50)
    
    # Initialize News Hunter Agent
    news_hunter = NewsHunterAgent()
    
    # Hunt for daily news
    result = news_hunter.hunt_daily_news(max_articles=10)
    
    if result.get("success"):
        print("✅ Daily news hunt successful!")
        print(f"📊 Articles processed: {result['articles_processed']}")
        print(f"🚨 Breaking news found: {result['breaking_news_count']}")
        
        # Try to parse the LLM response
        try:
            if isinstance(result['processed_articles'], str):
                processed = json.loads(result['processed_articles'])
            else:
                processed = result['processed_articles']
            
            print(f"\n📰 Top Headlines ({len(processed.get('top_headlines', []))}):")
            for i, headline in enumerate(processed.get('top_headlines', [])[:5], 1):
                print(f"{i}. {headline.get('title', 'N/A')}")
                print(f"   📁 {headline.get('category', 'N/A')} | 🔥 {headline.get('urgency', 'N/A')}")
                print(f"   📝 {headline.get('summary', 'N/A')}")
                print()
        
        except json.JSONDecodeError:
            print("📄 Raw LLM Response:")
            print(result['processed_articles'])
    
    else:
        print("❌ Daily news hunt failed!")
        print(f"Error: {result.get('error', 'Unknown error')}")
    
    # Show token usage summary
    print("\n💰 Token Usage Summary:")
    summary = token_manager.get_daily_summary()
    print(f"Total tokens used: {summary['total_tokens']}")
    print(f"Total cost: ${summary['total_cost']:.4f}")
    print(f"Budget remaining: {summary['budget_remaining']} tokens")
    
    for agent_name, usage in summary['agents'].items():
        print(f"  {agent_name}: {usage['total_tokens']} tokens (${usage['total_cost']:.4f})")

def test_breaking_news():
    """Test breaking news functionality"""
    print("\n🚨 Testing Breaking News Detection")
    print("=" * 50)
    
    news_hunter = NewsHunterAgent()
    result = news_hunter.hunt_breaking_news()
    
    if result.get("success"):
        if result.get("breaking_news_found", 0) > 0:
            print(f"🚨 Found {result['breaking_news_found']} breaking news articles!")
            
            try:
                if isinstance(result['processed_breaking_news'], str):
                    processed = json.loads(result['processed_breaking_news'])
                else:
                    processed = result['processed_breaking_news']
                
                print("\n🚨 Urgent Alerts:")
                for i, alert in enumerate(processed.get('urgent_alerts', []), 1):
                    print(f"{i}. {alert.get('headline', 'N/A')}")
                    print(f"   📝 {alert.get('summary', 'N/A')}")
                    print(f"   💥 Impact: {alert.get('impact', 'N/A')}")
                    print()
            
            except json.JSONDecodeError:
                print("📄 Raw Breaking News Response:")
                print(result['processed_breaking_news'])
        else:
            print("✅ No breaking news found (which is good!)")
    else:
        print("❌ Breaking news check failed!")

if __name__ == "__main__":
    # Test daily news hunt
    test_daily_news_hunt()
    
    # Test breaking news  
    test_breaking_news()
    
    print("\n🎉 Testing completed!")
    print("Check the 'data/token_usage.json' file for detailed token tracking.")