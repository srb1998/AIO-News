import asyncio
import os
import cloudinary
import cloudinary.uploader
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict
from PIL import Image, ImageDraw, ImageFont

# This assumes llm_client is in a 'core' directory relative to this file's location
from core.llm_client import llm_client

# Cloudinary Configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

class ImageGenerator:
    def __init__(self):
        self.platform_specs = {
            "instagram": {"aspect_ratio": "1:1", "dimensions": "1080x1080"},
            "twitter": {"aspect_ratio": "16:9", "dimensions": "1200x675"},
            "youtube": {"aspect_ratio": "16:9", "dimensions": "1280x720"}
        }
        # Using your new, more robust font finding logic
        self.font_paths = {
            'bold': [
                "C:/Windows/Fonts/verdanab.ttf", "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/calibrib.ttf", "C:/Windows/Fonts/arial.ttf"
            ],
            'regular': [
                "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/calibri.ttf",
                "C:/Windows/Fonts/verdana.ttf"
            ]
        }
        # Note: For non-Windows environments (like a Linux server), you'll need to
        # place font files (e.g., Inter-Bold.ttf) in a 'fonts' folder and update paths.
        # Example for Linux: 'bold': [os.path.join('fonts', 'Inter-Bold.ttf')]

    async def generate_social_image(self, headline: str, summary: str, story_id: str, platform: str, workflow_id: str) -> str:
        """
        Generates an AI image, then applies the headline locally using the advanced
        Pillow function before uploading the final result.
        """
        print(f"🤖 No user image provided for {platform}. Generating AI image...")
        temp_ai_image_path = f"temp_{story_id}_{platform}_ai_base.jpg"
        temp_output_path = f"temp_{story_id}_{platform}_ai_final.png"
        specs = self.platform_specs.get(platform, self.platform_specs["instagram"])

        try:
            # Step 1: Generate the base AI image
            prompt = self._create_platform_prompt(headline, summary, platform, specs)
            print(f"Generating image for {platform} with prompt: {prompt}")
            base_image_bytes = await llm_client.generate_image(prompt)
            if not base_image_bytes:
                print(f"❌ Failed to generate AI image for {platform}")
                return ""

            with open(temp_ai_image_path, "wb") as f:
                f.write(base_image_bytes)

            # Step 2: Apply the headline using your advanced Pillow function
            print(f"🎨 Applying advanced headline to AI-generated image...")
            self.add_professional_headline(
                image_path=temp_ai_image_path,
                output_path=temp_output_path,
                headline=headline,
                subheadline=summary,
                highlight_color="#FF6B35" # Example color, you can make this dynamic
            )

            # Step 3: Upload the final, processed image to Cloudinary
            folder_path = f"news/processed/{workflow_id}/{story_id}/{platform}"
            
            width, height = map(int, specs["dimensions"].split('x'))
            cloud_result = cloudinary.uploader.upload(
                temp_output_path,
                folder=folder_path,
                transformation=[
                    {"width": width, "height": height, "crop": "fill"},
                    {"quality": "auto:best", "format": "jpg"}
                ]
            )
            return cloud_result["secure_url"]

        except Exception as e:
            print(f"❌ AI Image generation and processing failed for {platform}: {e}")
            return ""
        finally:
            # Clean up all temporary files
            for p in [temp_ai_image_path, temp_output_path]:
                if os.path.exists(p):
                    os.remove(p)

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
        Applies the advanced headline to a user-provided image and uploads to Cloudinary.
        """
        print(f"🎨 Applying advanced headline to user image for {platform} (Story {story_id})")
        temp_input_path = f"temp_{story_id}_{platform}_user_input.jpg"
        temp_output_path = f"temp_{story_id}_{platform}_user_final.png"

        try:
            # Step 1: Get the user-provided image to a local path
            if image_path_or_url.startswith("http"):
                 async with aiohttp.ClientSession() as session:
                    async with session.get(image_path_or_url) as resp:
                        if resp.status == 200:
                            with open(temp_input_path, 'wb') as f:
                                f.write(await resp.read())
                            image_path = temp_input_path
                        else:
                            raise Exception(f"Failed to download image from URL: {image_path_or_url}")
            else:
                image_path = image_path_or_url

            # Step 2: Apply the text overlay using your advanced Pillow function
            self.add_professional_headline(
                image_path=image_path,
                output_path=temp_output_path,
                headline=headline,
                subheadline=subheadline,
                highlight_color="#FF6B35"
            )

            # Step 3: Upload the processed image to Cloudinary
            specs = self.platform_specs.get(platform, self.platform_specs["instagram"])
            width, height = map(int, specs["dimensions"].split('x'))
            
            folder_path = f"news/processed/{workflow_id}/{story_id}/{platform}"

            cloud_result = cloudinary.uploader.upload(
                temp_output_path,
                folder=folder_path,
                public_id=f"processed_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                transformation=[
                    {"width": width, "height": height, "crop": "fill"},
                    {"quality": "auto:best", "format": "jpg"}
                ]
            )
            print(f"✅ Headline applied and uploaded to Cloudinary: {cloud_result['secure_url']}")
            return cloud_result["secure_url"]

        except Exception as e:
            print(f"❌ Failed to apply headline to user image: {e}")
            return ""
        finally:
            for p in [temp_input_path, temp_output_path]:
                if os.path.exists(p):
                    os.remove(p)

    def add_professional_headline(
        self, image_path: str, output_path: str, headline: str, subheadline: str = None,
        max_width_ratio: float = 0.9, base_font_size: int = 42, highlight_color: str = "#FF0000"
    ):
        """
        Your powerful, custom headline generation function.
        """
        def get_font(font_list, size):
            for font_path in font_list:
                try:
                    if os.path.exists(font_path):
                        return ImageFont.truetype(font_path, size)
                except Exception:
                    continue
            print("⚠️ Custom fonts not found, using default.")
            return ImageFont.load_default()

        # Load base image
        img = Image.open(image_path).convert("RGBA")
        W, H = img.size
        max_width = int(W * max_width_ratio)
        draw = ImageDraw.Draw(img, "RGBA")

        # HEADLINE WRAPPING
        font_size = int(base_font_size * (W / 1080)) # Scale font with image size
        font_bold = get_font(self.font_paths['bold'], font_size)

        words = headline.upper().split()
        lines = []
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            if draw.textlength(test_line, font=font_bold) <= max_width:
                current_line.append(word)
            else:
                if current_line: lines.append(' '.join(current_line))
                current_line = [word]
        if current_line: lines.append(' '.join(current_line))

        # Re-wrap with smaller font if more than 2 lines
        while len(lines) > 2 and font_size > 24:
            font_size -= 3
            font_bold = get_font(self.font_paths['bold'], font_size)
            lines, current_line = [], []
            for word in words:
                test_line = ' '.join(current_line + [word])
                if draw.textlength(test_line, font=font_bold) <= max_width: current_line.append(word)
                else:
                    if current_line: lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line: lines.append(' '.join(current_line))

        line_height = int(font_size * 1.2)
        line_spacing = 8
        total_text_height = len(lines) * line_height + (len(lines) - 1) * line_spacing
        start_y = H - total_text_height - int(H * 0.15) # Position 15% from bottom

        # OVERLAY
        bg_padding = 25
        bg_top = start_y - bg_padding
        bg_bottom = start_y + total_text_height + bg_padding
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([0, bg_top, W, bg_bottom], fill=(0, 0, 0, 190))
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        # Highlight + Text
        hex_color = highlight_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        for i, line in enumerate(lines):
            y_pos = start_y + (i * (line_height + line_spacing))
            line_width = draw.textlength(line, font=font_bold)
            x_pos = (W - line_width) / 2
            draw.rectangle([x_pos, y_pos, x_pos + line_width, y_pos + line_height], fill=(r, g, b, 100))
            draw.text((x_pos, y_pos), line, font=font_bold, fill="white")

        # SUBHEADLINE
        if subheadline:
            sub_font_size = int(font_size * 0.65)
            sub_font = get_font(self.font_paths['regular'], sub_font_size)
            sub_words = subheadline.split()
            sub_lines, current_sub_line = [], []
            for word in sub_words:
                test_line = ' '.join(current_sub_line + [word])
                if draw.textlength(test_line, font=sub_font) <= max_width: current_sub_line.append(word)
                else:
                    if current_sub_line: sub_lines.append(' '.join(current_sub_line))
                    current_sub_line = [word]
            if current_sub_line: sub_lines.append(' '.join(current_sub_line))

            sub_line_height = int(sub_font_size * 1.1)
            sub_total_height = len(sub_lines) * sub_line_height
            sub_start_y = start_y + total_text_height + 40
            
            # Subheadline background
            sub_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            sub_draw = ImageDraw.Draw(sub_overlay)
            sub_draw.rectangle([0, sub_start_y - 20, W, sub_start_y + sub_total_height + 20], fill=(0, 0, 0, 190))
            img = Image.alpha_composite(img, sub_overlay)
            draw = ImageDraw.Draw(img)

            for i, sub_line in enumerate(sub_lines):
                y_pos = sub_start_y + (i * sub_line_height)
                line_width = draw.textlength(sub_line, font=sub_font)
                x_pos = (W - line_width) / 2
                draw.text((x_pos, y_pos), sub_line, font=sub_font, fill="#DDDDDD")

        img.convert("RGB").save(output_path, "PNG", quality=95)


    def _create_platform_prompt(self, headline: str, summary: str, platform: str, specs: dict) -> str:
        """Generates the prompt for the AI image generator."""
        base_prompt = (
            f"Photorealistic, editorial news style image for a {platform.upper()} post. "
            f"The image must be exactly {specs['dimensions']} pixels with a {specs['aspect_ratio']} aspect ratio. "
            f"The scene should visually represent the headline: '{headline}'. "
            f"Focus on high-resolution, professional quality. Avoid any text, logos, or watermarks on the image itself. "
            f"The tone should be serious and newsworthy."
        )
        if platform == "youtube":
            base_prompt += " The composition should be bold and high-contrast to work well as a small thumbnail."
        return base_prompt