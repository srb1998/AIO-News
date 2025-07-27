import httpx
import asyncio
from bs4 import BeautifulSoup
import time
import json
import re
from typing import List, Dict, Any
from urllib.parse import urlparse, urljoin
from core.token_manager import track_tokens
from core.llm_client import llm_client
from utils.cache_manager import cache_manager

class DetectiveAgent:
    def __init__(self):
        self.name = "detective"
        self.session = httpx.AsyncClient(headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }, timeout=10.0)
    
    @track_tokens("Detective")
    async def investigate_top_stories(self, top_headlines: List[Dict[str, Any]], max_stories: int = 5) -> Dict[str, Any]:
        """
        Main investigation method - takes top headlines and creates detailed research reports
        """
        print(f"🕵️ Detective Agent: Starting investigation of {len(top_headlines)} stories...")
        
        # Filter and sort by priority
        priority_stories = [h for h in top_headlines if h.get("priority", 0) >= 8]
        priority_stories.sort(key=lambda x: x.get("priority", 0), reverse=True)
        stories_to_investigate = priority_stories[:max_stories]
        
        print(f"🎯 Investigating top {len(stories_to_investigate)} priority stories...")
        
        if not stories_to_investigate:
            return {
                "success": True,
                "message": "No high-priority stories found for investigation",
                "investigation_reports": []
            }

        # Step 1: Extract content from source URLs (FREE)
        tasks = [self._extract_source_content(story) for story in stories_to_investigate]
        research_data = await asyncio.gather(*tasks)
        
        # Step 2: Batch analysis with LLM (EFFICIENT)
        analysis_result = await self._analyze_batch_with_llm(research_data)
        
        if "error" in analysis_result:
            return {"success": False, "error": analysis_result["error"]}
        
        # Step 3: Format research reports
        investigation_reports = self._format_research_reports(
            analysis_result["content"], 
            research_data
        )
        
        return {
            "success": True,
            "stories_investigated": len(stories_to_investigate),
            "investigation_reports": investigation_reports,
            "token_usage": analysis_result["token_usage"],
            "ready_for_script_writer": True
        }
    
    async def _extract_source_content(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract content from source URL + additional research (FREE methods)
        """
        cache_key = f"detective_content_{hash(story.get('headline', ''))}"
        cached_content = cache_manager.get(cache_key, expire_hours=24)
        
        if cached_content:
            print("📋 Using cached content...")
            return cached_content
        
        content_data = {
            "headline": story.get("headline", ""),
            "original_summary": story.get("summary", ""),
            "category": story.get("category", "general"),
            "priority": story.get("priority", 0),
            "source": story.get("source", "Unknown"),
            "source_url": story.get("url", ""),
            "extracted_content": "",
            "key_quotes": [],
            "statistics": [],
            "related_info": ""
        }
        
        # Extract from source URL if available
        source_url = story.get("url") or story.get("source_url")
        if source_url:
            extracted, additional_info = await asyncio.gather(
                self._scrape_article_content(source_url),
                self._get_duckduckgo_context(story["headline"])
            )

            content_data.update(extracted)
            content_data["related_info"] = additional_info
        
        # Cache the result
        cache_manager.set(cache_key, content_data, expire_hours=24)
        
        return content_data
    
    async def _scrape_article_content(self, url: str) -> Dict[str, Any]:
        """
        Scrape article content from URL (FREE web scraping)
        """
        try:
            print(f"🌐 Scraping: {urlparse(url).netloc}")
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            # Extract main content
            content_selectors = [
                'article', '[role="main"]', '.content', '.article-body', 
                '.story-body', '.post-content', 'main', '.entry-content'
            ]
            
            main_content = ""
            # for selector in content_selectors:
            #     content_elem = soup.select_one(selector)
            #     if content_elem:
            #         main_content = content_elem.get_text(strip=True)
            #         break
            
            # if not main_content:
            #     # Fallback: get all paragraph text
            #     paragraphs = soup.find_all('p')
            #     main_content = ' '.join([p.get_text(strip=True) for p in paragraphs])
            
            # Extract quotes (text in quotes)
            quotes = re.findall(r'"([^"]*)"', main_content)
            quotes = [q for q in quotes if len(q) > 20][:3]  # Top 3 substantial quotes
            
            # Extract statistics/numbers
            stats = re.findall(r'\b\d+(?:\.\d+)?%?\b(?:\s+(?:percent|million|billion|thousand|dollars?))?', main_content)
            stats = list(set(stats))[:5]  # Top 5 unique stats
            
            await asyncio.sleep(0.01)
            return {
                "content": main_content[:1500],  # Limit content to save tokens
                "quotes": quotes,
                "statistics": stats
            }
            
        except Exception as e:
            print(f"❌ Scraping failed for {url}: {str(e)}")
            return {"content": "", "quotes": [], "statistics": []}
    
    async def _get_duckduckgo_context(self, headline: str) -> str:
        """Gets DuckDuckGo context asynchronously."""
        try:
            query = ' '.join(headline.split()[:3])
            ddg_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
            
            # --- MODIFIED: Use await with the async client ---
            response = await self.session.get(ddg_url)
            response.raise_for_status()
            data = response.json()
            
            context_info = []
            if data.get("Abstract"): context_info.append(data["Abstract"])
            if data.get("RelatedTopics"):
                for topic in data["RelatedTopics"][:2]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        context_info.append(topic["Text"])
            
            print(f"🔎 DuckDuckGo context for '{headline[:30]}...': {'Found' if context_info else 'None'}")
            return " | ".join(context_info)
        except Exception as e:
            print(f"❌ DuckDuckGo context failed: {str(e)}")
            return ""

    async def _analyze_batch_with_llm(self, research_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze all research data in a single LLM call (EFFICIENT)
        """
        print("🧠 Analyzing research data with LLM...")
        
        # Create efficient batch prompt
        research_text = self._format_research_for_prompt(research_data)
        
        prompt = f"""
        You are a senior investigative journalist. Analyze these {len(research_data)} researched news stories and create detailed investigation reports.

        RESEARCH DATA:
        {research_text}

        For each story, provide deep analysis focusing on:
        - Key players and stakeholders involved
        - Verified facts and evidence
        - Potential impact and implications
        - Interesting angles for storytelling
        - Visual elements needed
        - Script presentation suggestions

        Return ONLY a JSON object with this structure:
        {{
            "investigation_reports": [
                {{
                    "story_id": 1,
                    "time": Example: "Hr,min,sec ago",
                    "importance_score": 1-10,
                    "research_summary": "2-3 sentence key findings from investigation",
                    "key_players": ["Person/Company A", "Person/Company B"],
                    "verified_facts": ["Fact 1 with numbers/data", "Fact 2 with evidence"],
                    "impact_analysis": "Why this matters and who it affects",
                    "story_angles": ["Angle 1: Human interest", "Angle 2: Economic impact"],
                    "script_suggestions": "How to present this story engagingly",
                    "visual_needs": [Give 2 examples only, "Chart showing X", "Photo of Y"],
                    "credibility_score": 1-10,
                    "follow_up_questions": ["What to investigate further?"]
                }}
            ]
        }}

        Focus on:
        - Factual accuracy and evidence-based analysis
        - Storytelling potential and human interest
        - Clear, actionable insights for script writers
        - Concrete visual suggestions
        - Credibility assessment of sources
        """
        print(f"📝 Prompt for Detective LLM:\n{prompt}")
        # Use smart LLM generation (Gemini first, OpenAI fallback)
        return await llm_client.smart_generate(prompt, max_tokens=8000, priority="normal")
    
    def _format_research_for_prompt(self, research_data: List[Dict[str, Any]]) -> str:
        """
        Format research data efficiently for LLM prompt
        """
        formatted = []
        
        for i, data in enumerate(research_data, 1):
            story_text = f"""
            STORY {i}:
            Headline: {data['headline']}
            Category: {data['category']} | Priority: {data['priority']}
            Source: {data['source']}
            
            Original Summary: {data['original_summary']}
            
            Extracted Content: {data['extracted_content'][:800]}...
            
            Key Quotes Found: {', '.join(data['key_quotes'][:2])}
            
            Statistics Found: {', '.join(data['statistics'][:3])}
            
            Additional Context: {data['related_info'][:300]}
            
            ---
            """
            formatted.append(story_text)
        
        return "\n".join(formatted)
    
    def _format_research_reports(self, llm_content: str, research_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format LLM analysis into structured reports
        """
        try:
            # Clean and parse JSON response
            cleaned_content = re.sub(r"^```json|```$", "", llm_content.strip()).strip()
            analysis_data = json.loads(cleaned_content)
            
            reports = analysis_data.get("investigation_reports", [])
            
            # Enhance reports with original data
            enhanced_reports = []
            for i, report in enumerate(reports):
                if i < len(research_data):
                    original_data = research_data[i]
                    
                    enhanced_report = {
                        **report,
                        "original_headline": original_data["headline"],
                        "original_summary": original_data["original_summary"],
                        "source": original_data["source"],
                        "source_url": original_data["source_url"],
                        "category": original_data["category"],
                        "investigation_timestamp": time.time(),
                        "content_extracted": bool(original_data["extracted_content"]),
                        "quotes_found": len(original_data["key_quotes"]),
                        "stats_found": len(original_data["statistics"])
                    }
                    
                    enhanced_reports.append(enhanced_report)
            
            return enhanced_reports
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing failed: {e}")
            # Fallback: create basic reports from research data
            return self._create_fallback_reports(research_data)
        except Exception as e:
            print(f"❌ Report formatting failed: {e}")
            return self._create_fallback_reports(research_data)
    
    def _create_fallback_reports(self, research_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create basic reports when LLM analysis fails
        """
        fallback_reports = []
        
        for data in research_data:
            report = {
                "story_id": len(fallback_reports) + 1,
                "original_headline": data["headline"],
                "original_summary": data["original_summary"],
                "importance_score": data["priority"],
                "research_summary": f"Investigation of {data['headline']} from {data['source']}",
                "key_players": [],
                "verified_facts": data["statistics"][:3] if data["statistics"] else [],
                "impact_analysis": "Requires further analysis",
                "story_angles": [f"{data['category']} impact analysis"],
                "script_suggestions": f"Present as {data['category']} story with focus on key facts",
                "visual_needs": ["Stock photo", "Text overlay with key stats"],
                "credibility_score": 7,  # Default medium credibility
                "source": data["source"],
                "category": data["category"],
                "investigation_timestamp": time.time(),
                "content_extracted": bool(data["extracted_content"]),
                "quotes_found": len(data["key_quotes"]),
                "stats_found": len(data["statistics"])
            }
            
            fallback_reports.append(report)
        
        return fallback_reports