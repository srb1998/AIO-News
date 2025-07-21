import re
from core.token_manager import track_tokens, token_manager
from core.llm_client import llm_client
from core.news_sources import NewsSourceManager
from typing import List, Dict, Any
import json

class NewsHunterAgent:
    def __init__(self):
        self.news_sources = NewsSourceManager()
    
    @track_tokens("NewsHunter")
    def hunt_daily_news(self, max_articles: int = 15) -> Dict[str, Any]:
        """Hunt for daily news articles and make engaging headlines"""
        print("🕵️ News Hunter Agent: Starting daily news hunt...")
        
        # Fetch articles from all sources
        raw_articles = self.news_sources.fetch_all_sources()
        print(f"📡 Fetched {len(raw_articles)} articles from sources")
        # print(f"🔍 Raw Articles are {raw_articles}")
        if not raw_articles:
            return {"error": "No articles found", "articles": []}
        
        print(f"📊 Found {len(raw_articles)} raw articles")
        
        # Limit articles to save tokens
        limited_articles = raw_articles[:max_articles]
        print(f"Limited articles: {limited_articles}")
        # Process articles with LLM
        processed_result = self._process_articles_with_llm(limited_articles)
        # print(f"Processed result from LLM: {processed_result}")
        if "error" in processed_result:
            return processed_result
        
        content = processed_result.get("content", "")
        cleaned = re.sub(r"^```json|```$", "", content.strip()).strip()
        structured = json.loads(cleaned) if cleaned else {}
        headlines = structured.get("top_headlines", [])
        headlines.sort(key=lambda x: x.get("priority", 0), reverse=True)
        breaking_news = structured.get("breaking_news", [])
        breaking_news.sort(key=lambda x: x.get("priority", 0), reverse=True)

        return {
            "success": True,
            "articles_processed": len(limited_articles),
            "top_headlines": headlines,
            "breaking_news": breaking_news,
            "token_usage": processed_result["token_usage"],
            "breaking_news_count": len([a for a in limited_articles if a['is_breaking']])
        }
    
    @track_tokens("NewsHunter-Breaking")
    def hunt_breaking_news(self) -> Dict[str, Any]:
        """Hunt specifically for breaking news"""
        print("🚨 News Hunter Agent: Checking for breaking news...")
        
        # Get breaking news articles
        breaking_articles = self.news_sources.get_breaking_news()
        
        if not breaking_articles:
            return {"success": True, "message": "No breaking news found", "articles": []}
        
        print(f"🚨 Found {len(breaking_articles)} breaking news articles")
        
        # Process breaking news with high priority
        processed_result = self._process_breaking_news_with_llm(breaking_articles)
        
        if "error" in processed_result:
            return processed_result
        
        return {
            "success": True,
            "breaking_news_found": len(breaking_articles),
            "processed_breaking_news": processed_result["content"],
            "token_usage": processed_result["token_usage"]
        }
    
    def _process_articles_with_llm(self, articles: List[Dict]) -> Dict[str, Any]:
        """Process articles using LLM for summarization and categorization"""
        
        # Create efficient prompt
        articles_text = self._format_articles_for_prompt(articles)
        
        prompt = f"""
            You are a master headline writer for a popular news platform. Create ENGAGING, 
            CLICKABLE headlines that make people WANT to read more.
            Analyze these {len(articles)} news articles and return a JSON response:
            Focus on: Clickbait headlines, engaging summaries, priority ranking.
            {articles_text}

            Return only the JSON object with this structure and dont make any error like forgetting comma or double quotes:
            {{
                "top_headlines": [
                    {{
                        "headline": "Engaging headline which can concisely summarize the article",
                        "summary": "2-3 sentence summary",
                        "published" : "DD-MM-YYYY HH:MM:SS",
                        "category": "tech/business/international",
                        "urgency": "high/medium/low",
                        "priority": give priority from 1 to 10,
                        "source": "source name",
                        "url": "article url",
                    }}
                ],
                "breaking_news": [
                    Same structure for urgent/breaking articles only
                ]
            }}

            Focus on:
            - International news, tech, and business
            - Clear, engaging headlines
            - Factual 2-sentence summaries
            - Proper categorization
            - Use human tone, avoid overly formal language
            - Prioritize urgency and importance
            - Remove duplicates
            - Don't include articles with Horoscope
            """
        print(f"Prompt for news hunter LLM:", prompt)
        # Use smart LLM generation
        return llm_client.smart_generate(prompt, max_tokens=6000, priority="normal")
    
    def _process_breaking_news_with_llm(self, articles: List[Dict]) -> Dict[str, Any]:
        """Process breaking news with high priority LLM"""
        
        articles_text = self._format_articles_for_prompt(articles)
        
        prompt = f"""
            URGENT: Process these {len(articles)} BREAKING NEWS articles:

            {articles_text}

            Return JSON with this structure:
            {{
                "urgent_alerts": [
                    {{
                        "headline": "urgent headline",
                        "summary": "key facts in 1-2 sentences",
                        "impact": "why this matters",
                        "source": "source name", 
                        "image_url": "image url if available"
                    }}
                ]
            }}

            Focus on:
            - Immediate impact and importance
            - Factual accuracy
            - Clear, urgent language
            - Essential details only
        """

        # Use high priority for breaking news
        return llm_client.smart_generate(prompt, max_tokens=400, priority="critical")
    
    def _format_articles_for_prompt(self, articles: List[Dict]) -> str:
        """Format articles efficiently for LLM prompt"""
        formatted = []
        
        for i, article in enumerate(articles, 1):
            formatted.append(f"""
                Article {i}:
                Title: {article['title']}
                Source: {article['source']} (Reliability: {article['reliability']}/10)
                url: {article['url']}
                Published: {article['published']}
                Description: {article['description'][:200]}...
                Breaking: {'YES' if article['is_breaking'] else 'NO'}
                """)
        
        return "\n".join(formatted)