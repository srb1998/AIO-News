import google.generativeai as genai
from openai import OpenAI
from config.settings import settings
import time
from typing import Dict, Any

class LLMClient:
    def __init__(self):
        # Configure Gemini
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Configure OpenAI  
        if settings.OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    def generate_with_gemini(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Generate text using Gemini (FREE!)"""
        print("🔄 Generating with Gemini...")
        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.7,
                )
            )
            
            # Estimate token usage (Gemini doesn't provide exact count)
            estimated_tokens = len(prompt.split()) + len(response.text.split())
            
            return {
                "content": response.text,
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

# Global LLM client
llm_client = LLMClient()