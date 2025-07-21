from PIL import Image, ImageDraw, ImageFont
import os

def add_professional_headline(
    image_path: str,
    output_path: str,
    headline: str,
    subheadline: str = None,
    max_width_ratio: float = 0.9,
    base_font_size: int = 42,
    highlight_color: str = "#FF0000",
    font_paths: dict = None
) -> str:
    
    if font_paths is None:
        font_paths = {
            'bold': [
                "C:/Windows/Fonts/verdanab.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/calibrib.ttf",
                "C:/Windows/Fonts/arial.ttf"
            ],
            'regular': [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/calibri.ttf",
                "C:/Windows/Fonts/verdana.ttf"
            ]
        }
    
    def get_font(font_list, size):
        for font_path in font_list:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except:
                continue
        return ImageFont.load_default()

    # Load base image
    img = Image.open(image_path).convert("RGBA")
    W, H = img.size
    max_width = int(W * max_width_ratio)
    
    # Create a draw object
    draw = ImageDraw.Draw(img, "RGBA")

    # HEADLINE WRAPPING
    font_size = base_font_size
    font_bold = get_font(font_paths['bold'], font_size)

    words = headline.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        if draw.textlength(test_line, font=font_bold) <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
    if current_line:
        lines.append(' '.join(current_line))

    while len(lines) > 2 and font_size > 24:
        font_size -= 3
        font_bold = get_font(font_paths['bold'], font_size)
        lines = []
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            if draw.textlength(test_line, font=font_bold) <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
        if current_line:
            lines.append(' '.join(current_line))

    line_height = int(font_size * 1.2)
    line_spacing = 8
    total_text_height = len(lines) * line_height + (len(lines) - 1) * line_spacing
    start_y = H - total_text_height - 150

    # ✅ OVERLAY (real blended black fade)
    bg_padding = 25
    bg_top = start_y - bg_padding
    bg_bottom = start_y + total_text_height + bg_padding

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([0, bg_top, W, bg_bottom], fill=(0, 0, 0, 200))  # Adjust alpha for fade
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)  # re-init draw after composite

    # Convert hex to RGB
    hex_color = highlight_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    # Highlight + Text
    for i, line in enumerate(lines):
        y_pos = start_y + (i * (line_height + line_spacing))
        line_width = draw.textlength(line, font=font_bold)
        x_pos = (W - line_width) / 2

        # Highlight
        draw.rectangle(
            [x_pos, y_pos, x_pos + line_width, y_pos + line_height],
            fill=(r, g, b, 100)
        )

        # Text
        draw.text((x_pos, y_pos), line, font=font_bold, fill="white")

    # SUBHEADLINE
    if subheadline:
        sub_font_size = int(font_size * 0.65)
        sub_font = get_font(font_paths['regular'], sub_font_size)

        sub_words = subheadline.split()
        sub_lines = []
        current_sub_line = []

        for word in sub_words:
            test_line = ' '.join(current_sub_line + [word])
            if draw.textlength(test_line, font=sub_font) <= max_width:
                current_sub_line.append(word)
            else:
                if current_sub_line:
                    sub_lines.append(' '.join(current_sub_line))
                    current_sub_line = [word]
                else:
                    sub_lines.append(word)

        if current_sub_line:
            sub_lines.append(' '.join(current_sub_line))

        sub_line_height = int(sub_font_size * 1.1)
        sub_total_height = len(sub_lines) * sub_line_height
        sub_start_y = start_y + total_text_height + 40

        # Optional subtle black fade under subheadline
        sub_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sub_draw = ImageDraw.Draw(sub_overlay)
        sub_draw.rectangle([0, sub_start_y - 20, W, sub_start_y + sub_total_height + 20], fill=(0, 0, 0, 200))
        img = Image.alpha_composite(img, sub_overlay)
        draw = ImageDraw.Draw(img)

        for i, sub_line in enumerate(sub_lines):
            y_pos = sub_start_y + (i * sub_line_height)
            line_width = draw.textlength(sub_line, font=sub_font)
            x_pos = (W - line_width) / 2

            draw.text((x_pos + 1, y_pos + 1), sub_line, font=sub_font, fill=(0, 0, 0, 10))
            draw.text((x_pos, y_pos), sub_line, font=sub_font, fill="white")

    # Save result
    img.save(output_path, "PNG")
    return output_path

# === USAGE EXAMPLES ===
if __name__ == "__main__":
    # Example 1: Earth rotation news
    add_professional_headline(
        image_path="test.jpg",
        output_path="earth_rotation_news.png",
        headline="Earth has started to rotate FASTER",
        subheadline="Days becoming shorter, say scientists",
        highlight_color="#FF6B35"  # Orange
    )
    
    # Example 2: Earthquake news  
    add_professional_headline(
        image_path="test.jpg",
        output_path="earthquake_news.png", 
        headline="Delhi NCR struck with 2nd strong earthquake in 36 hours",
        subheadline="North India on alert due to tremors",
        highlight_color="#DB2710" 
    )
    
    print("✅ Headlines generated with individual line highlighting!")