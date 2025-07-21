import os
from google import genai
from google.genai import types
from openai import OpenAI
from config.settings import settings
import time
from typing import Dict, Any
import asyncio

class LLMClient:
    def __init__(self):
        # Configure new Google GenAI SDK
        if settings.GEMINI_API_KEY:
            # Initialize the client with API key (same as your working test)
            self.genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        # Configure OpenAI  
        if settings.OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    def generate_with_gemini(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Generate text using Gemini """

        try:
            response = self.genai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=1.0
                )
            )
            
            # Extract text from response
            text_content = response.text if hasattr(response, 'text') else str(response)
            
            # Estimate token usage (Gemini doesn't provide exact count)
            estimated_tokens = len(prompt.split()) + len(text_content.split())
            
            return {
                "content": text_content,
                "token_usage": {
                    "model": "gemini-2.0-flash",
                    "tokens": estimated_tokens,
                    "cost": 0.0  # FREE!
                }
            }
        except Exception as e:
            print(f"❌ Gemini error: {e}")
            return {"error": str(e)}
    
    def generate_with_openai(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Generate text using OpenAI GPT-4o-mini"""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7
            )
            
            tokens_used = response.usage.total_tokens
            cost = (tokens_used / 1000) * settings.COST_PER_1K_TOKENS_OPENAI
            
            return {
                "content": response.choices[0].message.content,
                "token_usage": {
                    "model": "gpt-4o-mini", 
                    "tokens": tokens_used,
                    "cost": cost
                }
            }
        except Exception as e:
            print(f"❌ OpenAI error: {e}")
            return {"error": str(e)}
    
    def smart_generate(self, prompt: str, max_tokens: int = 800, priority: str = "normal") -> Dict[str, Any]:
        """Smart model selection based on priority and budget"""
        
        # For critical tasks or when Gemini fails, use OpenAI
        if priority == "critical":
            result = self.generate_with_openai(prompt, max_tokens)
            if "error" not in result:
                return result
        
        # Default: Try Gemini first (FREE!)
        result = self.generate_with_gemini(prompt, max_tokens)
        if "error" not in result:
            return result
        
        # Fallback to OpenAI if Gemini fails
        print("🔄 Gemini failed, trying OpenAI...")
        return self.generate_with_openai(prompt, max_tokens)

    async def generate_image(self, prompt: str) -> bytes:
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

# Global LLM client
llm_client = LLMClient()