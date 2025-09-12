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

        print("⚖️ Applying Category-Based Selection...")

        categories_to_fill = {
            "🇮🇳 India": 3,
            "🌍 World": 3,
            "🔬 SciTech": 3,
            "🌳 Bizarre & Amazing": 3
        }
        
        selected_articles_by_category = {cat: [] for cat in categories_to_fill.keys()}
        
        # Sort all articles by importance to ensure we consider the best ones first
        unique_ranked_articles.sort(key=lambda x: x.get('importance_score', 0), reverse=True)
        
        # Fill each category with its top stories
        for article in unique_ranked_articles:
            category = article.get("category")
            if category in categories_to_fill and len(selected_articles_by_category[category]) < categories_to_fill[category]:
                selected_articles_by_category[category].append(article)

        # Create the final flat list of articles to be processed
        promising_articles = []
        for cat_name, articles in selected_articles_by_category.items():
            promising_articles.extend(articles)
            print(f"✅ Selected {len(articles)} stories for category '{cat_name}'.")
            
        print(f"📰 Final selection: {len(promising_articles)} categorized stories for Creative Desk.")
        # END OF MODIFIED LOGIC

        # 4. STAGE 2 CREATIVE DESK: Process the selected categorized articles
        if not promising_articles:
             return {"success": True, "message": "No stories met the selection criteria.", "top_headlines": {}}

        creative_result = await self._stage2_creative_desk(promising_articles)
        if not creative_result.get("success") or not creative_result.get("headlines"):
            return {"success": False, "error": "Creative Desk stage failed."}

        # MODIFIED: Re-assemble the categorized dictionary after creative desk processing
        final_headlines_by_category = {cat: [] for cat in categories_to_fill.keys()}
        creative_headlines = creative_result.get("headlines", [])
        article_map = {i: article for i, article in enumerate(promising_articles, 1)}

        for creative_headline in creative_headlines:
            original_index = creative_headline.pop("original_index", None)
            if original_index and original_index in article_map:
                original_article = article_map[original_index]
                original_article.update(creative_headline)
                
                category = original_article.get("category")
                if category in final_headlines_by_category:
                    final_headlines_by_category[category].append(original_article)

        # 5. CACHE FINAL RESULTS: Flatten the dict to cache all stories
        all_final_headlines = [story for sublist in final_headlines_by_category.values() for story in sublist]
        await self._cache_final_results(all_final_headlines)

        total_token_usage = {
            "tokens": triage_result.get("token_usage", {}).get("tokens", 0) + creative_result.get("token_usage", {}).get("tokens", 0),
            "cost": triage_result.get("token_usage", {}).get("cost", 0) + creative_result.get("token_usage", {}).get("cost", 0)
        }

        return {
            "success": True,
            "articles_fetched": len(raw_articles),
            "articles_after_filtering": len(unique_articles),
            "articles_processed": len(all_final_headlines),
            "top_headlines": final_headlines_by_category,
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
        """Fast ranking, scoring, AND categorization of unique articles."""
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i}:\nTitle: {article['title']}\nDescription: {article['description'][:200]}..\n---\n"
        
        prompt = f"""
            You are a Section Editor for a digital news magazine. Your task is to evaluate, score, and CATEGORIZE each article.

            **Categories:**
            - "🇮🇳 India": Primary impact/focus is within India (politics, local business, domestic events).
            - "🌍 World": Significant geopolitical news, major events in other countries, conflicts.
            - "🔬 SciTech": Science, technology, space, and futuristic discoveries.
            - "🌳 Bizarre & Amazing": Unique, awe-inspiring, strange, or heartwarming stories. This is for the "wow factor".

            **Scoring:**
            1. `importance_score` (1-10): How impactful and need-to-know is this?
            2. `wow_factor_score` (1-10): How surprising, unique, or awe-inspiring is this?

            **Task:**
            For each article below, provide its category, importance_score, and wow_factor_score.

            Articles:\n{articles_text}

            Return ONLY valid JSON - score and categorize ALL articles:
            {{
                "ranked_articles": [
                    {{"index": 1, "category": "🇮🇳 India", "importance_score": 9.2, "wow_factor_score": 4.5}},
                    {{"index": 2, "category": "🌳 Bizarre & Amazing", "importance_score": 2.1, "wow_factor_score": 8.9}}
                ]
            }}
            """
        
        print("STAGE 1: TRIAGE - Applying 'Section Editor' model (Category, Importance, Wow Factor)...")
        response = await llm_client.smart_generate(prompt, max_tokens=25000, priority="normal")

        if "error" in response: return {"success": False, "error": response["error"]}
        
        try:
            content = re.sub(r"^```json|```$", "", response["content"].strip()).strip()
            ranked_data = json.loads(content).get("ranked_articles", [])
            
            ranked_articles = []
            for item in ranked_data:
                index = item.get("index")
                if index and 1 <= index <= len(articles):
                    article = articles[index - 1]
                    article['category'] = item.get("category", "🌍 World")
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

        **Highlighting Rule:**
        - For each headline, wrap the most important word(s) or phrase(s) that should be visually highlighted with |pipe| symbols. Example: "India officially BANS betting apps like |Dream11|".
        - Only use | | for 1-3 key words or phrases per headline.
        
        **Your Task:**
        Create distinct, varied headlines for these {len(articles)} stories. Each headline should feel different in tone and structure.
        Articles:{articles_text}
        Return JSON. IMPORTANT: You MUST include the `original_index` for each story exactly as it was provided in the input.
        {{
            "top_headlines": [
                {{
                    "original_index": 1,
                    "headline": "Clear and very simple english headline with |highlighted| words",
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
        response = await llm_client.smart_generate(prompt, max_tokens=25000, priority="normal")

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