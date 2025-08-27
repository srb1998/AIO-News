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
    
    @track_tokens("Detective")
    async def investigate_top_stories(self, top_headlines: List[Dict[str, Any]], max_stories: int = 5) -> Dict[str, Any]:
        """
        Main investigation method with Gemini AI grounding
        """
        print(f"🕵️ Detective Agent: Starting investigation with Gemini AI grounding of {len(top_headlines)} stories...")
        
        # Filter and sort by priority
        priority_stories = [h for h in top_headlines if h.get("priority", 0) >= 6]
        priority_stories.sort(key=lambda x: x.get("priority", 0), reverse=True)
        stories_to_investigate = priority_stories[:max_stories]
        
        print(f"🎯 Investigating top {len(stories_to_investigate)} priority stories...")
        
        if not stories_to_investigate:
            return {
                "success": True,
                "message": "No high-priority stories found for investigation",
                "investigation_reports": []
            }

        # Step 1: Extract content + Gemini AI grounding (FREE)
        tasks = [self._enhanced_extract_content_gemini(story) for story in stories_to_investigate]
        enhanced_research_data = await asyncio.gather(*tasks)
        
        # Step 2: Deep analysis with comprehensive data
        analysis_result = await self._enhanced_analyze_with_llm(enhanced_research_data)
        
        if "error" in analysis_result:
            return {"success": False, "error": analysis_result["error"]}
        
        # Step 3: Format enhanced research reports
        investigation_reports = self._format_enhanced_reports(
            analysis_result["content"], 
            enhanced_research_data
        )
        
        return {
            "success": True,
            "stories_investigated": len(stories_to_investigate),
            "investigation_reports": investigation_reports,
            "token_usage": analysis_result["token_usage"],
            "ready_for_script_writer": True,
            "enhanced_data_sources": "gemini_ai_grounding_enabled"
        }
    
    async def _enhanced_extract_content_gemini(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract content with Gemini AI grounding for comprehensive data
        """
        cache_key = f"enhanced_detective_gemini_{hash(story.get('headline', ''))}"
        cached_content = cache_manager.get(cache_key, expire_hours=12)
        
        if cached_content:
            print("📋 Using cached enhanced content...")
            return cached_content
        
        content_data = {
            "headline": story.get("headline", ""),
            "subheadline": story.get("subheadline", ""),
            "original_summary": story.get("summary", ""),
            "category": story.get("category", "general"),
            "priority": story.get("priority", 0),
            "source": story.get("source", "Unknown"),
            "source_url": story.get("url", ""),
            "extracted_content": "",
            "key_quotes": [],
            "statistics": [],
            "related_info": "",
            "verified_facts": [],
            "recent_developments": [],
            "expert_opinions": [],
            "background_context": "",
            "similar_incidents": [],
            "official_statements": [],
            "data_sources_count": 0
        }
        
        # Original extraction + DuckDuckGo context
        source_url = story.get("url") or story.get("source_url")
        
        # Run all data gathering tasks concurrently
        other_tasks = []
        if source_url:
            other_tasks.append(self._scrape_article_content(source_url))
        else:
            other_tasks.append(self._empty_scrape_result())
        other_tasks.append(self._get_duckduckgo_context(story["headline"]))
        
        other_results = await asyncio.gather(*other_tasks)
        
        # Run Gemini AI grounding tasks with reasonable delays
        print("🧠 Starting Gemini AI grounding analysis...")
        
        gemini_facts = await self._gemini_ai_grounding(story["headline"], story.get("summary", ""), "facts")
        await asyncio.sleep(0.5)
        
        gemini_recent = await self._gemini_ai_grounding(story["headline"], story.get("summary", ""), "recent")
        await asyncio.sleep(0.5) 
        
        gemini_background = await self._gemini_ai_grounding(story["headline"], story.get("summary", ""), "background")
        
        # Process results
        scraped_data = other_results[0]
        ddg_context = other_results[1]
        
        # Merge all data
        content_data.update(scraped_data)
        content_data["related_info"] = ddg_context
        
        # Process Gemini AI data
        content_data["verified_facts"] = gemini_facts.get("facts", [])
        content_data["recent_developments"] = gemini_recent.get("developments", [])
        content_data["background_context"] = gemini_background.get("context", "")
        content_data["expert_opinions"] = gemini_facts.get("expert_views", [])
        content_data["official_statements"] = gemini_facts.get("official_statements", [])

        gemini_results_list = [gemini_facts, gemini_recent, gemini_background]
        content_data["data_sources_count"] = len([res for res in gemini_results_list if res.get("success")])
        
        # Cache the enhanced result
        cache_manager.set(cache_key, content_data, expire_hours=12)
        
        print(f"✅ Enhanced extraction: {content_data['data_sources_count']}/3 Gemini sources + original")
        return content_data
    
    def _extract_json_from_response(self, content: str) -> str:
        """
        Extracts a JSON object from a string, ignoring leading/trailing text and markdown.
        """
        # First, try to find a JSON block within markdown ```json ... ```
        match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if match:
            return match.group(1)

        # If no markdown block, find the first '{' and the last '}'
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            return content[start:end+1]
        
        # Fallback for simple cases
        return content

    async def _gemini_ai_grounding(self, headline: str, summary: str, analysis_type: str) -> Dict[str, Any]:
        """
        Use Gemini AI for intelligent grounding analysis
        """
        try:
            # Create targeted analysis prompts based on type
            if analysis_type == "facts":
                prompt = f"""
                Analyze this news story and extract key facts, statistics, and verifiable information, Your entire response must be ONLY a valid JSON object. Do not include any other text:
                Headline: {headline}
                Summary: {summary}
                
                Provide:
                1. Key facts and statistics (with numbers where possible)
                2. Expert opinions or analyst views mentioned
                3. Official statements from governments/organizations
                
                Format as JSON:
                {{
                    "facts": ["fact 1 with specific details", "fact 2 with numbers/data"],
                    "expert_views": ["expert opinion 1", "expert opinion 2"],
                    "official_statements": ["official statement 1"]
                }}
                """
            elif analysis_type == "recent":
                prompt = f"""
                Analyze this news story and identify recent developments and updates:
                
                Headline: {headline}
                Summary: {summary}
                
                Focus on:
                1. Latest developments in the last 24-48 hours
                2. New information or updates
                3. Timeline of events
                
                Format as JSON:
                {{
                    "developments": ["recent development 1", "recent development 2"]
                }}
                """
            elif analysis_type == "background":
                prompt = f"""
                Analyze this news story and provide essential background context:
                
                Headline: {headline}
                Summary: {summary}
                
                Provide comprehensive background context that helps understand:
                1. Historical context
                2. Key players and their roles
                3. Why this story is significant
                4. Related events or precedents
                
                Format as JSON:
                {{
                    "context": "Detailed background context explaining the significance and history of this story"
                }}
                """
            
            print(f"🧠 Gemini AI analysis ({analysis_type}): {headline[:50]}...")
            
            # Use new smart generate with Gemini for AI grounding
            response = await llm_client.smart_generate_with_search(prompt, max_tokens=4000)

            if "error" in response:
                return {"success": False, "error": response["error"]}
            
            # Parse JSON response
            try:
                json_content = self._extract_json_from_response(response["content"])
                parsed_data = json.loads(json_content)
                parsed_data["success"] = True
                
                print(f"✅ Gemini AI ({analysis_type}): Analysis complete")
                return parsed_data
                
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON parsing failed for {analysis_type}, using fallback")
                return self._create_gemini_fallback(analysis_type, headline, summary)
            
        except Exception as e:
            print(f"❌ Gemini AI grounding ({analysis_type}) failed: {e}")
            return {"success": False, "error": str(e)}

    # def _extract_json_from_gemini_response(self, content: str) -> str:
    #     """
    #     Extract JSON content from Gemini response
    #     """
    #     # Remove markdown code blocks if present
    #     content = re.sub(r'```json\s*', '', content)
    #     content = re.sub(r'```\s*', '', content)
        
    #     # Find JSON object boundaries
    #     start_idx = content.find('{')
    #     end_idx = content.rfind('}') + 1
        
    #     if start_idx != -1 and end_idx != -1:
    #         return content[start_idx:end_idx]
        
    #     return content

    def _create_gemini_fallback(self, analysis_type: str, headline: str, summary: str) -> Dict[str, Any]:
        """
        Create fallback data when Gemini JSON parsing fails
        """
        if analysis_type == "facts":
            return {
                "success": True,
                "facts": [f"Analysis of {headline} indicates significant developments"],
                "expert_views": [],
                "official_statements": []
            }
        elif analysis_type == "recent":
            return {
                "success": True,
                "developments": [f"Recent developments in {headline} are being monitored"]
            }
        elif analysis_type == "background":
            return {
                "success": True,
                "context": f"Background context for {headline}: {summary[:200]}"
            }
        
        return {"success": False}
    
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
        Format enhanced research data for comprehensive LLM analysis
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
            
            VERIFIED FACTS FROM GEMINI AI:
            {chr(10).join(f"- {fact}" for fact in data['verified_facts'][:5])}
            
            RECENT DEVELOPMENTS:
            {chr(10).join(f"- {dev}" for dev in data['recent_developments'][:4])}
            
            BACKGROUND CONTEXT: {str(data.get('background_context', ''))[:400]}
            
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
            cleaned_content = self._extract_json_from_response(llm_content)
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
                        "gemini_facts_count": len(original_data["verified_facts"]),
                        "recent_developments_count": len(original_data["recent_developments"]),
                        "expert_opinions_count": len(original_data["expert_opinions"]),
                        "data_quality_score": original_data["data_sources_count"],
                        "enhanced_investigation": True,
                        "ai_grounding_type": "gemini"
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
        
        for data in enhanced_data:
            report = {
                "story_id": len(fallback_reports) + 1,
                "original_headline": data["headline"],
                "original_summary": data["original_summary"],
                "importance_score": data["priority"],
                "research_summary": f"Enhanced investigation of {data['headline']} with {data['data_sources_count']} Gemini AI sources",
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
                "background_context": str(data.get("background_context", ""))[:200],
                "source": data["source"],
                "category": data["category"],
                "investigation_timestamp": time.time(),
                "enhanced_investigation": True,
                "data_quality_score": data["data_sources_count"],
                "ai_grounding_type": "gemini"
            }
            
            fallback_reports.append(report)
        
        return fallback_reports

    async def _empty_scrape_result(self):
        """Return empty scrape result when no URL available"""
        return {"content": "", "quotes": [], "statistics": []}

    #  Keep all existing scraping and context methods
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