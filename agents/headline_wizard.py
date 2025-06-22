# File: agents/headline_wizard.py
from core.token_manager import track_tokens, token_manager
from core.llm_client import llm_client
from typing import List, Dict, Any, Union
import json
import re

class HeadlineWizardAgent:
    def __init__(self):
        self.name = "HeadlineWizard"
    
    @track_tokens("HeadlineWizard")
    def create_headlines(self, news_hunter_output: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw news into clean, engaging headlines"""
        print("✏️ Headline Wizard: Crafting engaging headlines...")
        
        # Extract articles from News Hunter output
        try:
            raw_articles = self._extract_articles(news_hunter_output)
            print(f"📄 Extracted {len(raw_articles)} articles from News Hunter output")
        except Exception as e:
            print(f"⚠️ Error extracting articles: {e}")
            return {"error": "Failed to extract articles", "headlines": []}

        if not raw_articles:
            return {"error": "No articles to process", "headlines": []}
        
        print(f"📝 Processing {len(raw_articles)} articles for headlines")
        
        # Create headlines with LLM (token-efficient)
        result = self._process_headlines_with_llm(raw_articles)
        print(f"result from LLM : {result}")
        content_result = result.get("content", "")
        clean_result = re.sub(r"^```json|```$", "", content_result.strip()).strip()
        if "error" in result:
            return result
        
        # Post-process and validate
        clean_headlines = self._clean_and_validate_headlines(clean_result)

        return {
            "success": True,
            "input_articles": len(raw_articles),
            "output_headlines": len(clean_headlines),
            "headlines": clean_headlines,
            "token_usage": result["token_usage"],
            "top_priorities": [h for h in clean_headlines if h.get("priority", 0) >= 8]
        }
    
    def _extract_articles(self, news_hunter_output: Dict) -> List[Dict]:
        """Extract articles from News Hunter output (handles both formats)"""
        articles = []
        
        # Handle successful News Hunter output
        if news_hunter_output.get("success") and "processed_articles" in news_hunter_output:
            print("inside news_hunter_output if condition")
            try:
                processed = news_hunter_output["processed_articles"]
                cleaned_processed = re.sub(r"^```json|```$", "", processed.strip()).strip()
                print("cleaned processed data :", cleaned_processed)
            except Exception as e:
                print(f"⚠️ Error extracting processed articles: {e}")
                return []

            # Handle JSON string or dict
            if isinstance(cleaned_processed, str):
                try:
                    cleaned_processed = json.loads(cleaned_processed)
                except json.JSONDecodeError:
                    print("⚠️ Failed to parse News Hunter JSON, using raw text")
                    return []
            
            # Extract articles from LLM response
            if isinstance(cleaned_processed, dict):
                articles.extend(cleaned_processed.get("top_headlines", []))
                articles.extend(cleaned_processed.get("breaking_news", []))
        print("articles extracted from news hunter output :", articles)
        return articles[:15]  # Limit to save tokens
    
    @track_tokens("HeadlineWizard-LLM")
    def _process_headlines_with_llm(self, articles: List[Dict]) -> Dict[str, Any]:
        """Process headlines using LLM - TOKEN EFFICIENT"""
        
        # Create compact prompt
        # articles_summary = self._create_compact_summary(articles)
        
        prompt = f"""Transform these {len(articles)} news articles into Clickbaiting headlines.

            {articles}

            Return JSON only:
            {{
                "headlines": [
                    {{
                        "headline": "Engaging clickbaiting humourous 8-12 word headline",
                        "summary": "One-two sentence humourous summary",
                        "category": "tech/business/world/india",
                        "priority": 9,
                        "source": "source name",
                        "urgency": "high/medium/low"
                    }}
                ]
            }}

            Rules:
            - Headlines must grab attention but stay factual
            - Priority 1-10 (10 = most important)
            - One sentence summaries only
            - Focus on impact/significance
            - Remove duplicates"""

        return llm_client.smart_generate(prompt, max_tokens=2000, priority="normal")
    
    def _create_compact_summary(self, articles: List[Dict]) -> str:
        """Create token-efficient article summary"""
        compact = []
        
        for i, article in enumerate(articles, 1):
            # Extract key info only
            title = article.get("title", "")[:100]  # Limit title length
            summary = article.get("summary", article.get("description", ""))[:150]
            category = article.get("category", "general")
            source = article.get("source", "unknown")
            
            compact.append(f"{i}. {title} | {category} | {source}\n   {summary}")

        print(f"Compact : {compact}")
        return "\n\n".join(compact)
    
    def _clean_and_validate_headlines(self, llm_response: str) -> List[Dict]:
        """Clean and validate LLM response"""
        try:
            # Parse JSON response
            if isinstance(llm_response, str):
                data = json.loads(llm_response)
            else:
                data = llm_response
            
            headlines = data.get("headlines", [])
            
            # Validate and clean each headline
            clean_headlines = []
            for headline in headlines:
                if self._is_valid_headline(headline):
                    clean_headline = self._standardize_headline(headline)
                    clean_headlines.append(clean_headline)
            
            # Sort by priority (highest first)
            clean_headlines.sort(key=lambda x: x.get("priority", 0), reverse=True)
            
            return clean_headlines[:10]  # Top 10 headlines
            
        except json.JSONDecodeError:
            print("⚠️ Failed to parse headlines JSON")
            return []
    
    def _is_valid_headline(self, headline: Dict) -> bool:
        """Validate headline structure"""
        required_fields = ["headline", "summary", "category", "priority"]
        return all(field in headline and headline[field] for field in required_fields)
    
    def _standardize_headline(self, headline: Dict) -> Dict:
        """Standardize headline format"""
        return {
            "headline": headline.get("headline", "").strip(),
            "summary": headline.get("summary", "").strip(),
            "category": headline.get("category", "general").lower(),
            "priority": min(10, max(1, int(headline.get("priority", 5)))),
            "source": headline.get("source", "unknown"),
            "urgency": headline.get("urgency", "medium").lower(),
            "created_at": "2025-06-21"  # Add timestamp
        }