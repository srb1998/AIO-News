# FILE: agents/script_writer.py

from core.llm_client import LLMClient
from core.token_manager import token_manager
from typing import Dict, Any, List
from datetime import datetime
import json
import re

class ScriptWriterAgent:
    def __init__(self):
        self.name = "script_writer"
        self.llm_client = LLMClient()
        self.templates = self._load_templates()

    def generate_multi_platform_scripts(self, investigation_reports: List[Dict[str, Any]], 
                                      max_stories: int = 3) -> Dict[str, Any]:
        """
        Generate scripts for all platforms from detective investigation reports
        Uses smart batching to minimize token usage
        """
        print(f"📝 Script Writer: Generating multi-platform scripts for {len(investigation_reports)} stories...")
        
        try:
            # Filter and prioritize stories
            priority_stories = self._prioritize_stories(investigation_reports, max_stories)
            
            if not priority_stories:
                return {
                    "success": False,
                    "error": "No priority stories found for script generation"
                }

            # Generate scripts using batched approach
            script_results = []
            total_tokens = 0
            total_cost = 0.0

            for story in priority_stories:
                print(f"📝 Generating scripts for: {story.get('original_headline', 'Unknown story')[:50]}...")
                
                # Generate all platform scripts in one LLM call
                script_result = self._generate_story_scripts(story)
                
                if script_result.get("success"):
                    script_results.append(script_result["scripts"])
                    
                    # Track token usage
                    tokens = script_result.get("token_usage", {}).get("tokens", 0)
                    cost = script_result.get("token_usage", {}).get("cost", 0)
                    total_tokens += tokens
                    total_cost += cost
                    
                    print(f"✅ Scripts generated ({tokens} tokens, ${cost:.4f})")
                else:
                    print(f"❌ Failed to generate scripts: {script_result.get('error')}")

            return {
                "success": True,
                "scripts_generated": len(script_results),
                "platform_scripts": script_results,
                "token_usage": {
                    "model": "gemini-2.0-flash",
                    "tokens": total_tokens,
                    "cost": total_cost
                },
                "ready_for_social_media_manager": len(script_results) > 0,
                "generation_timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Script generation failed: {str(e)}"
            }

    def _generate_story_scripts(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """Generate all platform scripts for a single story using one LLM call"""
        
        # Build comprehensive prompt for all platforms
        prompt = self._build_multi_platform_prompt(story)
        
        try:
            # Single LLM call for all platforms
            response = self.llm_client.smart_generate(prompt, max_tokens=5000, priority="normal")
            
            # if not response.get("success"):
            #     return {
            #         "success": False,
            #         "error": f"LLM generation failed: {response.get('error')}"
            #     }

            # Parse the JSON response
            content = response["content"]
            parsed_scripts = self._parse_json_response(content, story)
            
            return {
                "success": True,
                "scripts": parsed_scripts,
                "token_usage": response.get("token_usage", {})
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Script generation error: {str(e)}"
            }

    def _build_multi_platform_prompt(self, story: Dict[str, Any]) -> str:
        """Build comprehensive prompt for all platform scripts with JSON response format"""
        
        headline = story.get("original_headline", "Unknown Story")
        summary = story.get("research_summary", "")
        key_players = ", ".join(story.get("key_players", []))
        verified_facts = story.get("verified_facts", [])[:2]  # Limit to save tokens
        impact_analysis = story.get("impact_analysis", "")
        importance_score = story.get("importance_score", 0)
        visual_needs = story.get("visual_needs", [])
        
        # Determine Instagram slides count based on story complexity
        slides_count = self._determine_slides_count(importance_score, len(summary))
        
        return f"""
            You are a professional script writer for an AI news agency. Generate scripts for ALL platforms for this news story.

            STORY DETAILS:
            Headline: {headline}
            Summary: {summary}
            Key Players: {key_players}
            Impact: {impact_analysis}
            Verified Facts: {verified_facts}
            Importance Score: {importance_score}/10
            Available Visuals: {visual_needs}

            CRITICAL INSTRUCTIONS:
            - NEVER end any content with questions
            - Always provide definitive, factual statements
            - Use unbiased, professional journalism tone like palki sharma
            - Give to the point and clear news
            - Youtube dont use these keywords in the script OPENING_HOOK, CONTEXT_SETTING etc its just for reference
            - Instagram slides: Use {slides_count} slides based on story importance
            - Use provided visual needs for image suggestions

            Respond with VALID JSON in this exact format:

            {{
              "instagram": {{
                "slides_count": {slides_count},
                "carousel_slides": ["Provide Hook/Breaking news","Key facts/Context","Impact/Conclusion"],
                "story_content": "15-20 words Instagram story text - factual statement",
                "image_suggestions": [
                  "Specific image suggestion 1,2,3 based on visual needs",
                ],
                "estimated_engagement": "high/medium/low",
              }},
              "twitter": {{
                "tweet": "A single, structured, and highly engaging tweet summarizing the story, using a hook, key fact, and call to action.",
                "hashtags": ["3-5 relevant hashtags"],
                "image_suggestions": ["Specific image 1","Specific image 2"],
                "posting_priority": "immediate"
              }},
              "youtube": {{
                "full_script": "Provide OPENING_HOOK: [15-second attention grabber] + CONTEXT_SETTING: [30-second background] + CORE_ANALYSIS: [90-second detailed analysis] + IMPACT_ASSESSMENT: [30-second implications] + 
                    CLOSING: [15-second wrap-up with proper ending], Complete anchor script Include [pause], [serious], [emphasis], [slight smile] cues. Make valid script like journalist Palki Sharma style. and human-like simple tone.",
                "estimated_duration": "2-4 minutes",
                "image_suggestions": [
                  "B-roll footage suggestion 1",
                  "Graphics needed for explanation",
                  "Background visuals for key points"
                ],
                "anchor_personality": "professional_authoritative"
              }}
            }}

            Remember: Definitive conclusions and don't include any other news channel name.
            """

    def _determine_slides_count(self, importance_score: int, summary_length: int) -> int:
        """Determine number of Instagram slides based on story complexity"""
        if importance_score >= 9 or summary_length > 300:  # Breaking/Complex news
            return 3
        elif importance_score >= 7 or summary_length > 150:  # Important news
            return 2
        else:  # Regular news
            return 1

    def _parse_json_response(self, content: str, story: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON response from LLM into structured script format"""
        
        scripts = {
            "story_id": story.get("story_id", 0),
            "original_headline": story.get("original_headline", ""),
            "importance_score": story.get("importance_score", 0),
            "instagram": {},
            "twitter": {},
            "youtube": {},
            "metadata": {
                "generation_time": datetime.now().isoformat(),
                "source_story": story.get("source_url", ""),
                "category": story.get("category", "general")
            }
        }

        try:
            # Extract JSON from response (handle potential markdown formatting)
            json_content = self._extract_json_from_response(content)
            parsed_data = json.loads(json_content)
            
            # Process Instagram scripts
            if "instagram" in parsed_data:
                ig_data = parsed_data["instagram"]
                scripts["instagram"] = {
                    "slides_count": ig_data.get("slides_count", 2),
                    "carousel_slides": ig_data.get("carousel_slides", [])[:ig_data.get("slides_count", 2)],
                    "story_content": ig_data.get("story_content", ""),
                    "image_suggestions": self._merge_visual_suggestions(
                        story.get("visual_needs", []),
                        ig_data.get("image_suggestions", []),
                        "instagram"
                    ),
                    "estimated_engagement": ig_data.get("estimated_engagement", "medium")
                }

            # Process Twitter scripts
            if "twitter" in parsed_data:
                tw_data = parsed_data["twitter"]
                scripts["twitter"] = {
                    "tweet": tw_data.get("tweet", []),
                    "hashtags": tw_data.get("hashtags", []),
                    "image_suggestions": self._merge_visual_suggestions(
                        story.get("visual_needs", []),
                        tw_data.get("image_suggestions", []),
                        "twitter"
                    ),
                    "posting_priority": tw_data.get("posting_priority", "scheduled")
                }

            # Process YouTube scripts
            if "youtube" in parsed_data:
                yt_data = parsed_data["youtube"]
                scripts["youtube"] = {
                    "full_script": yt_data.get("full_script", ""),
                    "estimated_duration": yt_data.get("estimated_duration", "3-4 minutes"),
                    "image_suggestions": self._merge_visual_suggestions(
                        story.get("visual_needs", []),
                        yt_data.get("image_suggestions", []),
                        "youtube"
                    ),
                    "anchor_personality": yt_data.get("anchor_personality", "professional_authoritative"),
                    "teleprompter_ready": True
                }

            return scripts

        except json.JSONDecodeError as e:
            print(f"⚠️ JSON parsing error: {e}")
            # Fallback to basic structure
            # return self._create_fallback_scripts(story)
        except Exception as e:
            print(f"⚠️ Error parsing scripts: {e}")
            # return self._create_fallback_scripts(story)

    def _extract_json_from_response(self, content: str) -> str:
        """Extract JSON content from LLM response, handling markdown formatting"""
        # Remove markdown code blocks if present
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*$', '', content)
        
        # Find JSON object boundaries
        start_idx = content.find('{')
        end_idx = content.rfind('}') + 1
        
        if start_idx != -1 and end_idx != -1:
            return content[start_idx:end_idx]
        
        return content

    def _merge_visual_suggestions(self, detective_visuals: List[str], 
                                 llm_suggestions: List[str], 
                                 platform: str) -> List[str]:
        """Merge detective visual needs with LLM suggestions, prioritizing detective data"""
        merged = []
        
        # Always include detective visuals first (they're more specific)
        if detective_visuals:
            merged.extend(detective_visuals)
        
        # Add LLM suggestions that don't duplicate detective visuals
        for suggestion in llm_suggestions:
            if suggestion not in merged and len(merged) < 5:  # Limit to 5 suggestions
                merged.append(suggestion)
        
        # Platform-specific formatting
        if platform == "instagram":
            merged = [f"{item}" for item in merged]
        elif platform == "twitter":
            merged = [f"{item}" for item in merged]
        elif platform == "youtube":
            merged = [f"Video content: {item}" for item in merged]
        
        return merged[:3]  # Return max 3 suggestions per platform

    def _create_fallback_scripts(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """Create basic script structure if JSON parsing fails"""
        headline = story.get("original_headline", "")
        summary = story.get("research_summary", "")
        visual_needs = story.get("visual_needs", [])
        
        return {
            "story_id": story.get("story_id", 0),
            "original_headline": headline,
            "importance_score": story.get("importance_score", 0),
            "instagram": {
                "slides_count": 2,
                "carousel_slides": [
                    f"🚨 BREAKING: {headline[:50]}...",
                    f"Key Details: {summary[:100]}..."
                ],
                "story_content": f"Breaking: {headline[:50]}",
                "image_suggestions": visual_needs[:3] if visual_needs else ["Stock image needed"],
                "estimated_engagement": "medium"
            },
            "twitter": {
                "tweet": [
                    f"🚨 BREAKING: {headline}",
                    f"Key details: {summary[:200]}",
                    f"This story is developing..."
                ],
                "hashtags": ["#Breaking", "#News", "#Update"],
                "image_suggestions": visual_needs[:2] if visual_needs else ["News graphic needed"],
                "posting_priority": "immediate"
            },
            "youtube": {
                "full_script": f"Good evening. [pause] We're following a developing story. [seriously] {headline}. [pause] Here's what we know so far... {summary}",
                "estimated_duration": "2-3 minutes",
                "image_suggestions": visual_needs if visual_needs else ["B-roll footage needed"],
                "anchor_personality": "professional_authoritative",
                "teleprompter_ready": True
            },
            "metadata": {
                "generation_time": datetime.now().isoformat(),
                "source_story": story.get("source_url", ""),
                "category": story.get("category", "general"),
                "fallback_used": True
            }
        }

    def _prioritize_stories(self, reports: List[Dict[str, Any]], max_stories: int) -> List[Dict[str, Any]]:
        """Prioritize stories for script generation based on importance score"""
        # Sort by importance score descending
        sorted_reports = sorted(reports, key=lambda x: x.get("importance_score", 0), reverse=True)
        
        # Filter stories with minimum importance score
        priority_stories = [story for story in sorted_reports if story.get("importance_score", 0) >= 6]
        
        # Return top stories up to max limit
        return priority_stories[:max_stories]

    def _load_templates(self) -> Dict[str, str]:
        """Load script templates for different platforms"""
        return {
            "youtube_anchor_intro": "Good evening, I'm your AI news anchor with today's top stories.",
            "youtube_transition": "[pause] Now, here's what makes this story particularly significant...",
            "instagram_hook": "🚨 BREAKING: This just happened...",
            "twitter_breaking": "🔥 DEVELOPING:",
            "linkedin_opener": "Industry Analysis:",
            "emotional_cues": {
                "serious": "[seriously]",
                "pause": "[pause]",
                "excited": "[with excitement]",
                "concerned": "[concerned tone]",
                "confident": "[confidently]",
                "reflective": "[thoughtfully]"
            }
        }

    def generate_breaking_news_scripts(self, breaking_story: Dict[str, Any]) -> Dict[str, Any]:
        """Generate urgent scripts for breaking news (faster, simplified)"""
        print(f"🚨 Script Writer: Generating BREAKING NEWS scripts...")
        
        headline = breaking_story.get('original_headline', '')
        summary = breaking_story.get('research_summary', '')
        visual_needs = breaking_story.get('visual_needs', [])
        
        # Simplified prompt for speed
        prompt = f"""
            Generate URGENT breaking news scripts in JSON format:
            
            Story: {headline}
            Summary: {summary}
            
            {{
              "twitter_alert": "🚨 BREAKING: Factual statement about this news",
              "instagram_story": "Breaking news story text - 15 words max",  
              "youtube_alert": "Emergency news script for 30-second announcement",
              "image_suggestions": ["Urgent visual 1", "Breaking news graphic"]
            }}
            
            NO questions, only factual statements.
            """
        
        try:
            response = self.llm_client.generate_content(prompt)
            
            if response.get("success"):
                content = response["content"]
                json_content = self._extract_json_from_response(content)
                parsed_data = json.loads(json_content)
                
                return {
                    "success": True,
                    "breaking_scripts": {
                        "twitter_alert": parsed_data.get("twitter_alert", f"🚨 BREAKING: {headline}"),
                        "instagram_story": parsed_data.get("instagram_story", f"Breaking: {headline[:30]}"),
                        "youtube_alert": parsed_data.get("youtube_alert", f"Breaking news: {summary[:100]}"),
                        "image_suggestions": visual_needs + parsed_data.get("image_suggestions", []),
                        "priority": "immediate",
                        "story_id": breaking_story.get("story_id", 0)
                    },
                    "token_usage": response.get("token_usage", {})
                }
            else:
                return {"success": False, "error": "Breaking news script generation failed"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}