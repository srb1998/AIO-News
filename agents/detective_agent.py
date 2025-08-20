# detective_agent.py

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
from config.settings import settings

class DetectiveAgent:
    def __init__(self):
        self.name = "detective"
        self.session = httpx.AsyncClient(headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }, timeout=10.0)
        
        # Initialize Brave Search for AI grounding
        self.brave_api_key = settings.BRAVE_API_KEY
        self.brave_ai_url = "https://api.search.brave.com/res/v1/chat/completions"
    
    @track_tokens("Detective")
    async def investigate_top_stories(self, top_headlines: List[Dict[str, Any]], max_stories: int = 5) -> Dict[str, Any]:
        """
        Main investigation method. Processes stories SEQUENTIALLY using the Brave AI Grounding API
        to provide rich context while respecting API rate limits.
        """
        print(f"🕵️ Detective Agent: Starting investigation of {len(top_headlines)} stories...")

        # Prioritize stories to investigate
        stories_to_investigate = self._prioritize_stories(top_headlines, max_stories)

        if not stories_to_investigate:
            return {
                "success": True,
                "message": "No high-priority stories found for investigation.",
                "investigation_reports": []
            }

        print(f"🎯 Investigating top {len(stories_to_investigate)} priority stories one by one...")

        # Process each story sequentially to prevent rate-limiting ---
        enhanced_research_data = []
        for story in stories_to_investigate:
            print(f"\n--- Investigating Story: {story['headline'][:60]}... ---")
            # This function now contains the single, powerful AI Grounding API call
            enhanced_data = await self._enhanced_extract_content(story)
            enhanced_research_data.append(enhanced_data)

            # A small delay between processing each story is a crucial safety measure
            await asyncio.sleep(1.0) 

        # After all research is complete, analyze the collected data in a single batch
        print("\n🧠 All research complete. Sending collected data for deep analysis...")
        analysis_result = await self._enhanced_analyze_with_llm(enhanced_research_data)

        if "error" in analysis_result:
            return {"success": False, "error": analysis_result["error"]}

        # Format the final reports
        investigation_reports = self._format_enhanced_reports(
            analysis_result["content"], 
            enhanced_research_data
        )

        return {
            "success": True,
            "stories_investigated": len(stories_to_investigate),
            "investigation_reports": investigation_reports,
            "token_usage": analysis_result.get("token_usage", {}),
            "ready_for_script_writer": True,
            "enhanced_data_sources": "Brave AI Grounding API"
        }
    
    async def _enhanced_extract_content(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        Uses the Brave AI Grounding API for research.
        """
        cache_key = f"enhanced_detective_{hash(story.get('headline', ''))}"
        if cached_content := cache_manager.get(cache_key, expire_hours=12):
            print("📋 Using cached enhanced content...")
            return cached_content
        
        content_data = { "headline": story.get("headline", ""), "subheadline": story.get("subheadline", ""), **self._get_empty_content_dict() }
        
        # Run non-rate-limited tasks concurrently
        source_url = story.get("url") or story.get("source_url")
        other_tasks = [
            self._scrape_article_content(source_url) if source_url else self._empty_scrape_result(),
            self._get_duckduckgo_context(story["headline"])
        ]
        other_results = await asyncio.gather(*other_tasks)
        scraped_data, ddg_context = other_results[0], other_results[1]
        
        # Make a single, powerful call to the Brave AI Grounding API
        ai_grounding_data = await self._brave_ai_grounding(story["headline"])
        
        # Merge all data sources
        content_data.update(scraped_data)
        content_data["related_info"] = ddg_context
        if ai_grounding_data.get("success"):
            content_data.update(ai_grounding_data["data"])
            content_data["data_sources_count"] = 1
        
        cache_manager.set(cache_key, content_data, expire_hours=12)
        print(f"✅ Enhanced extraction complete. AI Grounding Success: {ai_grounding_data.get('success', False)}")
        return content_data

    async def _brave_ai_grounding(self, headline: str) -> Dict[str, Any]:
        """
        Use Brave Search API for AI grounding with specific search strategies
        """
        try:
            # Create comprehensive question for AI instead of search query
            ai_prompt = f"""
            Please provide detailed information about: "{headline}"

            I need:
            1. Key facts and statistics
            2. Recent developments and updates  
            3. Background context and history
            4. Expert opinions or analysis
            5. Official statements or positions
            6. Important quotes if available

            Format your response with clear sections for each type of information.
            """
            
            print(f"🤖 AI Grounding request: {headline[:50]}...")
        
            payload = {
                "messages": [
                    {
                        "role": "user", 
                        "content": ai_prompt
                    }
                ],
                "stream": False
            }
            
            headers = {
                "x-subscription-token": self.brave_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            response = await self.session.post(
                self.brave_ai_url,
                headers=headers,
                json=payload,
                timeout=20 
            )
            
            response.raise_for_status()
            data = response.json()
            print(f"🤖 AI Grounding response: {data}")

            ai_response = data["choices"][0]["message"]["content"]
            
            print(f"✅ AI Grounding success: {len(ai_response)} chars")
            
            parsed_data = self._parse_ai_response(ai_response)
            
            return {
                "success": True,
                "data": parsed_data,
                "raw_response": ai_response[:500] + "..." if len(ai_response) > 500 else ai_response
            }
            
        except Exception as e:
            print(f"❌ Brave AI Grounding failed: {e}")
            return {"success": False, "error": str(e)}

    def _parse_ai_response(self, ai_response: str) -> Dict[str, Any]:
        """
        Parses the structured text response from the Brave AI.
        """
        parsed = self._get_empty_content_dict()
        
        # Use regex to find sections like "1. Key Facts", "Recent Developments:", etc.
        for key, pattern in self._get_parsing_patterns().items():
            match = re.search(pattern, ai_response, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1).strip()
                # Split bullet points into a list
                items = [item.strip() for item in re.split(r'\n\s*[-•*]\s*', content) if len(item.strip()) > 10]
                if key == "background_context":
                    parsed[key] = content[:800] # Keep as a single text block
                else:
                    parsed[key] = items[:5] # Limit to 5 items per section

        # Fallback if no sections were parsed
        if not any(parsed.values()):
            print("⚠️ AI response was unstructured, using fallback sentence parsing.")
            sentences = [s.strip() for s in re.split(r'[.!?]+', ai_response) if len(s.strip()) > 30]
            parsed["verified_facts"] = sentences[:4]
            parsed["recent_developments"] = sentences[4:7]
        
        print(f"📊 Parsed AI response: {len(parsed['verified_facts'])} facts, {len(parsed['recent_developments'])} developments.")
        return parsed
    
    def _prioritize_stories(self, headlines: List[Dict[str, Any]], max_stories: int) -> List[Dict[str, Any]]:
        """Filters and sorts stories by priority."""
        priority_stories = [h for h in headlines if h.get("priority", 0) >= 7]
        priority_stories.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return priority_stories[:max_stories]

    def _get_empty_content_dict(self) -> Dict:
        """Returns a consistent empty dictionary structure with ALL needed fields."""
        return {
            # Story metadata
            "original_summary": "",
            "category": "general", 
            "priority": 0,
            "source": "Unknown",
            "source_url": "",
            "extracted_content": "",
            "related_info": "",
            "data_sources_count": 0,
            
            # AI Grounding data
            "verified_facts": [],
            "recent_developments": [], 
            "expert_opinions": [],
            "background_context": "",
            "official_statements": [],
            "key_quotes": [],
            "statistics": []
        }

    def _get_parsing_patterns(self) -> Dict:
        """Returns regex patterns for parsing the AI response."""
        return {
            "verified_facts": r"(?:Key Facts|Facts & Statistics|Key Facts & Statistics):?\n(.*?)(?:\n\n|\Z|2\.)",
            "recent_developments": r"(?:Recent Developments):?\n(.*?)(?:\n\n|\Z|3\.)",
            "background_context": r"(?:Background Context|Background):?\n(.*?)(?:\n\n|\Z|4\.)",
            "expert_opinions": r"(?:Expert Opinions|Expert Analysis):?\n(.*?)(?:\n\n|\Z|5\.)",
            "official_statements": r"(?:Official Statements|Official Positions):?\n(.*?)(?:\n\n|\Z|6\.)",
        }

    async def _enhanced_analyze_with_llm(self, enhanced_research_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
         Analyze comprehensive research data with detailed prompting
        """
        print("🧠 Enhanced LLM analysis with comprehensive data...")
        
        # Create enhanced batch prompt with all available data
        research_text = self._format_enhanced_research(enhanced_research_data)
        
        prompt = f"""
        You are a senior investigative journalist with access to comprehensive research data. Analyze these {len(enhanced_research_data)} stories and create detailed, SPECIFIC investigation reports.

        COMPREHENSIVE RESEARCH DATA:
        {research_text}

        CRITICAL INSTRUCTIONS:
        - Use SPECIFIC facts, numbers, and verified information from the research
        - Include recent developments and timeline information  
        - Reference expert opinions and official statements when available
        - Provide concrete impact analysis with specific examples
        - Suggest detailed visual elements based on actual story content
        - Create engaging story angles that go beyond basic facts
        - Focus on Indian perspective and current global context (Trump presidency)
        - NO generic statements - everything must be specific to the story

        For each story, provide DETAILED analysis:

        Return ONLY a JSON object:
        {{
            "investigation_reports": [
                {{
                    "story_id": 1,
                    "time_relevance": "Why this story matters RIGHT NOW - specific timing",
                    "importance_score": 1-10,
                    "research_summary": "SPECIFIC findings with concrete details and numbers from investigation",
                    "key_players": ["Specific Person/Organization with their role", "Another specific entity"],
                    "verified_facts": ["Specific fact with number/data from research", "Another concrete verified fact"],
                    "recent_developments": ["What happened in last 24-48 hours - specific events"],
                    "impact_analysis": "WHO is affected and HOW - with specific examples and potential consequences",
                    "story_angles": ["Unique angle 1 with specific focus", "Different perspective with concrete reasoning"],
                    "expert_insights": ["Specific expert opinion from research", "Another expert viewpoint with context"],
                    "official_positions": ["Government/organization stance with details"],
                    "script_suggestions": "HOW to present this story - specific narrative structure and key points to emphasize",
                    "visual_needs": ["Specific visual 1 with exact requirement", "Specific visual 2 with clear description"],
                    "credibility_score": 1-10,
                    "follow_up_questions": ["Specific investigative question based on gaps found"],
                    "background_context": "Essential background that audience needs to understand this story",
                    "indian_perspective": "How this specifically affects/relates to India and Indians"
                }}
            ]
        }}

        Focus on creating RICH, DETAILED content that gives script writers substantial material to work with.
        """
        
        return await llm_client.smart_generate(prompt, max_tokens=12000, priority="normal")

    def _format_enhanced_research(self, enhanced_data: List[Dict[str, Any]]) -> str:
        """
        NEW: Format enhanced research data for comprehensive LLM analysis
        """
        formatted = []
        
        for i, data in enumerate(enhanced_data, 1):
            story_text = f"""
            STORY {i} - COMPREHENSIVE DATA:
            Headline: {data['headline']}
            Category: {data['category']} | Priority: {data['priority']}
            Source: {data['source']}
            
            Original Summary: {data['original_summary']}
            
            SCRAPED CONTENT: {data['extracted_content'][:600]}...
            
            VERIFIED FACTS FROM BRAVE AI:
            {chr(10).join(f"- {fact}" for fact in data['verified_facts'][:5])}
            
            RECENT DEVELOPMENTS:
            {chr(10).join(f"- {dev}" for dev in data['recent_developments'][:4])}
            
            BACKGROUND CONTEXT: {data['background_context'][:400]}
            
            EXPERT OPINIONS:
            {chr(10).join(f"- {opinion}" for opinion in data['expert_opinions'][:3])}
            
            OFFICIAL STATEMENTS:
            {chr(10).join(f"- {statement}" for statement in data['official_statements'][:2])}
            
            KEY QUOTES: {', '.join(data['key_quotes'][:3])}
            STATISTICS: {', '.join(data['statistics'][:4])}
            ADDITIONAL CONTEXT: {data['related_info'][:200]}
            
            DATA QUALITY: {data['data_sources_count']}/3 enhanced sources + original
            
            ---
            """
            formatted.append(story_text)
        
        return "\n".join(formatted)

    def _format_enhanced_reports(self, llm_content: str, enhanced_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
         Format LLM analysis with additional research data
        """
        try:
            cleaned_content = re.sub(r"^```json|```$", "", llm_content.strip()).strip()
            analysis_data = json.loads(cleaned_content)
            
            reports = analysis_data.get("investigation_reports", [])
            
            enhanced_reports = []
            for i, report in enumerate(reports):
                if i < len(enhanced_data):
                    original_data = enhanced_data[i]
                    
                    enhanced_report = {
                        **report,
                        "original_headline": original_data["headline"],
                        "subheadline": original_data.get("subheadline", ""),
                        "original_summary": original_data["original_summary"],
                        "source": original_data["source"],
                        "source_url": original_data["source_url"],
                        "category": original_data["category"],
                        "investigation_timestamp": time.time(),
                        "content_extracted": bool(original_data["extracted_content"]),
                        "quotes_found": len(original_data["key_quotes"]),
                        "stats_found": len(original_data["statistics"]),
                        #  Additional metadata
                        "brave_facts_count": len(original_data["verified_facts"]),
                        "recent_developments_count": len(original_data["recent_developments"]),
                        "expert_opinions_count": len(original_data["expert_opinions"]),
                        "data_quality_score": original_data["data_sources_count"],
                        "enhanced_investigation": True
                    }
                    
                    enhanced_reports.append(enhanced_report)
            
            return enhanced_reports
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing failed: {e}")
            return self._create_enhanced_fallback_reports(enhanced_data)
        except Exception as e:
            print(f"❌ Report formatting failed: {e}")
            return self._create_enhanced_fallback_reports(enhanced_data)

    def _create_enhanced_fallback_reports(self, enhanced_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
         Create detailed fallback reports with available data
        """
        fallback_reports = []
        print("Creating enhanced fallback reports...")
        for data in enhanced_data:
            report = {
                "story_id": len(fallback_reports) + 1,
                "original_headline": data["headline"],
                "original_summary": data["original_summary"],
                "importance_score": data["priority"],
                "research_summary": f"Enhanced investigation of {data['headline']} with {data['data_sources_count']} data sources",
                "key_players": [],
                "verified_facts": data["verified_facts"][:3],
                "recent_developments": data["recent_developments"][:2],
                "impact_analysis": "Comprehensive analysis available from multiple sources",
                "story_angles": [f"{data['category']} perspective", "Recent developments analysis"],
                "expert_insights": data["expert_opinions"][:2],
                "official_positions": data["official_statements"][:1],
                "script_suggestions": f"Present as developing {data['category']} story with emphasis on recent facts",
                "visual_needs": ["Relevant news graphic", "Statistical chart if applicable"],
                "credibility_score": 7,
                "background_context": data["background_context"][:200],
                "source": data["source"],
                "category": data["category"],
                "investigation_timestamp": time.time(),
                "enhanced_investigation": True,
                "data_quality_score": data["data_sources_count"]
            }
            
            fallback_reports.append(report)
        
        return fallback_reports

    async def _empty_scrape_result(self):
        """Return empty scrape result when no URL available"""
        return {"content": "", "quotes": [], "statistics": []}

    # Keep all existing methods unchanged
    async def _scrape_article_content(self, url: str) -> Dict[str, Any]:
        """Original scraping method - unchanged"""
        try:
            print(f"🌐 Scraping: {urlparse(url).netloc}")
            
            response = await self.session.get(url)
            response.raise_for_status()
            
            html_content = response.content

            def parse_html(content):
                soup = BeautifulSoup(content, 'html.parser')
                
                for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                    element.decompose()
                
                content_selectors = ['article', '.article-body', '.story-body', 'main']
                main_content = ""
                for selector in content_selectors:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        main_content = content_elem.get_text(strip=True)
                        break
                
                if not main_content:
                    paragraphs = soup.find_all('p')
                    main_content = ' '.join([p.get_text(strip=True) for p in paragraphs])
                
                quotes = re.findall(r'"(.*?)"', main_content)
                quotes = [q for q in quotes if len(q) > 20][:3]
                
                stats = re.findall(r'\b\d+(?:\.\d+)?%?\b', main_content)
                stats = list(set(stats))[:5]
                
                return {
                    "content": main_content[:2000],
                    "quotes": quotes,
                    "statistics": stats
                }

            parsed_data = await asyncio.to_thread(parse_html, html_content)
            
            print(f"✅ Scraping successful for: {urlparse(url).netloc}")
            return parsed_data
            
        except Exception as e:
            print(f"❌ Scraping failed for {url}: {e}")
            return {"content": "", "quotes": [], "statistics": []}

    async def _get_duckduckgo_context(self, headline: str) -> str:
        """Original DuckDuckGo method - unchanged"""
        try:
            query = ' '.join(headline.split()[:3])
            ddg_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
            
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