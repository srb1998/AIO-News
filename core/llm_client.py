# core/llm_client.py

import os
from google import genai
from google.genai import types
from openai import OpenAI
from openai import AsyncOpenAI
from config.settings import settings
import time
from typing import Dict, Any, Optional, List
import asyncio

class LLMClient:
    def __init__(self):
        # Configure new Google GenAI SDK
        if settings.GEMINI_API_KEY:
            # Initialize the client with API key (same as your working test)
            self.genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        # Gemini client for Search Grounding
        if settings.GEMINI_SEARCH_API_KEY:
            self.gemini_search_client = genai.Client(api_key=settings.GEMINI_SEARCH_API_KEY)
        
        # Configure OpenAI  
        if settings.OPENAI_API_KEY:
            self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    def generate_with_gemini(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Generate text using Gemini """

        try:
            
            response = self.genai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.80
                )
            )
            
            # Extract text from response
            text_content = response.text if hasattr(response, 'text') else str(response)
            
            # Estimate token usage (Gemini doesn't provide exact count)
            estimated_tokens = len(prompt.split()) + len(text_content.split())
            
            return {
                "content": text_content,
                "token_usage": {
                    "model": "gemini-2.5-flash",
                    "tokens": estimated_tokens,
                    "cost": 0.0  # FREE!
                }
            }
        except Exception as e:
            print(f"❌ Gemini error: {e}")
            if e['error']['code'] == 503:
                time.sleep(2)  # Simple retry delay
                return self.generate_with_gemini_pro(prompt, max_tokens)
            return {"error": str(e)}
    
    def generate_with_gemini_pro(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Retry Gemini generation once after a delay."""
        try:
            response = self.genai_client.models.generate_content(
                model='gemini-2.5-pro',
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.80
                )
            )
            text_content = response.text if hasattr(response, 'text') else str(response)
            estimated_tokens = len(prompt.split()) + len(text_content.split())
            return {
                "content": text_content,
                "token_usage": {
                    "model": "gemini-2.5-flash",
                    "tokens": estimated_tokens,
                    "cost": 0.0
                }
            }
        except Exception as e:
            print(f"❌ Gemini pro retry failed with error: {e}")
            return {"error": str(e)}
    
    async def generate_with_openai(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Generate text using OpenAI GPT-4o-mini asynchronously."""
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7
            )
            tokens_used = response.usage.total_tokens
            cost = (tokens_used / 1_000_000) * 0.15 # gpt-4o-mini cost per 1M tokens
            return {
                "content": response.choices[0].message.content,
                "token_usage": {"model": "gpt-4o-mini", "tokens": tokens_used, "cost": cost}
            }
        except Exception as e:
            print(f"❌ OpenAI error: {e}")
            return {"error": str(e)}
        
    def generate_with_gemini_search_grounding(self, query: str, max_tokens: int = 4000) -> Dict[str, Any]:
        """
        Generate text using Gemini with Search Grounding for real-time information
        Uses separate API key for search grounding functionality
        """
        try:
            # Use search grounding mode with the dedicated client
            response = self.gemini_search_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=query,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.7,
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            
            # Extract text from response
            text_content = response.text if hasattr(response, 'text') else str(response)
            
            # Extract grounding metadata if available
            grounding_metadata = []
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata'):
                    grounding_metadata = candidate.grounding_metadata
            
            # Estimate token usage
            estimated_tokens = len(query.split()) + len(text_content.split())
            
            return {
                "content": text_content,
                "grounding_metadata": grounding_metadata,
                "token_usage": {
                    "model": "gemini-2.5-flash-exp-search",
                    "tokens": estimated_tokens,
                    "search_grounded": True
                }
            }
        except Exception as e:
            print(f"❌ Gemini Search Grounding error: {e}")
            return {"error": str(e)}
    
    async def smart_generate(self, prompt: str, max_tokens: int = 8000, priority: str = "normal") -> Dict[str, Any]:
        """Smart model selection, now fully asynchronous."""
        if priority == "critical":
            return await self.generate_with_openai(prompt, max_tokens)
        
        # Run the synchronous Gemini call in a separate thread to avoid blocking
        result = await asyncio.to_thread(self.generate_with_gemini, prompt, max_tokens)
        
        if "error" not in result:
            return result
        
        print("🔄 Gemini failed, trying OpenAI as fallback...")
        return await self.generate_with_openai(prompt, max_tokens)
    
    async def smart_generate_with_search(self, query: str, max_tokens: int = 2000) -> Dict[str, Any]:
        """
        Smart generation with search grounding, async wrapper
        First tries Gemini Search Grounding, falls back to regular generation
        """
        try:
            # Run Gemini Search Grounding in thread
            result = await asyncio.to_thread(self.generate_with_gemini_search_grounding, query, max_tokens)
            
            if "error" not in result:
                print("✅ Gemini Search Grounding successful")
                return result
            
            print("🔄 Search grounding failed, trying regular Gemini...")
            # Fallback to regular generation
            return await self.smart_generate(query, max_tokens, "normal")
            
        except Exception as e:
            print(f"❌ Smart generation with search failed: {e}")
            return {"error": str(e)}
    
    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generates a vector embedding for a given text using OpenAI.
        """
        if not text: return None
        try:
            text = text.replace("\n", " ").strip()
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=[text]
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"❌ OpenAI embedding failed: {e}")
            return None

    def _generate_image_sync(self, prompt: str) -> bytes:
        """
        Use Gemini 2.0-Flash to generate an image.
        Returns image bytes or empty bytes on failure.
        """
        try:
            # Use the exact same approach as your working test
            response = self.genai_client.models.generate_content(
                model="gemini-2.0-flash-preview-image-generation",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['TEXT', 'IMAGE']
                )
            )
            
            # Extract inline_data (same logic as your working test)
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    return part.inline_data.data
            
            print("❌ No image data found in Gemini response")
            return b""
            
        except Exception as e:
            print(f"❌ Gemini image generation error: {e}")
            return b""
    
    async def generate_image(self, prompt: str) -> bytes:
        """Asynchronously generates an image using Gemini."""
        return await asyncio.to_thread(self._generate_image_sync, prompt)

# Global LLM client
llm_client = LLMClient()