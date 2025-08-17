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
        self.brave_base_url = "https://api.search.brave.com/res/v1/web/search"
    
    @track_tokens("Detective")
    async def investigate_top_stories(self, top_headlines: List[Dict[str, Any]], max_stories: int = 5) -> Dict[str, Any]:
        """
         Main investigation method with Brave AI grounding
        """
        print(f"🕵️ Detective Agent: Starting  investigation of {len(top_headlines)} stories...")
        
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

        #  Step 1: Extract content + Brave AI grounding (FREE + PAID)
        tasks = [self._enhanced_extract_content(story) for story in stories_to_investigate]
        enhanced_research_data = await asyncio.gather(*tasks)
        
        #  Step 2: Deep analysis with comprehensive data
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
            "enhanced_data_sources": "brave_ai_grounding_enabled"
        }
    
    async def _enhanced_extract_content(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract content with Brave AI grounding for comprehensive data
        """
        cache_key = f"enhanced_detective_{hash(story.get('headline', ''))}"
        cached_content = cache_manager.get(cache_key, expire_hours=12)
        
        if cached_content:
            print("📋 Using cached enhanced content...")
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
            "related_info": "",
            "verified_facts": [],
            "recent_developments": [],
            "expert_opinions": [],
            "background_context": "",
            "similar_incidents": [],
            "official_statements": [],
            "data_sources_count": 0
        }
        
        # Original extraction +  Brave AI grounding
        source_url = story.get("url") or story.get("source_url")
        
        # Run all data gathering concurrently
        tasks = []
        
        if source_url:
            tasks.append(self._scrape_article_content(source_url))
        else:
            tasks.append(self._empty_scrape_result())
            
        #  Multiple Brave searches for comprehensive coverage
        tasks.extend([
            self._brave_ai_grounding(story["headline"], "facts"),
            self._brave_ai_grounding(story["headline"], "recent"),
            self._brave_ai_grounding(story["headline"], "background"),
            self._get_duckduckgo_context(story["headline"])
        ])
        
        results = await asyncio.gather(*tasks)
        
        # Process results
        scraped_data = results[0]
        brave_facts = results[1]
        brave_recent = results[2] 
        brave_background = results[3]
        ddg_context = results[4]
        
        # Merge all data
        content_data.update(scraped_data)
        content_data["related_info"] = ddg_context
        
        #  Process Brave AI data
        content_data["verified_facts"] = brave_facts.get("facts", [])
        content_data["recent_developments"] = brave_recent.get("developments", [])
        content_data["background_context"] = brave_background.get("context", "")
        content_data["expert_opinions"] = brave_facts.get("expert_views", [])
        content_data["official_statements"] = brave_facts.get("official_statements", [])
        content_data["data_sources_count"] = len([r for r in results[1:4] if r.get("success")])
        
        # Cache the enhanced result
        cache_manager.set(cache_key, content_data, expire_hours=12)
        
        print(f"✅ Enhanced extraction: {content_data['data_sources_count']}/3 Brave sources + original")
        return content_data

    async def _brave_ai_grounding(self, headline: str, search_type: str) -> Dict[str, Any]:
        """
        NEW: Use Brave Search API for AI grounding with specific search strategies
        """
        try:
            # Create targeted search queries based on type
            if search_type == "facts":
                query = f'"{headline}" facts statistics data numbers'
            elif search_type == "recent":
                query = f'"{headline}" latest news today updates developments'
            elif search_type == "background":
                query = f'"{headline}" background context history explanation'
            else:
                query = headline
            
            print(f"🔍 Brave AI grounding ({search_type}): {query[:50]}...")
            
            params = {
                'q': query,
                'count': 10,
                'search_lang': 'en',
                'safesearch': 'off',
                'freshness': 'pd' if search_type == "recent" else 'pw',  # Past day for recent, past week for others
                'text_decorations': False
            }
            
            headers = {
                'X-Subscription-Token': self.brave_api_key,
                'Accept': 'application/json'
            }
            
            response = await self.session.get(self.brave_base_url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            results = data.get('results', [])
            
            # Process results based on search type
            processed_data = await self._process_brave_results(results, search_type)
            processed_data["success"] = True
            
            print(f"✅ Brave AI ({search_type}): Found {len(processed_data.get('facts') or processed_data.get('developments') or processed_data.get('context', []))} items")
            
            await asyncio.sleep(1.5)
        
            return processed_data
            
        except Exception as e:
            print(f"❌ Brave AI grounding ({search_type}) failed: {e}")
            return {"success": False, "error": str(e)}

    async def _process_brave_results(self, results: List[Dict], search_type: str) -> Dict[str, Any]:
        """
        NEW: Process Brave search results based on search type
        """
        processed = {
            "facts": [],
            "developments": [],
            "context": "",
            "expert_views": [],
            "official_statements": []
        }
        
        for result in results[:8]:  # Process top 8 results
            title = result.get('title', '')
            description = result.get('description', '')
            url = result.get('url', '')
            combined_text = f"{title} {description}"
            
            if search_type == "facts":
                # Extract factual information, statistics, numbers
                facts = self._extract_facts_from_text(combined_text)
                processed["facts"].extend(facts)
                
                # Identify expert opinions and official statements
                if any(keyword in combined_text.lower() for keyword in ['expert', 'analyst', 'professor', 'researcher']):
                    processed["expert_views"].append(f"{title}: {description[:150]}")
                
                if any(keyword in combined_text.lower() for keyword in ['official', 'government', 'ministry', 'spokesperson']):
                    processed["official_statements"].append(f"{title}: {description[:150]}")
                    
            elif search_type == "recent":
                # Extract recent developments and updates
                developments = self._extract_developments_from_text(combined_text)
                processed["developments"].extend(developments)
                
            elif search_type == "background":
                # Build comprehensive background context
                if description and len(description) > 50:
                    processed["context"] += f" {description}"
        
        # Clean and limit results
        processed["facts"] = list(set(processed["facts"]))[:8]
        processed["developments"] = list(set(processed["developments"]))[:6]
        processed["context"] = processed["context"][:800]
        processed["expert_views"] = processed["expert_views"][:4]
        processed["official_statements"] = processed["official_statements"][:3]
        
        return processed

    def _extract_facts_from_text(self, text: str) -> List[str]:
        """Extract factual statements with numbers, percentages, dates, etc."""
        facts = []
        
        # Extract sentences with numbers/percentages
        number_pattern = r'[^.!?]*\b\d+(?:\.\d+)?(?:%|billion|million|thousand|crore|lakh)?\b[^.!?]*[.!?]'
        number_sentences = re.findall(number_pattern, text, re.IGNORECASE)
        facts.extend([s.strip() for s in number_sentences if len(s.strip()) > 20])
        
        # Extract sentences with specific fact indicators
        fact_indicators = ['according to', 'reported that', 'confirmed that', 'announced that', 'revealed that']
        for indicator in fact_indicators:
            pattern = f'[^.!?]*{re.escape(indicator)}[^.!?]*[.!?]'
            fact_sentences = re.findall(pattern, text, re.IGNORECASE)
            facts.extend([s.strip() for s in fact_sentences if len(s.strip()) > 30])
        
        return facts[:6]  # Return top 6 facts

    def _extract_developments_from_text(self, text: str) -> List[str]:
        """Extract recent developments and updates"""
        developments = []
        
        # Extract sentences with time indicators
        time_indicators = ['today', 'yesterday', 'this morning', 'earlier', 'just announced', 'breaking', 'latest']
        for indicator in time_indicators:
            pattern = f'[^.!?]*{re.escape(indicator)}[^.!?]*[.!?]'
            dev_sentences = re.findall(pattern, text, re.IGNORECASE)
            developments.extend([s.strip() for s in dev_sentences if len(s.strip()) > 25])
        
        return developments[:5]  # Return top 5 developments

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