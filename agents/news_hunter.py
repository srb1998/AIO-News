# agents/news_hunter.py - IMPROVED VERSION

import re
import json
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timedelta

from core.token_manager import track_tokens
from core.llm_client import llm_client
from core.news_sources import NewsSourceManager
from core.semantic_cache import SemanticCache

class NewsHunterAgent:
    def __init__(self):
        self.news_sources = NewsSourceManager()
        self.semantic_cache = SemanticCache()

    @track_tokens("NewsHunter")
    async def hunt_daily_news(self, max_articles_to_fetch: int = 40, top_n_to_process: int = 8) -> Dict[str, Any]:
        """
        Finds the best stories using a two-stage funnel with improved caching strategy.
        """
        print("🕵️ News Hunter Agent: Starting efficient two-stage news hunt...")

        # 1. FETCH
        raw_articles = self.news_sources.fetch_all_sources(max_articles=max_articles_to_fetch)
        print(f"📡 Fetched {len(raw_articles)} raw articles for triage.")
        if not raw_articles:
            return {"success": True, "message": "No raw articles found.", "top_headlines": []}

        # 2. PRE-FILTER: Remove already cached articles BEFORE triage to save tokens
        print("🔍 Pre-filtering: Removing already cached stories...")
        filtered_articles = await self._prefilter_cached_articles(raw_articles)
        print(f"📝 After pre-filtering: {len(filtered_articles)} articles remain")

        if len(filtered_articles) < 3:
            print("⚠️ Too few unique articles after pre-filtering. Expanding search...")
            # Increase processing count to get more variety
            top_n_to_process = min(len(filtered_articles), 15)
        
        # 3. TRIAGE (Cheap & Fast) - Now with better viral detection
        triage_result = await self._stage1_triage(filtered_articles)
        if not triage_result.get("success") or not triage_result.get("ranked_articles"):
            return {"success": False, "error": "Triage stage failed or returned no articles."}
        
        ranked_articles = triage_result.get("ranked_articles", [])

        # 4. CREATIVE DESK (Expensive & High-Quality)
        promising_articles = ranked_articles[:top_n_to_process]
        print(f"📰 Triage complete. Sending top {len(promising_articles)} promising articles to the Creative Desk.")
        creative_result = await self._stage2_creative_desk(promising_articles)
        if not creative_result.get("success") or not creative_result.get("headlines"):
            return {"success": False, "error": "Creative Desk stage failed or returned no headlines."}

        final_headlines = creative_result.get("headlines", [])

        # 5. FINAL CACHE CHECK (Only for exact duplicates, not semantic)
        print("💾 Final Cache: Adding new stories to cache...")
        unique_final_headlines = []
        for headline_data in final_headlines:
            text_to_embed = f"{headline_data['headline']}\n{headline_data['summary']}"
            embedding = await llm_client.get_embedding(text_to_embed)
            if not embedding: continue

            # Add to cache regardless (we already pre-filtered)
            unique_final_headlines.append(headline_data)
            story_id = str(abs(hash(f"{headline_data.get('original_title')}_{headline_data.get('source')}")))
            self.semantic_cache.add_story_embedding(story_id, embedding)
            print(f"✅ Added fresh headline: '{headline_data['headline'][:50]}...'")
            await asyncio.sleep(0.05)

        # Calculate total cost from both stages
        total_token_usage = {
            "tokens": triage_result.get("token_usage", {}).get("tokens", 0) + creative_result.get("token_usage", {}).get("tokens", 0),
            "cost": triage_result.get("token_usage", {}).get("cost", 0) + creative_result.get("token_usage", {}).get("cost", 0)
        }

        unique_final_headlines.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return {
            "success": True,
            "articles_processed": len(promising_articles),
            "top_headlines": unique_final_headlines[:5],
            "token_usage": total_token_usage,
        }

    async def _prefilter_cached_articles(self, articles: List[Dict]) -> List[Dict]:
        """Pre-filter articles against cache before expensive LLM processing"""
        filtered_articles = []
        
        for article in articles:
            # Create a simple text representation
            text_to_embed = f"{article['title']}\n{article.get('description', '')[:200]}"
            embedding = await llm_client.get_embedding(text_to_embed)
            
            if not embedding:
                continue
                
            # Use a stricter threshold for pre-filtering (only very similar stories)
            if not self.semantic_cache.is_story_similar(embedding, threshold=0.4):
                filtered_articles.append(article)
            else:
                print(f"🔄 Pre-filter: Skipping cached story: '{article['title'][:50]}...'")
            
            await asyncio.sleep(0.03)
        
        return filtered_articles

    async def _stage1_triage(self, articles: List[Dict]) -> Dict[str, Any]:
        """Enhanced triage that detects viral-worthy, amazing, and unusual stories"""
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i}:\nTitle: {article['title']}\nDescription: {article['description'][:300]}..\nSource: {article['source']}\n---\n"
        
        prompt = f"""
            You are a viral content curator with an eye for AMAZING stories that make people stop scrolling.

            Rate these {len(articles)} articles on VIRAL POTENTIAL (1-10 scale):

            **HIGH SCORES (8-10) for:**
            - Shocking/surprising revelations ("Man saves ₹36,500 buying MacBook in Vietnam")  
            - Incredible human achievements ("Meet world's rarest bird with rainbow feathers")
            - Unbelievable coincidences or irony
            - David vs Goliath stories (small person vs big corporation/system)
            - Mind-blowing discoveries or inventions
            - Heartwarming rescue stories
            - Celebrity drama/scandals
            - Economic hacks (travel, shopping, life hacks that save money)
            - Unusual animals, places, or phenomena
            - Stories that make you think "No way, that actually happened!"

            **MEDIUM SCORES (5-7) for:**
            - Important but predictable news (political statements, routine announcements)
            - Business earnings, routine government decisions
            - Sports results (unless truly historic)

            **LOW SCORES (1-4) for:**
            - Boring corporate news, routine updates
            - Technical jargon-heavy content
            - Overly complex policy discussions

            **Indian Audience Focus:** Prioritize stories with India connection OR universal human interest.

            Articles:
            {articles_text}

            Return ONLY valid JSON:
            {{"ranked_articles": [{{"index": 1, "viral_score": 9.2}}, {{"index": 2, "viral_score": 3.1}}]}}
        """
        
        print("STAGE 1: ENHANCED TRIAGE - Looking for viral-worthy stories...")
        response = await llm_client.smart_generate(prompt, max_tokens=5000, priority="normal")

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
            print(f"❌ Triage stage failed to parse JSON: {e}")
            return {"success": False, "error": str(e)}

    async def _stage2_creative_desk(self, articles: List[Dict]) -> Dict[str, Any]:
        """Enhanced creative desk with focus on amazing, viral headlines"""
        articles_text = ""
        for i, article in enumerate(articles, 1):
            viral_score = article.get('viral_score', 0)
            articles_text += f"""Article {i}: (Viral Score: {viral_score}/10)
                Original Title: {article['title']}
                Source: {article['source']}
                URL: {article['url']}
                Description: {article['description'][:300]}...
                ---
                """
        
        prompt = f"""
        You are the lead editor for 'ViralFeed India' - master of creating headlines that make people think "I HAVE to read this!"

        **Your Mission:** Create headlines for stories that are GENUINELY interesting, amazing, or shocking.

        **HEADLINE FORMULA for VIRAL SUCCESS:**
        1. **Curiosity Gap:** Make readers desperate to know more
        2. **Specific Numbers/Details:** "Saves ₹36,500" not "saves money"  
        3. **Emotion Words:** SHOCK, AMAZING, UNBELIEVABLE, GENIUS, DISASTER
        4. **Human Element:** Focus on people, not institutions
        5. **Clear Context:** Reader must understand what happened

        **PERFECT EXAMPLES:**
        - "Genius Indian Flies to Vietnam, Buys MacBook ₹36,500 Cheaper Than India + Free Holiday"
        - "World's Rarest Bird Found in India - Its Feathers Change 7 Different Colors!"
        - "Traffic Cop's ₹2 Jugaad Solves Mumbai's ₹200 Crore Problem - Engineers Shocked"
        - "Tesla Owner's Electricity Bill: ₹0 for 6 Months - Here's His Secret Trick"

        **STYLE RULES:**
        - Use specific amounts, numbers, timeframes
        - Focus on the AMAZING/SURPRISING aspect first
        - Keep it conversational, not news-reporter formal
        - Add context that makes non-Indians curious too

        Process these {len(articles)} articles:
        {articles_text}

        Return ONLY valid JSON:
        {{
            "top_headlines": [
                {{
                    "headline": "Your viral headline here",
                    "summary": "1-2 sentence punchy explanation of why this matters",
                    "priority": 8,
                    "category": "Amazing Stories",
                    "original_title": "Original article title",
                    "source": "Source name",
                    "url": "Article URL"
                }}
            ]
        }}

        **CRITICAL:** Only include stories that are genuinely interesting. Skip boring corporate/political routine news.
        """

        print("STAGE 2: ENHANCED CREATIVE DESK - Crafting viral headlines...")
        response = await llm_client.smart_generate(prompt, max_tokens=10000, priority="normal")

        if "error" in response: return {"success": False, "error": response["error"]}

        try:
            content = re.sub(r"^```json|```$", "", response["content"].strip()).strip()
            headlines = json.loads(content).get("top_headlines", [])
            return {"success": True, "headlines": headlines, "token_usage": response.get("token_usage")}
        except Exception as e:
            print(f"❌ Creative Desk stage failed to parse JSON: {e}")
            return {"success": False, "error": str(e)}

    def _format_articles_for_prompt(self, articles: List[Dict]) -> str:
        """Format articles efficiently for LLM prompt"""
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