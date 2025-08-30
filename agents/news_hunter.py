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
    async def hunt_daily_news(self, max_articles_to_fetch: int = 40, top_n_to_process: int = 12) -> Dict[str, Any]:
        """
        FLOW: Cache filtering happens BEFORE LLM stages to prevent repetitive processing
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

        # This removes duplicates from the current run before selection.
        print(f"Deduplicating current batch of {len(ranked_articles)} articles...")
        seen_titles = set()
        unique_ranked_articles = []
        for article in ranked_articles:
            title = article.get('title', '').strip()
            if title not in seen_titles:
                unique_ranked_articles.append(article)
                seen_titles.add(title)
        print(f"Found {len(unique_ranked_articles)} unique articles after in-batch deduplication.")

        print("⚖️ Applying Strict Dual-Funnel Selection...")

        # Funnel 1: Top 5 by Importance
        unique_ranked_articles.sort(key=lambda x: x.get('importance_score', 0), reverse=True)
        important_stories = unique_ranked_articles[:5]
        print(f"✅ Selected {len(important_stories)} top stories for the 'Front Page'.")

        # Create a set of selected titles to avoid duplicates
        selected_titles = {story['title'] for story in important_stories}

        # Funnel 2: Top 5 by Curiosity from the remaining pool
        remaining_articles = [story for story in unique_ranked_articles if story['title'] not in selected_titles]
        
        wow_factor_threshold = 7.0
        high_wow_stories = [
            story for story in remaining_articles 
            if story.get('wow_factor_score', 0) >= wow_factor_threshold
        ]
        print(f"🔍 Applying 'Wow Factor' Quality Gate (Score >= {wow_factor_threshold})... Found {len(high_wow_stories)} qualifying stories.")

        high_wow_stories.sort(key=lambda x: x.get('wow_factor_score', 0), reverse=True)
        wow_stories = high_wow_stories[:5]

        # Combine the two funnels
        promising_articles = important_stories + wow_stories
        print(f"📰 Final selection: {len(promising_articles)} diverse stories for Creative Desk ({len(important_stories)} important + {len(wow_stories)} wow).")

        # 4. STAGE 2 CREATIVE DESK: Process the selected diverse articles
        if not promising_articles:
             return {"success": True, "message": "No stories met the selection criteria.", "top_headlines": []}
        
        creative_result = await self._stage2_creative_desk(promising_articles)
        if not creative_result.get("success") or not creative_result.get("headlines"):
            return {"success": False, "error": "Creative Desk stage failed."}

        final_headlines = []
        creative_headlines = creative_result.get("headlines", [])

        # Create a mapping from original index to the article data
        article_map = {i: article for i, article in enumerate(promising_articles, 1)}

        for creative_headline in creative_headlines:
            original_index = creative_headline.pop("original_index", None)
            if original_index and original_index in article_map:
                original_article = article_map[original_index]
                # Merge the new creative data with the original article data (including scores)
                original_article.update(creative_headline)
                final_headlines.append(original_article)

        # 5. CACHE FINAL RESULTS: Add processed stories to cache for future filtering
        await self._cache_final_results(final_headlines)

        # Calculate total cost
        total_token_usage = {
            "tokens": triage_result.get("token_usage", {}).get("tokens", 0) + creative_result.get("token_usage", {}).get("tokens", 0),
            "cost": triage_result.get("token_usage", {}).get("cost", 0) + creative_result.get("token_usage", {}).get("cost", 0)
        }

        # Sort final list by importance for presentation, but it contains the full mix
        final_headlines.sort(key=lambda x: x.get("importance_score", 0), reverse=True)
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
                
            # 1. Check exact duplicate cache first
            if self.story_cache.has_story(title):
                print(f"EXACT HIT: Skipping '{title[:50]}...' - found in story cache")
                continue
            
            # 2. Check semantic similarity
            text_to_embed = f"{title}\n{description[:200]}"
            embedding = await llm_client.get_embedding(text_to_embed)
            
            if not embedding:
                continue
                
            if self.semantic_cache.is_story_similar(embedding, threshold=0.35):
                print(f"SEMANTIC HIT: Skipping '{title[:50]}...' - semantically similar story found")
                continue
            
            # Article passed all filters
            unique_articles.append(article)
            await asyncio.sleep(0.02)
        
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
        """Fast ranking of unique articles"""
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i}:\nTitle: {article['title']}\nDescription: {article['description'][:200]}..\n---\n"
        
        prompt = f"""
            You are the chief editor of a digital news magazine. Your task is to evaluate articles for two separate sections: The Front Page (Importance) and The Features Section (Wow Factor). Provide two separate scores for each article.

            **1. `importance_score` (1-10): Is this "Front Page" material? Is it need-to-know?**
            - HIGH (8-10): Major policy changes (app bans), significant geopolitical events involving India, scientific breakthroughs with huge implications, medical miracles.
            - LOW (1-4): Routine politics, minor incidents, celebrity gossip, predictable sports results.

            **2. `wow_factor_score` (1-10): Is this "Features Section" material? Is it surprising, unique, omg type or awe-inspiring?**
            - HIGH (8-10): The truly unbelievable. Bizarre natural phenomena (sky turns pink), awe-inspiring achievements (man survives impossible odds), heartwarming animal stories, mind-bending discoveries (mushrooms communicating).
            - LOW (1-4): Predictable and mundane news.

            **IMPORTANT ANTI-EXAMPLES for "Wow Factor":**
            - The following are NOT high "wow_factor_score" stories: routine political debates, corporate earnings reports, murder cases, standard international relations updates. These are often important, but not "wow" or awe-inspiring.

            **Scoring Examples:**
            - "India successfully tests Agni-5 missile" -> importance_score: 9.5, wow_factor_score: 5.0
            - "Ujjain woman declared dead comes back to life" -> importance_score: 8.0, wow_factor_score: 9.8
            - "Scientists discover a planet made of diamond" -> importance_score: 6.5, wow_factor_score: 9.5
            - "Rare deep-sea squid filmed for the first time" -> importance_score: 2.0, wow_factor_score: 9.2

            Articles:\n{articles_text}

            Return ONLY valid JSON - score ALL articles:
            {{"ranked_articles": [{{"index": 1, "importance_score": 9.2, "wow_factor_score": 4.5}}, {{"index": 2, "importance_score": 2.1, "wow_factor_score": 8.9}}]}}
            """
        
        print("STAGE 1: TRIAGE - Ranking unique articles...")
        response = await llm_client.smart_generate(prompt, max_tokens=20000, priority="normal")

        if "error" in response: return {"success": False, "error": response["error"]}
        
        try:
            content = re.sub(r"^```json|```$", "", response["content"].strip()).strip()
            ranked_data = json.loads(content).get("ranked_articles", [])
            
            ranked_articles = []
            for item in ranked_data:
                index = item.get("index")
                if index and 1 <= index <= len(articles):
                    article = articles[index - 1]
                    article['importance_score'] = item.get("importance_score", 0)
                    article['wow_factor_score'] = item.get("wow_factor_score", 0)
                    ranked_articles.append(article)
            
            return {"success": True, "ranked_articles": ranked_articles, "token_usage": response.get("token_usage")}
        
        except Exception as e:
            print(f"❌ Triage parsing failed: {e}")
            return {"success": False, "error": str(e)}

    async def _stage2_creative_desk(self, articles: List[Dict]) -> Dict[str, Any]:
        """
        Less repetitive headline generation with better style variety
        """
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i} (original_index: {i}):\nOriginal Title: {article['title']}\nSource: {article['source']}\nURL: {article['url']}\nDescription: {article['description'][:250]}...\n---\n"
        
        prompt = f"""
        You are a skilled news editor creating engaging headlines for Indian audiences.

        **Good Examples:**
        - "Ujjain woman declared dead comes back to life on way to cremation"
        - "Scientists declare rainbows to go extinct from India soon"
        - "India officially BANS betting apps like Dream11"
        - "India successfully tests Agni-5 ballistic nuclear missile"
        - "Trump says india and russia dead economy"
        - "China and India getting close thanks to trump"

        **Bad Examples:**
        - "India Dares US: Russian Oil Imports Set to Surge Despite Tariff Threats!"
        - "Dark Clouds Over Green Energy: Trump Tariffs Cripple India's Solar Dreams!"
        - " Trump's Tariff Hammer Falls: India Eyes MORE Russian Oil Amidst 50% Export Hit!"

        **Your Task:**
        Create distinct, varied headlines for these {len(articles)} stories. Each headline should feel different in tone and structure.
        Articles:{articles_text}
        Return JSON. IMPORTANT: You MUST include the `original_index` for each story exactly as it was provided in the input.
        {{
            "top_headlines": [
                {{
                    "original_index": 1,
                    "headline": "Clear and very simple english headline",
                    "subheadline": "Short, punchy fun fact about the article",
                    "summary": "1-2 sentence summary",
                    "priority": 8,
                    "category": "World News",
                    "original_title": "Original title",
                    "source": "Source name",
                    "url": "URL"
                }}
            ]
        }}
        
        Rules: 
        - Skip non-news content. Each headline must be unique in style and tone.
        """
        
        print("STAGE 2: CREATIVE DESK - Generating varied headlines...")
        response = await llm_client.smart_generate(prompt, max_tokens=20000, priority="normal")

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