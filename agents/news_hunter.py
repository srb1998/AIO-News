import re
import json
import asyncio
from core.token_manager import track_tokens, token_manager
from core.llm_client import llm_client
from core.news_sources import NewsSourceManager
from typing import List, Dict, Any
from core.story_cache import StoryCache
from core.semantic_cache import SemanticCache

class NewsHunterAgent:
    def __init__(self):
        self.news_sources = NewsSourceManager()
        self.story_cache = StoryCache()
        self.semantic_cache = SemanticCache()

    @track_tokens("NewsHunter")
    async def hunt_daily_news(self, max_articles_to_fetch: int = 40, top_n_to_process: int = 5) -> Dict[str, Any]:
        """
        Finds the best stories using a two-stage filtering funnel.
        1. Triage: Scans a large number of articles cheaply to find promising candidates.
        2. Creative Desk: Processes the best candidates with a high-quality prompt.
        """
        print("🕵️ News Hunter Agent: Starting two-stage news hunt...")

        # Fetch a large number of articles
        raw_articles = self.news_sources.fetch_all_sources(max_articles=max_articles_to_fetch)
        print(f"📡 Fetched {len(raw_articles)} raw articles for triage.")

        unique_articles = await self._filter_semantic_duplicates(raw_articles)
        if not unique_articles:
            return {"success": True, "message": "No new unique articles found.", "top_headlines": []}
        
        # Run the cheap triage LLM call to rank the unique articles
        triage_result = await self._stage1_triage(unique_articles)
        if not triage_result.get("success"):
            return {"success": False, "error": "Triage stage failed."}
        
        ranked_articles = triage_result.get("ranked_articles", [])
        if not ranked_articles:
            return {"success": True, "message": "No articles passed the triage stage.", "top_headlines": []}
        
         # --- STAGE 2: CREATIVE DESK ---
        # Select the best N articles from triage to send to the expensive prompt
        promising_articles = ranked_articles[:top_n_to_process]
        print(f"📰 Triage complete. Sending top {len(promising_articles)} promising articles to the Creative Desk.")

        creative_result = await self._stage2_creative_desk(promising_articles)
        if not creative_result.get("success"):
            return {"success": False, "error": "Creative Desk stage failed."}
        
        # --- FINAL PROCESSING ---
        headlines = creative_result.get("headlines", [])

        for i, headline_data in enumerate(headlines):
            if i < len(promising_articles):
                embedding_to_add = promising_articles[i]['embedding']
                story_id = str(abs(hash(f"{headline_data.get('original_title')}_{headline_data.get('source')}")))
                self.semantic_cache.add_story_embedding(story_id, embedding_to_add)

        total_token_usage = {
            "tokens": triage_result.get("token_usage", {}).get("tokens", 0) + creative_result.get("token_usage", {}).get("tokens", 0),
            "cost": triage_result.get("token_usage", {}).get("cost", 0) + creative_result.get("token_usage", {}).get("cost", 0)
        }

        headlines.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return {
            "success": True,
            "articles_processed": len(promising_articles),
            "top_headlines": headlines,
            "token_usage": total_token_usage,
        }
    
    async def _filter_semantic_duplicates(self, articles: List[Dict]) -> List[Dict]:
        """Helper to generate embeddings and filter out semantic duplicates."""
        unique_articles_with_embeddings = []
        for article in articles:
            text_to_embed = f"{article['title']}\n{article['description']}"
            embedding = await llm_client.get_embedding(text_to_embed)
            if not embedding: continue

            if not self.semantic_cache.is_story_similar(embedding):
                article['embedding'] = embedding
                unique_articles_with_embeddings.append(article)
            else:
                print(f"SEMANTIC HIT: Skipping duplicate story '{article['title'][:50]}...'")
            await asyncio.sleep(0.05)
        return unique_articles_with_embeddings
    
    async def _stage1_triage(self, articles: List[Dict]) -> Dict[str, Any]:
        """
        Cheap, fast LLM call to rank a large number of articles by viral potential.
        """
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"Article {i}:\nTitle: {article['title']}\nDescription: {article['description'][:200]}..\n---\n"
        
        prompt = f"""
        You are a news curator. Your job is to be extremely fast and efficient.
        Read these {len(articles)} article titles and descriptions. For each one, assign a 'viral_score' from 1-10 based on its potential to be interesting, shocking, or emotionally engaging.

        {articles_text}

        Return ONLY a valid JSON object with a single key "ranked_articles".
        Each item must include the article index and its score.
        Example format:
        {{
            "ranked_articles": [
                {{"index": 1, "viral_score": 9}},
                {{"index": 2, "viral_score": 3}}
            ]
        }}
        """
        print("STAGE 1: TRIAGE - Ranking articles for viral potential...")
        print(f"Prompt for triage LLM:", prompt)
        response = await llm_client.smart_generate(prompt, max_tokens=4000, priority="normal")
        print(f"Response of stage1 triage {response}")
        if "error" in response: return {"success": False, "error": response["error"]}
        
        try:
            content = re.sub(r"^```json|```$", "", response["content"].strip()).strip()
            ranked_data = json.loads(content).get("ranked_articles", [])
            
            # Reconstruct the article list, sorted by the new score
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
        """
        Processes the most promising articles with the high-quality 'ViralFeed' prompt.
        This is the expensive, creative step.
        """
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"""
                Article {i}:
                Original Title: {article['title']}
                Source: {article['source']}
                URL: {article['url']}
                Description: {article['description'][:250]}...
                """
        
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
        
    # @track_tokens("NewsHunter")
    # async def hunt_daily_news(self, max_articles: int = 25) -> Dict[str, Any]:
    #     """Hunt for daily news articles and make engaging headlines"""
    #     print("🕵️ News Hunter Agent: Starting daily news hunt...")
        
    #     # Prune old stories from the cache before starting
    #     self.story_cache.prune_cache()

    #     # Fetch articles from all sources
    #     raw_articles = self.news_sources.fetch_all_sources()
    #     print(f"📡 Fetched {len(raw_articles)} articles from sources")
    #     # print(f"🔍 Raw Articles are {raw_articles}")

    #     unseen_articles_with_embeddings = []
    #     for article in raw_articles:
    #         # Use a combination of title and source to create a unique key
    #         text_to_embed = f"{article['title']}\n{article['description']}"
            
    #         embedding = await llm_client.get_embedding(text_to_embed)
    #         if not embedding:
    #             print(f"⚠️ Could not generate embedding for '{article['title'][:30]}...'. Skipping.")
    #             continue

    #         if not self.semantic_cache.is_story_similar(embedding):
    #             print(f"✅ Unique story found: '{article['title'][:50]}...'")
    #             # Store the embedding with the article to avoid generating it again
    #             article['embedding'] = embedding
    #             unseen_articles_with_embeddings.append(article)
    #         else:
    #             print(f"SEMANTIC HIT: Skipping duplicate story '{article['title'][:50]}...'")
            
    #         await asyncio.sleep(0.1) # Small delay to avoid hitting rate limits

    #     if not unseen_articles_with_embeddings:
    #         return {"success": True, "message": "No new unique articles to process.", "top_headlines": []}

    #     # Limit articles to save tokens
    #     limited_articles = unseen_articles_with_embeddings[:max_articles]
    #     # print(f"Limited articles: {limited_articles}")

    #     processed_result = await self._process_articles_with_llm(limited_articles)
    #     # print(f"Processed result from LLM: {processed_result}")
    #     if "error" in processed_result:
    #         return processed_result
        
    #     content = processed_result.get("content", "")
    #     try:
    #         cleaned = re.sub(r"^```json|```$", "", content.strip()).strip()
    #         structured = json.loads(cleaned) if cleaned else {}
    #     except json.JSONDecodeError as e:
    #         print(f"❌ JSON parsing failed in NewsHunter: {e}")
    #         return {"success": False, "error": "LLM returned invalid JSON."}
        
    #     headlines = structured.get("top_headlines", [])
        
    #     for i, headline_data in enumerate(headlines):
    #         if i < len(limited_articles):
    #             # Use the pre-calculated embedding
    #             embedding_to_add = limited_articles[i]['embedding']
    #             # Create a stable ID from the original title and source
    #             story_id = str(abs(hash(f"{headline_data.get('original_title')}_{headline_data.get('source')}")))
    #             self.semantic_cache.add_story_embedding(story_id, embedding_to_add)

        # headlines.sort(key=lambda x: x.get("priority", 0), reverse=True)
        # return {
        #     "success": True,
        #     "articles_processed": len(limited_articles),
        #     "top_headlines": headlines,
        #     "token_usage": processed_result["token_usage"],
        # }
    
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