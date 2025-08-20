import aiohttp
import asyncio
import os
from typing import Dict, Optional, List
import cloudinary
import cloudinary.uploader
from urllib.parse import quote_plus
from services.image_generator import ImageGenerator
import random


class PlacidTemplateGenerator:
    """
    Generates Placid images using the direct URL-based method, which is
    synchronous and more efficient.
    """
    def __init__(self):
        self.base_url = "https://placid.app/u/"

        template_ids_str = os.getenv("TEMPLATE_ID", "")
        instagram_templates = []
        if template_ids_str:
            instagram_templates = [item.strip() for item in template_ids_str.split(',')]
        
        self.template_ids = {
            "instagram": instagram_templates,
            "twitter": "your_twitter_template_id", 
            "youtube": "your_youtube_template_id"
        }

        self.template_layers = {
            "instagram": {
                "headline": "headline",
                "background_image": "background_image",
                "subheadline": "subheadline"
            }
        }

    async def generate_from_template(
        self, 
        platform: str, 
        headline: str, 
        background_image_url: str,
        story_id: str,
        workflow_id: str,
        additional_data: Dict = None,
        subheadline: str = None
    ) -> Optional[str]:
        """
        Generates an image from a Placid template and uploads it to Cloudinary.
        """
        try:
            template_id_list = self.template_ids.get(platform)
            if not template_id_list:
                raise ValueError(f"No Placid templates configured for {platform} in .env")

            template_id = random.choice(template_id_list)
            print(f"🎨 Randomly selected Placid template: {template_id}")

            # Debug: Print what we're working with
            print(f"📝 Debug - Headline: {headline}")
            print(f"📝 Debug - Subheadline parameter: {subheadline}")
            print(f"📝 Debug - Additional data: {additional_data}")

            # Step 1: Construct the final Placid image URL directly.
            placid_url = self._create_image_url(
                template_id, platform, headline, background_image_url, additional_data or {}, subheadline
            )
            
            if not placid_url:
                return None
            
            # Step 2: Download from the Placid URL and upload to Cloudinary.
            print(f"Uploading generated Placid image to Cloudinary...")
            cloudinary_url = await self._upload_to_cloudinary(
                placid_url, platform, story_id, workflow_id
            )
            
            return cloudinary_url
            
        except Exception as e:
            print(f"❌ Placid template generation failed: {e}")
            return None

    def _create_image_url(
        self, 
        template_id: str, 
        platform: str,
        headline: str, 
        background_image_url: str,
        additional_data: Dict,
        subheadline: str = None 
    ) -> Optional[str]:
        """
        Constructs the Placid URL with dynamic content in the query parameters.
        """
        layers = self.template_layers.get(platform)
        if not layers:
            print(f"❌ No layer configuration found for {platform}")
            return None

        headline_layer_name = layers["headline"]
        image_layer_name = layers["background_image"]

        # URL encode all dynamic content
        encoded_headline = quote_plus(headline)
        encoded_background_url = quote_plus(background_image_url)

        # Construct the URL as per the Placid documentation
        final_url = (
            f"{self.base_url}{template_id}?"
            f"{headline_layer_name}[text]={encoded_headline}&"
            f"{image_layer_name}[image]={encoded_background_url}"
        )

        subheadline_layer_name = layers.get("subheadline")
        subheadline_text = subheadline or additional_data.get("subheadline")

        print(f"📝 Debug - Subheadline layer name: {subheadline_layer_name}")
        print(f"📝 Debug - Final subheadline text: {subheadline_text}")

        # Handle subheadline if provided
        if subheadline_layer_name and subheadline_text:
            encoded_subheadline = quote_plus(str(subheadline_text))
            final_url += f"&{subheadline_layer_name}[text]={encoded_subheadline}"
            print(f"📝 Debug - Added subheadline to URL: {subheadline_layer_name}[text]={encoded_subheadline}")
        else:
            print(f"⚠️ Debug - Subheadline not added. Layer name: {subheadline_layer_name}, Text: {subheadline_text}")

        print(f"✅ Constructed Placid URL: {final_url}")
        return final_url
                    
    async def _upload_to_cloudinary(
        self, 
        placid_image_url: str, 
        platform: str, 
        story_id: str, 
        workflow_id: str
    ) -> str:
        """
        Downloads the image from the generated Placid URL and uploads it to Cloudinary.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(placid_image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                    else:
                        print(f"❌ Failed to download from Placid URL ({response.status})")
                        return ""

            # Upload to Cloudinary
            folder_path = f"news/processed/{workflow_id}/{story_id}/{platform}"
            
            cloud_result = cloudinary.uploader.upload(
                image_data,
                folder=folder_path,
                public_id=f"placid_template_{story_id}_{platform}",
                format="png",
                quality="auto:best",
                tags=["system_generated"]
            )
            
            secure_url = cloud_result.get("secure_url", "")
            print(f"✅ Placid image uploaded to Cloudinary: {secure_url}")
            return secure_url
            
        except Exception as e:
            print(f"❌ Cloudinary upload failed: {e}")
            return ""


class PlacidImageGenerator(ImageGenerator):
    """Enhanced ImageGenerator using Placid templates."""
    
    def __init__(self):
        super().__init__()
        self.placid_generator = PlacidTemplateGenerator()
        self.use_placid_templates = True
    
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
        # if self.use_placid_templates:
        #     # Option 1: Generate base AI image first, then apply Placid template
        #     ai_image_url = await self._generate_base_ai_image(
        #         headline, summary, platform, workflow_id, story_id
        #     )
            
        #     if ai_image_url:
        #         additional_data = {"subheadline": summary} if summary else {}
        #         return await self.placid_generator.generate_from_template(
        #             platform=platform,
        #             headline=headline, 
        #             background_image_url=ai_image_url,
        #             story_id=story_id,
        #             workflow_id=workflow_id,
        #             additional_data=additional_data
        #         )
            
        #     # Option 2: Use Placid template with no background (text-only design)
        #     else:
        #         print("⚠️ AI image failed, using text-only Placid template")
        #         return await self.placid_generator.generate_from_template(
        #             platform=platform,
        #             headline=headline,
        #             background_image_url="",  # Empty for text-only template
        #             story_id=story_id,
        #             workflow_id=workflow_id,
        #             additional_data={"subheadline": summary}
        #         )
        
        # Fallback to original method
        return await super().generate_social_image(
        headline, summary, story_id, platform, workflow_id
        )