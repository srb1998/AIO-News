import aiohttp
import asyncio
import os
from typing import Dict, Optional, List
import cloudinary
import cloudinary.uploader

from services.image_generator import ImageGenerator
from core.llm_client import llm_client

class PlacidTemplateGenerator:
    def __init__(self):
        self.api_key = os.getenv("PLACID_API_KEY")
        self.base_url = "https://api.placid.app/api"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        self.template_ids = {
            "instagram": "3ub0a06bci9lw",
            "twitter": "your_twitter_template_id", 
            "youtube": "your_youtube_template_id"
        }

    async def generate_from_template(
        self, 
        platform: str, 
        headline: str, 
        background_image_url: str,
        story_id: str,
        workflow_id: str,
        additional_data: Dict = None
    ) -> Optional[str]:
        """
        Generate image from Placid template with dynamic content.
        
        Args:
            platform: Target platform (instagram, twitter, youtube)
            headline: Dynamic headline text
            background_image_url: URL of user's uploaded image
            story_id: Unique story identifier
            workflow_id: Workflow identifier
            additional_data: Any additional dynamic data for template
        """
        try:
            template_id = self.template_ids.get(platform)
            if not template_id:
                raise ValueError(f"No Placid template configured for {platform}")

            # Step 1: Generate image from template
            placid_url = await self._create_image_from_template(
                template_id, headline, background_image_url, additional_data or {}
            )
            
            if not placid_url:
                return None
            
            # Step 2: Upload to Cloudinary for permanent storage
            cloudinary_url = await self._upload_to_cloudinary(
                placid_url, platform, story_id, workflow_id
            )
            
            return cloudinary_url
            
        except Exception as e:
            print(f"❌ Placid template generation failed: {e}")
            return None

    async def _create_image_from_template(
        self, 
        template_id: str, 
        headline: str, 
        background_image_url: str,
        additional_data: Dict
    ) -> Optional[str]:
        """Generate image using Placid API."""
        
        # Placid API payload - map your template's dynamic fields
        payload = {
            "template_uuid": template_id,
            "data": {
                # Map these field names to match your Placid template
                "headline": headline,
                "background_image": background_image_url,
                **additional_data  # Any additional dynamic fields
            },
            "create_now": True,  # Generate immediately
            "webhook_url": None
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/rest",
                headers=self.headers,
                json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # Placid returns the generated image URL directly
                    return result.get("image_url") or result.get("url")
                else:
                    error_text = await response.text()
                    print(f"❌ Placid API error: {response.status} - {error_text}")
                    return None

    async def _upload_to_cloudinary(
        self, 
        placid_image_url: str, 
        platform: str, 
        story_id: str, 
        workflow_id: str
    ) -> str:
        """Download from Placid and upload to Cloudinary for permanent storage."""
        try:
            # Download the generated image from Placid
            async with aiohttp.ClientSession() as session:
                async with session.get(placid_image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                    else:
                        print(f"❌ Failed to download from Placid: {response.status}")
                        return ""

            # Upload to Cloudinary with high quality settings
            folder_path = f"news/processed/{workflow_id}/{story_id}/{platform}"
            
            cloud_result = cloudinary.uploader.upload(
                image_data,
                folder=folder_path,
                public_id=f"placid_template_{story_id}_{platform}",
                format="png",  # Use PNG for high quality
                quality="auto:best"
            )
            
            print(f"✅ Placid image uploaded to Cloudinary: {cloud_result['secure_url']}")
            return cloud_result["secure_url"]
            
        except Exception as e:
            print(f"❌ Cloudinary upload failed: {e}")
            return ""

    async def generate_for_multiple_platforms(
        self, 
        headline: str, 
        background_image_url: str, 
        story_id: str,
        workflow_id: str,
        platforms: List[str] = None,
        additional_data: Dict = None
    ) -> Dict[str, str]:
        """Generate templates for multiple platforms simultaneously."""
        
        if not platforms:
            platforms = ["instagram", "twitter", "youtube"]
        
        # Create concurrent tasks for all platforms
        tasks = []
        for platform in platforms:
            task = self.generate_from_template(
                platform=platform,
                headline=headline,
                background_image_url=background_image_url,
                story_id=story_id,
                workflow_id=workflow_id,
                additional_data=additional_data
            )
            tasks.append((platform, task))
        
        # Execute all tasks concurrently
        results = {}
        for platform, task in tasks:
            try:
                url = await task
                if url:
                    results[platform] = url
                    print(f"✅ {platform} Placid template created: {url}")
                else:
                    print(f"❌ {platform} Placid template failed")
                    results[platform] = ""
            except Exception as e:
                print(f"❌ {platform} Placid template error: {e}")
                results[platform] = ""
        
        return results


# Integration with your existing ImageGenerator class
class PlacidImageGenerator(ImageGenerator):
    """Enhanced ImageGenerator using Placid templates."""
    
    def __init__(self):
        super().__init__()
        self.placid_generator = PlacidTemplateGenerator()
        self.use_placid_templates = True  # Feature flag
    
    async def apply_headline_to_image(
        self,
        image_path_or_url: str,
        story_id: str,
        platform: str,
        headline: str,
        subheadline: str,
        workflow_id: str
    ) -> str:
        """
        Use Placid templates instead of Pillow processing for better quality.
        """
        if self.use_placid_templates:
            print(f"🎨 Using Placid template for {platform} (Story {story_id})")
            
            # Prepare additional data for template
            additional_data = {}
            if subheadline:
                additional_data["subheadline"] = subheadline
            
            # Use Placid template system
            placid_url = await self.placid_generator.generate_from_template(
                platform=platform,
                headline=headline,
                background_image_url=image_path_or_url,
                story_id=story_id,
                workflow_id=workflow_id,
                additional_data=additional_data
            )
            
            if placid_url:
                print(f"✅ Placid template applied successfully: {placid_url}")
                return placid_url
            else:
                print("⚠️ Placid template failed, falling back to Pillow...")
        
        # Fallback to original Pillow method if Placid fails
        return await super().apply_headline_to_image(
            image_path_or_url, story_id, platform, headline, subheadline, workflow_id
        )
    
    async def generate_social_image(
        self, 
        headline: str, 
        summary: str, 
        story_id: str, 
        platform: str, 
        workflow_id: str
    ) -> str:
        """
        Generate AI image then apply Placid template, or use Placid with text-only template.
        """
        if self.use_placid_templates:
            # Option 1: Generate base AI image first, then apply Placid template
            ai_image_url = await self._generate_base_ai_image(
                headline, summary, platform, workflow_id, story_id
            )
            
            if ai_image_url:
                additional_data = {"subheadline": summary} if summary else {}
                return await self.placid_generator.generate_from_template(
                    platform=platform,
                    headline=headline, 
                    background_image_url=ai_image_url,
                    story_id=story_id,
                    workflow_id=workflow_id,
                    additional_data=additional_data
                )
            
            # Option 2: Use Placid template with no background (text-only design)
            # You can create a separate template for this case
            else:
                print("⚠️ AI image failed, using text-only Placid template")
                return await self.placid_generator.generate_from_template(
                    platform=platform,
                    headline=headline,
                    background_image_url="",  # Empty for text-only template
                    story_id=story_id,
                    workflow_id=workflow_id,
                    additional_data={"subheadline": summary}
                )
        
        # Fallback to original method
        return await super().generate_social_image(
            headline, summary, story_id, platform, workflow_id
        )
        
    async def _generate_base_ai_image(
        self, headline: str, summary: str, platform: str, workflow_id: str, story_id: str
    ) -> str:
        """Generate base AI image without text overlay for Placid template use."""
        temp_ai_path = f"temp_{story_id}_{platform}_ai_base.jpg"
        
        try:
            specs = self.platform_specs.get(platform, self.platform_specs["instagram"])
            
            # Updated prompt - no text needed since Placid will add it
            prompt = (
                f"Clean, professional background image for {platform.upper()} post. "
                f"The image must be {specs['dimensions']} pixels. "
                f"Visual theme related to: '{headline}'. "
                f"No text, logos, or overlays - clean background only for template overlay. "
                f"High-resolution, professional quality."
            )
            
            base_image_bytes = await llm_client.generate_image(prompt)
            if not base_image_bytes:
                return ""

            with open(temp_ai_path, "wb") as f:
                f.write(base_image_bytes)
            
            # Upload base image to Cloudinary
            folder_path = f"news/ai_generated/{workflow_id}/{story_id}"
            cloud_result = cloudinary.uploader.upload(
                temp_ai_path,
                folder=folder_path,
                public_id=f"ai_base_{platform}",
                format="jpg",
                quality="auto:best"
            )
            
            return cloud_result["secure_url"]
            
        except Exception as e:
            print(f"❌ Base AI image generation failed: {e}")
            return ""
        finally:
            if os.path.exists(temp_ai_path):
                os.remove(temp_ai_path)
