# agents/news_hunter.py

import re
import json
import asyncio
from typing import List, Dict, Any

from core.token_manager import track_tokens
from core.llm_client import llm_client
from core.news_sources import NewsSourceManager
from core.semantic_cache import SemanticCache

class NewsHunterAgent:
    def __init__(self):
        self.news_sources = NewsSourceManager()
        self.semantic_cache = SemanticCache()

    @track_tokens("NewsHunter")
    async def hunt_daily_news(self, max_articles_to_fetch: int = 40, top_n_to_process: int = 5) -> Dict[str, Any]:
        """
        Finds the best stories using a two-stage funnel and caches only the final results.
        """
        print("🕵️ News Hunter Agent: Starting efficient two-stage news hunt...")

        # 1. FETCH
        raw_articles = self.news_sources.fetch_all_sources(max_articles=max_articles_to_fetch)
        print(f"📡 Fetched {len(raw_articles)} raw articles for triage.")
        if not raw_articles:
            return {"success": True, "message": "No raw articles found.", "top_headlines": []}

        # 2. TRIAGE (Cheap & Fast)
        triage_result = await self._stage1_triage(raw_articles)
        if not triage_result.get("success") or not triage_result.get("ranked_articles"):
            return {"success": False, "error": "Triage stage failed or returned no articles."}
        
        ranked_articles = triage_result.get("ranked_articles", [])

        # 3. CREATIVE DESK (Expensive & High-Quality)
        promising_articles = ranked_articles[:top_n_to_process]
        print(f"📰 Triage complete. Sending top {len(promising_articles)} promising articles to the Creative Desk.")
        creative_result = await self._stage2_creative_desk(promising_articles)
        if not creative_result.get("success") or not creative_result.get("headlines"):
            return {"success": False, "error": "Creative Desk stage failed or returned no headlines."}

        final_headlines = creative_result.get("headlines", [])

        # 4. CACHE (Efficient - Only on final, high-quality headlines)
        print("💾 Caching Stage: Generating embeddings and checking for duplicates on final headlines...")
        unique_final_headlines = []
        for headline_data in final_headlines:
            text_to_embed = f"{headline_data['headline']}\n{headline_data['summary']}"
            embedding = await llm_client.get_embedding(text_to_embed)
            if not embedding: continue

            if not self.semantic_cache.is_story_similar(embedding):
                print(f"✅ Unique final headline: '{headline_data['headline'][:50]}...'")
                unique_final_headlines.append(headline_data)
                story_id = str(abs(hash(f"{headline_data.get('original_title')}_{headline_data.get('source')}")))
                self.semantic_cache.add_story_embedding(story_id, embedding)
            else:
                print(f"SEMANTIC HIT: Skipping final headline as it's a duplicate of a past story: '{headline_data['headline'][:50]}...'")
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
            "top_headlines": unique_final_headlines,
            "token_usage": total_token_usage,
        }

    async def _stage1_triage(self, articles: List[Dict]) -> Dict[str, Any]:
        """Cheap, fast LLM call to rank a large number of articles by title only."""
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i}:\nTitle: {article['title']}\nDescription: {article['description'][:200]}..\n---\n"
        
        prompt = f"""
        You are an extremely fast news curator. Your only job is to rank articles by their potential to be viral or interesting and priority.
        Read these {len(articles)} articles. Based on the title and description, assign a 'viral_score' from 1-10.
        A high score means the story sounds shocking, emotionally engaging, or highly unusual or Amazing news.

        Article Titles and Descriptions:\n{articles_text}

        Return ONLY a valid JSON object with a single key "ranked_articles".
        Each item must include the article index and its score.
        Example: {{"ranked_articles": [{{"index": 1, "viral_score": 9.0}}, {{"index": 2, "viral_score": 3.7}}]}}
        """
        print("STAGE 1: TRIAGE - Ranking articles by title...")
        response = await llm_client.smart_generate(prompt, max_tokens=4000, priority="normal")

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
        """Processes the most promising articles with the high-quality 'ViralFeed' prompt."""
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i}:\nOriginal Title: {article['title']}\nSource: {article['source']}\nURL: {article['url']}\nDescription: {article['description'][:250]}...\n---\n"
        
        prompt = f"""
        You are the lead editor for 'ViralFeed', a digital news outlet famous for its edgy, highly-engaging, and easy-to-understand content for a young, internet-savvy audience. 
            Your goal is to get clicks, but NEVER at the expense of clarity. 
            The reader must understand the core of the story from the headline alone.

            **Your Style Guide:**
            1.  **Clarity First, Clickbait Second:** The headline MUST provide enough context for the reader to understand what the story is about. It should be intriguing, not confusing.
            2.  **Simple, Powerful Language:** Use everyday English. Avoid jargon.
            3.  **Inject Emotion & Conflict:** Frame stories around human elements: conflict, surprise, outrage, humor, or shock.
            4.  **The "Why" Factor:** Your summary must answer "Why should I care?" in 1-2 punchy sentences.

            **Crucial Example of What to Do (and Not Do):**
            - **Original Boring Headline:** "Air India Express operations affected as crew members report sick"
            - **BAD Viral Headline:** "Air India Pilots Are SCARED? Mass Sick Calls After HORRIFIC Crash!" (This is too vague, lacks context about the *consequence*.)
            - **GOOD Viral Headline:** "Mass 'Sick-Out' at Air India GROUNDS 80+ Flights After Crash - What's Really Happening?" (This is perfect. It has emotion, context (flights grounded), and a question to drive engagement.)

        **Your Task:**
        Analyze these {len(articles)} articles. Return ONLY a valid JSON object.
        {{
            "top_headlines": [
                {{
                    "headline": "Your new viral headline.",
                    "summary": "Your punchy summary.",
                    "priority": 9,
                    "category": "World News",
                    "original_title": "Original Title from Article",
                    "source": "Source Name from Article",
                    "url": "URL from Article"
                }}
            ]
        }}
        
        **Rules:**
        - If an article is not a real news story, EXCLUDE it from the JSON.
        - Do not repeat stories.

        **Articles to Process:**
        {articles_text}
        """
        
        print("STAGE 2: CREATIVE DESK - Generating polished headlines for top stories...")
        response = await llm_client.smart_generate(prompt, max_tokens=8000, priority="normal")

        if "error" in response: return {"success": False, "error": response["error"]}

        try:
            content = re.sub(r"^```json|```$", "", response["content"].strip()).strip()
            headlines = json.loads(content).get("top_headlines", [])
            return {"success": True, "headlines": headlines, "token_usage": response.get("token_usage")}
        except Exception as e:
            print(f"❌ Creative Desk stage failed to parse JSON: {e}")
            return {"success": False, "error": str(e)}
        
    @track_tokens("NewsHunter-Breaking")
    async def hunt_breaking_news(self) -> Dict[str, Any]:
        """Hunt specifically for breaking news"""
        print("🚨 News Hunter Agent: Checking for breaking news...")
        
        # Get breaking news articles
        breaking_articles = self.news_sources.get_breaking_news()
        
        if not breaking_articles:
            return {"success": True, "message": "No breaking news found", "articles": []}
        
        print(f"🚨 Found {len(breaking_articles)} breaking news articles")
        
        # Process breaking news with high priority
        processed_result = await self._process_breaking_news_with_llm(breaking_articles)
        
        if "error" in processed_result:
            return processed_result
        
        return {
            "success": True,
            "breaking_news_found": len(breaking_articles),
            "processed_breaking_news": processed_result["content"],
            "token_usage": processed_result["token_usage"]
        }
    
    async def _process_articles_with_llm(self, articles: List[Dict]) -> Dict[str, Any]:
        """Process articles using LLM for summarization and categorization"""
        
        # Create efficient prompt
        articles_text = self._format_articles_for_prompt(articles)
        
        prompt = f"""
            You are the lead editor for 'ViralFeed', a digital news outlet famous for its edgy, highly-engaging, and easy-to-understand content for a young, internet-savvy audience. 
            Your goal is to get clicks, but NEVER at the expense of clarity. 
            The reader must understand the core of the story from the headline alone.

            **Your Style Guide:**
            1.  **Clarity First, Clickbait Second:** The headline MUST provide enough context for the reader to understand what the story is about. It should be intriguing, not confusing.
            2.  **Simple, Powerful Language:** Use everyday English. Avoid jargon.
            3.  **Inject Emotion & Conflict:** Frame stories around human elements: conflict, surprise, outrage, humor, or shock.
            4.  **The "Why" Factor:** Your summary must answer "Why should I care?" in 1-2 punchy sentences.

            **Crucial Example of What to Do (and Not Do):**
            - **Original Boring Headline:** "Air India Express operations affected as crew members report sick"
            - **BAD Viral Headline:** "Air India Pilots Are SCARED? Mass Sick Calls After HORRIFIC Crash!" (This is too vague, lacks context about the *consequence*.)
            - **GOOD Viral Headline:** "Mass 'Sick-Out' at Air India GROUNDS 80+ Flights After Crash - What's Really Happening?" (This is perfect. It has emotion, context (flights grounded), and a question to drive engagement.)

            Your Task:
            Analyze these {len(articles)} news articles and return a JSON response:
            {articles_text}
            - The `headline` should be your new, viral-style headline.
            - The `summary` should be a short, punchy, 1-2 sentence explanation in the same style.
            - The `priority` score (1-10) must be based on VIRAL POTENTIAL and shocking and interesting news. A story about a celebrity feud or a shocking local event is a 10.
            - The `category` should be simple: 'Tech', 'Entertainment', 'World News', 'Finance', 'Oddly Specific'.
            - Add an `original_title` field to store the article's original title for caching.
            Return only the JSON object with this structure and dont make any error like forgetting comma or double quotes:
            {{
                "top_headlines": [
                    {{
                        "headline": "Your new viral headline here.",
                        "summary": "Your punchy, simple summary.",
                        "priority": give priority from 1 to 10,
                        "published" : "DD-MM-YYYY HH:MM:SS",
                        "category": "Entertainment",
                        "original_title": "Original Title from Article",
                        "source": "source name",
                        "url": "article url",
                    }}
                ]
            }}
            Rules -
            - "CRITICAL RULE: If an article is not a real news story (e.g., it's a site description, an ad, or a note), you MUST completely exclude it from your JSON output. Do not comment on it. Just ignore it. Your output must ONLY contain real news stories."
            - Dont repeat the story
            """
        print(f"Prompt for news hunter LLM:", prompt)
        # Use smart LLM generation
        return await llm_client.smart_generate(prompt, max_tokens=8000, priority="normal")

    async def _process_breaking_news_with_llm(self, articles: List[Dict]) -> Dict[str, Any]:
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
        return await llm_client.smart_generate(prompt, max_tokens=400, priority="critical")

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