# script_writer.py 

import asyncio
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

    async def generate_multi_platform_scripts(self, investigation_reports: List[Dict[str, Any]], 
                                      max_stories: int = 5) -> Dict[str, Any]:
        """
        Generate scripts using comprehensive investigation data
        """
        print(f"📝 Enhanced Script Writer: Generating multi-platform scripts for {len(investigation_reports)} stories...")
        
        try:
            # Filter and prioritize stories
            priority_stories = self._prioritize_stories(investigation_reports, max_stories)
            
            if not priority_stories:
                return {
                    "success": False,
                    "error": "No priority stories found for script generation"
                }

            # Process stories with rich data
            tasks = [self._generate_enhanced_story_scripts(story) for story in priority_stories]
            results = await asyncio.gather(*tasks)

            # Process results
            script_results = []
            total_tokens = 0
            total_cost = 0.0

            for result in results:
                if result.get("success"):
                    script_results.append(result["scripts"])
                    tokens = result.get("token_usage", {}).get("tokens", 0)
                    cost = result.get("token_usage", {}).get("cost", 0)
                    total_tokens += tokens
                    total_cost += cost
                else:
                    print(f"❌ Enhanced script generation task failed: {result.get('error')}")

            return {
                "success": True,
                "scripts_generated": len(script_results),
                "platform_scripts": script_results,
                "token_usage": {
                    "model": "mixed",
                    "tokens": total_tokens,
                    "cost": total_cost
                },
                "enhancement_level": "comprehensive_data_integration"
            }
        except Exception as e:
            return {"success": False, "error": f"Enhanced script generation failed: {str(e)}"}

    async def _generate_enhanced_story_scripts(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate scripts using comprehensive investigation data
        """
        
        # Build enhanced prompt with ALL available data
        prompt = self._build_multi_platform_prompt(story)
        
        try:
            # Use enhanced generation with more tokens for detailed content
            response = await self.llm_client.smart_generate(prompt, max_tokens=8000, priority="normal")
            
            # Parse the comprehensive response
            content = response["content"]
            parsed_scripts = self._parse_json_response(content, story)
            
            return {
                "success": True,
                "scripts": parsed_scripts,
                "token_usage": response.get("token_usage", {}),
                "data_richness": "enhanced"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Enhanced script generation error: {str(e)}"
            }

    def _build_multi_platform_prompt(self, story: Dict[str, Any]) -> str:
        """
        Build comprehensive prompt with ALL investigation data
        """
        
        headline = story.get("original_headline", "Unknown Story")
        summary = story.get("research_summary", "")
        importance_score = story.get("importance_score", 0)
        
        # Extract enhanced investigation data
        verified_facts = story.get("verified_facts", [])
        recent_developments = story.get("recent_developments", [])
        expert_insights = story.get("expert_insights", [])
        official_positions = story.get("official_positions", [])
        background_context = story.get("background_context", "")
        indian_perspective = story.get("indian_perspective", "")
        impact_analysis = story.get("impact_analysis", "")
        key_players = story.get("key_players", [])
        
        # Create rich context string
        enhanced_context = f"""
        VERIFIED FACTS: {' | '.join(verified_facts[:4])}
        RECENT DEVELOPMENTS: {' | '.join(recent_developments[:3])}
        EXPERT INSIGHTS: {' | '.join(expert_insights[:2])}
        OFFICIAL POSITIONS: {' | '.join(official_positions[:2])}
        BACKGROUND: {background_context[:300]}
        INDIAN PERSPECTIVE: {indian_perspective}
        IMPACT: {impact_analysis[:200]}
        KEY PLAYERS: {', '.join(key_players[:3])}
        """
        
        return f"""
            You are Palki Sharma, a renowned Indian journalist known for sharp, opinionated, and well-researched news presentation. 
            Generate scripts for ALL platforms using this COMPREHENSIVE investigation data.

            STORY HEADLINE: {headline}
            IMPORTANCE SCORE: {importance_score}/10

            COMPREHENSIVE INVESTIGATION DATA:
            {enhanced_context}

            CRITICAL SCRIPT REQUIREMENTS:
            
            FOR ALL PLATFORMS:
            - Use SPECIFIC facts and numbers from the investigation data above
            - Include recent developments and expert opinions where relevant
            - NO generic statements - everything must be specific and factual
            - current global context (Trump is current us president, current year 2025)
            - Show clear opinion and analysis, not just reporting
            - Use conversational, engaging tone like Palki Sharma
            - Don't use Palki Sharma's name on any script

            FOR YOUTUBE SPECIFICALLY:
            - Create a 2-3 minute anchor-style script
            - Structure: Hook → Context → Analysis → Indian Angle → Impact → Conclusion
            - Include specific timestamps and pacing
            - Add natural pauses and emphasis points
            - Include specific data points and expert quotes
            - End with strong opinion/takeaway
            - Remember: If news is not very important make max of 2 mins script. And if news is important and impactful then make upto 4 mins of script

            FOR INSTAGRAM:
            - Create engaging story content that works as standalone post
            - Use specific facts to make it informative
            - Include clear takeaway message
            
            FOR TWITTER:
            - Create content with specific information
            - Include key statistics or quotes
            - Make it shareable with clear hook

            Respond with VALID JSON in this exact format:

            {{
              "instagram": {{
                "story_content": "Write a detailed, informative caption using specific facts from the investigation. Begin with a strong, attention-grabbing first line that makes people want to read more. Include expert opinions or official statements. End with a definitive conclusion, not questions.",
                "estimated_engagement": "high/medium/low",
                "hashtags": ["#FactCheck", "#IndianPerspective", "#GlobalNews", "relevant topic hashtags"],
                "content_style": "informative_conversational"
              }},
              "twitter": {{
                "tweet": "Write a concise, update-style news tweet. Start with a strong hook, include one key fact or number, and end with a clear, definitive conclusion. Do not create a thread or provide a detailed breakdown. No questions - make definitive statements.",
                "hashtags": ["#NewsUpdate", "#IndiaFirst", "#FactsMatter", "relevant hashtags"],
                "image_suggestions": ["Specific infographic showing key statistics", "Photo of main subject/location"],
                "posting_priority": "immediate/scheduled",
              }},
              "youtube": {{
                "full_script": "CREATE COMPLETE 2-3 MINUTE SCRIPT with as per below hook,context etc but dont include [HOOK - 15 seconds],[CONTEXT - 30 seconds] etc keyword in the script:
                
                [HOOK - 15 seconds]: Start with attention-grabbing statement using specific fact or recent development
                
                [CONTEXT - 30 seconds]: Provide essential background using investigation data, mention key players
                
                [ANALYSIS - 90 seconds]: Deep dive into verified facts, expert opinions, official positions. Include specific numbers, quotes, developments
                
                [INDIAN PERSPECTIVE - 30 seconds]: How this affects India, Indian interests, our stance vs others
                
                [GLOBAL IMPACT - 30 seconds]: Broader implications using impact analysis data
                
                [CONCLUSION - 15 seconds]: Strong opinion-based ending with clear takeaway
                
                WRITE ACTUAL SCRIPT CONTENT - not just structure descriptions. Use natural speaking rhythm with pauses marked as [PAUSE]. Include emphasis points [EMPHASIS]. Make it sound like Palki Sharma's style - confident, opinionated, fact-based.",
                
                "estimated_duration": "2-4 minutes",
                "image_suggestions": [
                  "B-roll: Specific relevant footage based on story",
                  "Graphics: Key statistics from verified facts",
                  "Maps/Charts: Visual representation of impact data",
                  "Photos: Key players mentioned in investigation"
                ],
                "anchor_personality": "confident_opinionated_palki_style",
                "teleprompter_ready": true,
                "pacing_notes": "Include natural pauses, fast, emphasis points, and conversational flow"
              }}
            }}

            REMEMBER: 
            - Use SPECIFIC information from the comprehensive investigation data
            - No generic news speak - make it conversational and opinionated
            - Reference actual facts, numbers, expert opinions from the data provided
            - End with conclusions, not questions
            - Make it sound authoritative but approachable like Palki Sharma
            - Remember to keep the language simple and clear, avoiding jargon
            """

    def _parse_json_response(self, content: str, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse JSON response with better error handling and data integration
        """
        
        scripts = {
            "story_id": story.get("story_id", 0),
            "original_headline": story.get("original_headline", ""),
            "subheadline": story.get("subheadline", ""),
            "importance_score": story.get("importance_score", 0),
            "instagram": {},
            "twitter": {},
            "youtube": {},
            "metadata": {
                "generation_time": datetime.now().isoformat(),
                "source_story": story.get("source_url", ""),
                "category": story.get("category", "general"),
                "enhanced_data_used": True,
                "investigation_quality": story.get("data_quality_score", 0),
                "facts_integrated": len(story.get("verified_facts", [])),
                "expert_opinions_used": len(story.get("expert_insights", []))
            }
        }

        try:
            # Extract and parse JSON
            json_content = self._extract_json_from_response(content)
            parsed_data = json.loads(json_content)
            
            # Process Instagram with enhanced data
            if "instagram" in parsed_data:
                ig_data = parsed_data["instagram"]
                scripts["instagram"] = {
                    "insta_headline": story.get("original_headline", ""),
                    "story_content": ig_data.get("story_content", ""),
                    "hashtags": ig_data.get("hashtags", []),
                    "estimated_engagement": ig_data.get("estimated_engagement", "medium"),
                    "content_style": ig_data.get("content_style", "informative"),
                    "key_facts_used": story.get("verified_facts", [])[:2],
                    "indian_angle": story.get("indian_perspective", "")[:100]
                }

            # Process Twitter with enhanced data
            if "twitter" in parsed_data:
                tw_data = parsed_data["twitter"]
                scripts["twitter"] = {
                    "tweet": tw_data.get("tweet", ""),
                    "hashtags": tw_data.get("hashtags", []),
                    "image_suggestions": self._merge_enhanced_visual_suggestions(
                        story.get("visual_needs", []),
                        tw_data.get("image_suggestions", []),
                        "twitter",
                        story.get("verified_facts", [])
                    ),
                    "posting_priority": tw_data.get("posting_priority", "scheduled"),
                    "facts_to_highlight": story.get("verified_facts", [])[:3],
                    "expert_backing": story.get("expert_insights", [])[:1]
                }

            # Process YouTube with comprehensive data
            if "youtube" in parsed_data:
                yt_data = parsed_data["youtube"]
                scripts["youtube"] = {
                    "full_script": yt_data.get("full_script", ""),
                    "estimated_duration": yt_data.get("estimated_duration", "3-4 minutes"),
                    "image_suggestions": self._merge_enhanced_visual_suggestions(
                        story.get("visual_needs", []),
                        yt_data.get("image_suggestions", []),
                        "youtube",
                        story.get("verified_facts", [])
                    ),
                    "anchor_personality": yt_data.get("anchor_personality", "confident_opinionated"),
                    "teleprompter_ready": True,
                    "pacing_notes": yt_data.get("pacing_notes", ""),
                    # Rich contextual data
                    "background_context": story.get("background_context", "")[:200],
                    "key_players_mentioned": story.get("key_players", []),
                    "recent_developments": story.get("recent_developments", [])[:2]
                }

            return scripts

        except json.JSONDecodeError as e:
            print(f"⚠️JSON parsing error: {e}")
            return self._create_enhanced_fallback_scripts(story)
        except Exception as e:
            print(f"⚠️ Error parsing scripts: {e}")
            return self._create_enhanced_fallback_scripts(story)

    def _merge_enhanced_visual_suggestions(self, detective_visuals: List[str], 
                                         llm_suggestions: List[str], 
                                         platform: str,
                                         verified_facts: List[str]) -> List[str]:
        """
        Merge visual suggestions with fact-based requirements
        """
        merged = []
        
        # Start with detective visuals (most specific)
        if detective_visuals:
            merged.extend(detective_visuals)
        
        # Add LLM suggestions
        for suggestion in llm_suggestions:
            if suggestion not in merged and len(merged) < 4:
                merged.append(suggestion)
        
        # Add fact-based visual suggestions
        for fact in verified_facts[:2]:
            if any(keyword in fact.lower() for keyword in ['%', 'million', 'billion', 'increase', 'decrease']):
                merged.append(f"Infographic showing: {fact[:50]}")
                break
        
        # Platform-specific enhancements
        if platform == "youtube":
            merged.append("Lower-third graphics for key statistics")
            merged.append("Background visuals matching story location/context")
        elif platform == "twitter":
            merged.append("Quote card with expert opinion")
        elif platform == "instagram":
            merged.append("Story-style graphic with key facts")
        
        return merged[:5]  # Return max 5 suggestions

    def _create_enhanced_fallback_scripts(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        : Create fallback scripts using available investigation data
        """
        headline = story.get("original_headline", "")
        summary = story.get("research_summary", "")
        verified_facts = story.get("verified_facts", [])
        recent_developments = story.get("recent_developments", [])
        indian_perspective = story.get("indian_perspective", "")
        
        # Create fact-based content
        key_fact = verified_facts[0] if verified_facts else "Key details are emerging"
        recent_update = recent_developments[0] if recent_developments else "This is a developing story"
        
        return {
            "story_id": story.get("story_id", 0),
            "original_headline": headline,
            "importance_score": story.get("importance_score", 0),
            "instagram": {
                "insta_headline": headline,
                "story_content": f"🚨 {headline}\n\nKey Fact: {key_fact}\n\nRecent Update: {recent_update}\n\n{indian_perspective[:100] if indian_perspective else 'This impacts India significantly.'}\n\nWhat do you think about this development?",
                "hashtags": ["#IndiaFirst", "#NewsUpdate", "#FactCheck", "#GlobalNews"],
                "estimated_engagement": "high" if story.get("importance_score", 0) >= 8 else "medium",
                "key_facts_used": verified_facts[:2],
                "content_style": "informative_engaging"
            },
            "twitter": {
                "tweet": f"🚨 {headline}\n\n✅ Verified: {key_fact[:80]}...\n\n🔄 Latest: {recent_update[:60]}...\n\n🇮🇳 Indian angle: {indian_perspective[:80] if indian_perspective else 'Significant implications for India'}",
                "hashtags": ["#Breaking", "#IndianPerspective", "#FactCheck", "#NewsAlert"],
                "image_suggestions": ["Infographic with key statistics", "News graphic with headline"],
                "posting_priority": "immediate" if story.get("importance_score", 0) >= 9 else "scheduled",
                "facts_to_highlight": verified_facts[:3],
            },
            "youtube": {
                "full_script": f"""
                [HOOK - 15 seconds]: {headline} - and here's what you need to know. [PAUSE]
                
                [CONTEXT - 30 seconds]: Let me break this down for you. {summary[:150]}. The key players involved are {', '.join(story.get('key_players', ['various stakeholders'])[:2])}. [PAUSE]
                
                [ANALYSIS - 90 seconds]: Here are the facts we've verified: {key_fact}. [EMPHASIS] This is significant because {story.get('impact_analysis', 'it affects multiple stakeholders')[:100]}. Recent developments show that {recent_update}. [PAUSE]
                
                [INDIAN PERSPECTIVE - 45 seconds]: Now, how does this affect India? [PAUSE] {indian_perspective if indian_perspective else 'This has direct implications for Indian interests, particularly in terms of trade, security, and diplomatic relations.'}
                
                [GLOBAL IMPACT - 30 seconds]: Looking at the broader picture, {story.get('impact_analysis', 'this development could reshape regional dynamics')[:100]}. [PAUSE]
                
                [CONCLUSION - 15 seconds]: The bottom line is this: {headline.split('.')[0]} represents a significant shift that India must navigate carefully. That's the story for now.
                """,
                "estimated_duration": "3-4 minutes",
                "image_suggestions": [
                    "B-roll footage relevant to story location",
                    "Graphics showing key statistics from verified facts",
                    "Maps if geographical relevance exists",
                    "Photos of key players mentioned"
                ],
                "anchor_personality": "confident_authoritative_palki_style",
                "teleprompter_ready": True,
                "background_context": story.get("background_context", ""),
                "expert_quotes_available": story.get("expert_insights", [])[:2],
                "enhanced_fallback": True
            },
            "metadata": {
                "generation_time": datetime.now().isoformat(),
                "source_story": story.get("source_url", ""),
                "category": story.get("category", "general"),
                "enhanced_fallback_used": True,
                "investigation_data_available": bool(verified_facts or recent_developments),
                "facts_count": len(verified_facts),
                "developments_count": len(recent_developments)
            }
        }
    
    def _extract_json_from_response(self, content: str) -> str:
        """Extract JSON content from LLM response, handling markdown formatting"""
        # Remove markdown code blocks if present
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)

        # Find JSON object boundaries
        start_idx = content.find('{')
        end_idx = content.rfind('}') + 1

        if start_idx != -1 and end_idx != -1:
            return content[start_idx:end_idx]

        return content

    def _prioritize_stories(self, reports: List[Dict[str, Any]], max_stories: int) -> List[Dict[str, Any]]:
        """Prioritize stories considering investigation quality"""
        # Sort by importance score and investigation quality
        def story_priority(story):
            importance = story.get("importance_score", 0)
            data_quality = story.get("data_quality_score", 0)
            enhanced_investigation = story.get("enhanced_investigation", False)
            
            # Boost priority for stories with rich investigation data
            priority_score = importance + (data_quality * 0.5) + (2 if enhanced_investigation else 0)
            return priority_score
        
        sorted_reports = sorted(reports, key=story_priority, reverse=True)
        
        # Filter stories with minimum importance score (lowered since we have better data)
        priority_stories = [story for story in sorted_reports if story.get("importance_score", 0) >= 5]
        
        return priority_stories[:max_stories]

    def _load_templates(self) -> Dict[str, str]:
        """: Load templates with Palki Sharma style elements"""
        return {
            "youtube_palki_style": {
                "opening": "Let me tell you what's really happening here...",
                "transition": "But here's what they're not telling you...",
                "emphasis": "This is important - pay attention...",
                "indian_angle": "Now, how does this affect India?",
                "conclusion": "The bottom line is this..."
            },
            "instagram_hooks": [
                "🚨 This just happened and it changes everything...",
                "❗ Here's what the media isn't telling you about...",
                "🔥 Breaking: This could affect millions..."
            ],
            "twitter_hooks": [
                "🧵 Thread: Why this matters more than you think",
                "⚡ BREAKING: Here are the verified facts",
                "🎯 Indian perspective on today's biggest story"
            ]
        }
