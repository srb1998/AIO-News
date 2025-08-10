# agents/news_hunter.py

import re
import json
import asyncio
from typing import List, Dict, Any

from core.token_manager import track_tokens
from core.llm_client import llm_client
from core.news_sources import NewsSourceManager
from core.semantic_cache import SemanticCache
from core.story_cache import StoryCache

class NewsHunterAgent:
    def __init__(self):
        self.news_sources = NewsSourceManager()
        self.semantic_cache = SemanticCache()
        self.story_cache = StoryCache(max_age_seconds=86400)  # 24 hours cache

    @track_tokens("NewsHunter")
    async def hunt_daily_news(self, max_articles_to_fetch: int = 40, top_n_to_process: int = 5) -> Dict[str, Any]:
        """
        FIXED FLOW: Cache filtering happens BEFORE LLM stages to prevent repetitive processing
        """
        print("🕵️ News Hunter Agent: Starting efficient news hunt with pre-filtering...")

        # 1. FETCH RAW ARTICLES
        raw_articles = self.news_sources.fetch_all_sources(max_articles=max_articles_to_fetch)
        print(f"📡 Fetched {len(raw_articles)} raw articles.")
        if not raw_articles:
            return {"success": True, "message": "No raw articles found.", "top_headlines": []}

        # 2. PRE-FILTER: Remove exact duplicates and cached stories BEFORE LLM processing
        unique_articles = await self._pre_filter_articles(raw_articles)
        print(f"🔍 After pre-filtering: {len(unique_articles)} unique articles remaining.")
        
        if not unique_articles:
            return {"success": True, "message": "All articles were duplicates or cached.", "top_headlines": []}

        # 3. STAGE 1 TRIAGE: Only process truly unique articles
        triage_result = await self._stage1_triage(unique_articles)
        if not triage_result.get("success") or not triage_result.get("ranked_articles"):
            return {"success": False, "error": "Triage stage failed or returned no articles."}
        
        ranked_articles = triage_result.get("ranked_articles", [])

        # 4. STAGE 2 CREATIVE DESK: Process top articles
        promising_articles = ranked_articles[:top_n_to_process]
        print(f"📰 Sending top {len(promising_articles)} articles to Creative Desk.")
        creative_result = await self._stage2_creative_desk(promising_articles)
        if not creative_result.get("success") or not creative_result.get("headlines"):
            return {"success": False, "error": "Creative Desk stage failed."}

        final_headlines = creative_result.get("headlines", [])

        # 5. CACHE FINAL RESULTS: Add processed stories to cache for future filtering
        await self._cache_final_results(final_headlines)

        # Calculate total cost
        total_token_usage = {
            "tokens": triage_result.get("token_usage", {}).get("tokens", 0) + creative_result.get("token_usage", {}).get("tokens", 0),
            "cost": triage_result.get("token_usage", {}).get("cost", 0) + creative_result.get("token_usage", {}).get("cost", 0)
        }

        final_headlines.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return {
            "success": True,
            "articles_fetched": len(raw_articles),
            "articles_after_filtering": len(unique_articles),
            "articles_processed": len(promising_articles),
            "top_headlines": final_headlines,
            "token_usage": total_token_usage,
        }

    async def _pre_filter_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        Filter articles BEFORE LLM processing using both caches
        """
        unique_articles = []
        
        # Clean old cache entries first
        self.story_cache.prune_cache()
        
        for article in articles:
            title = article.get('title', '').strip()
            description = article.get('description', '').strip()
            
            # Skip if empty or invalid
            if not title or len(title) < 10:
                continue
                
            # 1. Check exact duplicate cache first (fast)
            if self.story_cache.has_story(title):
                print(f"EXACT HIT: Skipping '{title[:50]}...' - found in story cache")
                continue
            
            # 2. Check semantic similarity (slower but more thorough)
            text_to_embed = f"{title}\n{description[:200]}"
            embedding = await llm_client.get_embedding(text_to_embed)
            
            if not embedding:
                continue
                
            if self.semantic_cache.is_story_similar(embedding, threshold=0.35):  # Slightly stricter threshold
                print(f"SEMANTIC HIT: Skipping '{title[:50]}...' - semantically similar story found")
                continue
            
            # Article passed all filters
            unique_articles.append(article)
            await asyncio.sleep(0.02)  # Small delay to avoid rate limits
        
        return unique_articles

    async def _cache_final_results(self, headlines: List[Dict]):
        """
        Cache the final processed headlines to prevent future duplicates
        """
        for headline_data in headlines:
            # Add to exact match cache
            original_title = headline_data.get('original_title', headline_data.get('headline', ''))
            if original_title:
                self.story_cache.add_story(original_title)
            
            # Add to semantic cache
            text_to_embed = f"{headline_data['headline']}\n{headline_data.get('summary', '')}"
            embedding = await llm_client.get_embedding(text_to_embed)
            if embedding:
                story_id = str(abs(hash(f"{original_title}_{headline_data.get('source')}")))
                self.semantic_cache.add_story_embedding(story_id, embedding)
            
            await asyncio.sleep(0.02)

    async def _stage1_triage(self, articles: List[Dict]) -> Dict[str, Any]:
        """UNCHANGED: Fast ranking of unique articles"""
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i}:\nTitle: {article['title']}\nDescription: {article['description'][:200]}..\n---\n"
        
        prompt = f"""
        You are a fast news curator. Rank these {len(articles)} articles by viral potential and importance.
        Focus on: shocking news, major developments, unusual events, celebrity drama, political conflicts.
        Avoid: routine updates, minor incidents, technical announcements.
        
        Articles:\n{articles_text}

        Return ONLY valid JSON:
        {{"ranked_articles": [{{"index": 1, "viral_score": 9.0}}, {{"index": 2, "viral_score": 3}}]}}
        """
        
        print("STAGE 1: TRIAGE - Ranking unique articles...")
        response = await llm_client.smart_generate(prompt, max_tokens=8000, priority="normal")

        if "error" in response: return {"success": False, "error": response["error"]}
        
        try:
            content = re.sub(r"^```json|```$", "", response["content"].strip()).strip()
            ranked_data = json.loads(content).get("ranked_articles", [])
            
            ranked_articles = []
            for item in ranked_data:
                index = item.get("index")
                if index and 1 <= index <= len(articles):
                    article = articles[index - 1]
                    article['viral_score'] = item.get("viral_score", 0)
                    ranked_articles.append(article)
            
            ranked_articles.sort(key=lambda x: x['viral_score'], reverse=True)
            return {"success": True, "ranked_articles": ranked_articles, "token_usage": response.get("token_usage")}
        except Exception as e:
            print(f"❌ Triage parsing failed: {e}")
            return {"success": False, "error": str(e)}

    async def _stage2_creative_desk(self, articles: List[Dict]) -> Dict[str, Any]:
        """
        IMPROVED: Less repetitive headline generation with better style variety
        """
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i}:\nOriginal Title: {article['title']}\nSource: {article['source']}\nURL: {article['url']}\nDescription: {article['description'][:250]}...\n---\n"
        
        prompt = f"""
        You are a skilled news editor creating engaging headlines for Indian audiences. 

        **Style Variety Rules:**
        - Use different headline structures: questions, statements, dramatic reveals
        - Avoid repetitive words like "BOMBSHELL", "REVEALS", "DROPS" in every headline
        - Mix emotional tones: shocking, curious, informative, urgent
        - Focus on the ACTUAL NEWS impact, not just drama

        **Good Examples:**
        - "Trump Announces 50% Tariff on Indian Goods"
        - "Pakistan's Response to Operation Sindoor: Full Details Emerge" 
        - "Air India Crisis: 80+ Flights Cancelled as Pilots Strike Continues"

        **Your Task:**
        Create distinct, varied headlines for these {len(articles)} stories.
        Each headline should feel different in tone and structure.

        Articles:{articles_text}

        Return JSON:
        {{
            "top_headlines": [
                {{
                    "headline": "Clear, engaging headline",
                    "summary": "2-sentence explanation",
                    "priority": 8,
                    "category": "World News",
                    "original_title": "Original title",
                    "source": "Source name",
                    "url": "URL"
                }}
            ]
        }}
        
        Rules: Skip non-news content. Each headline must be unique in style and tone.
        """
        
        print("STAGE 2: CREATIVE DESK - Generating varied headlines...")
        response = await llm_client.smart_generate(prompt, max_tokens=8000, priority="normal")

        if "error" in response: return {"success": False, "error": response["error"]}

        try:
            content = re.sub(r"^```json|```$", "", response["content"].strip()).strip()
            headlines = json.loads(content).get("top_headlines", [])
            return {"success": True, "headlines": headlines, "token_usage": response.get("token_usage")}
        except Exception as e:
            print(f"❌ Creative Desk parsing failed: {e}")
            return {"success": False, "error": str(e)}
        
    def _format_articles_for_prompt(self, articles: List[Dict]) -> str:
        """Format articles for LLM prompt"""
        formatted = []
        
        for i, article in enumerate(articles, 1):
            formatted.append(f"""
                Article {i}:
                Original Title: {article['title']}
                Source: {article['source']} (Reliability: {article['reliability']}/10)
                url: {article['url']}
                Published: {article['published']}
                Description: {article['description'][:250]}...
                """)
        
        return "\n".join(formatted)