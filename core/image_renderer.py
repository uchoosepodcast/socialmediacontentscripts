import os
import re
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from typing import Dict, Any, Optional, Tuple
import logging
from core.config import IssueMetadata, RunConfig, PlatformConfig

logger = logging.getLogger(__name__)

# Fallback fonts
DEFAULT_FONT_REGULAR = "arial.ttf"
DEFAULT_FONT_BOLD = "arialbd.ttf"
if os.name == 'nt':
    DEFAULT_FONT_REGULAR = r"C:\Windows\Fonts\verdana.ttf"
    DEFAULT_FONT_BOLD = r"C:\Windows\Fonts\verdanab.ttf"

class ImageRenderer:
    def __init__(self):
        try:
            self.resample_filter = Image.Resampling.LANCZOS
        except AttributeError:
            self.resample_filter = Image.LANCZOS

    def _get_font(self, path: str, size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype(path, size)
        except IOError:
            logger.warning(f"Font {path} not found. Using default.")
            return ImageFont.load_default()

    def _fit_cover_proportional(self, cover_img: Image.Image, target_width: int, target_height: int) -> Tuple[Image.Image, int, int]:
        """Proportionally fits the cover within the target dimensions, letterboxing if necessary."""
        img_ratio = cover_img.width / cover_img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # Image is wider than target
            new_width = target_width
            new_height = int(target_width / img_ratio)
        else:
            # Image is taller than target
            new_height = target_height
            new_width = int(target_height * img_ratio)

        resized = cover_img.resize((new_width, new_height), self.resample_filter)

        # Calculate centering offsets
        offset_x = (target_width - new_width) // 2
        offset_y = (target_height - new_height) // 2

        return resized, offset_x, offset_y

    def _auto_scale_text(self, text: str, font_path: str, max_width: int, max_height: int, start_size: int, min_size: int = 14) -> Tuple[ImageFont.FreeTypeFont, str, int]:
        """Dynamically shrinks text size and truncates gracefully if it still exceeds bounds."""
        current_size = start_size
        font = self._get_font(font_path, current_size)

        def wrap_text(t: str, f: ImageFont.FreeTypeFont) -> Tuple[str, int]:
            words = t.split()
            lines = []
            current_line = []
            for word in words:
                current_line.append(word)
                test_line = " ".join(current_line)
                bbox = f.getbbox(test_line)
                if (bbox[2] - bbox[0]) > max_width:
                    if len(current_line) > 1:
                        current_line.pop()
                        lines.append(" ".join(current_line))
                        current_line = [word]
                    else:
                        lines.append(" ".join(current_line))
                        current_line = []
            if current_line:
                lines.append(" ".join(current_line))

            wrapped = "\n".join(lines)

            # calculate height
            draw = ImageDraw.Draw(Image.new('RGB', (1,1)))
            bbox = draw.multiline_textbbox((0,0), wrapped, font=f)
            h = bbox[3] - bbox[1]
            return wrapped, h

        wrapped_text, h = wrap_text(text, font)

        while h > max_height and current_size > min_size:
            current_size -= 2
            font = self._get_font(font_path, current_size)
            wrapped_text, h = wrap_text(text, font)

        # If it still doesn't fit at min_size, truncate at sentence boundaries
        if h > max_height:
            sentences = re.split(r'(?<=[.!?]) +', text)
            while sentences and h > max_height:
                sentences.pop()
                if sentences:
                    truncated = " ".join(sentences) + "..."
                    wrapped_text, h = wrap_text(truncated, font)
                else:
                    wrapped_text, h = wrap_text(text[:50] + "...", font) # hard truncate

        return font, wrapped_text, current_size

    def render_social_image(self, config: RunConfig, platform_config: PlatformConfig, issue: IssueMetadata, cover_path: str, output_path: str) -> bool:
        """Unified layout engine for social media images."""

        if platform_config.name.lower() == "instagram":
            canvas_w, canvas_h = 1080, 1080
            cover_area_w = 550
        elif platform_config.name.lower() == "facebook":
            canvas_w, canvas_h = 1200, 630
            cover_area_w = 400
        elif platform_config.name.lower() == "twitter":
            canvas_w, canvas_h = 1920, 1080
            cover_area_w = 700
        else:
            canvas_w, canvas_h = 1080, 1080
            cover_area_w = 550

        margin = 30
        bg_color = (255, 255, 255)
        text_color = (0, 0, 0)

        try:
            img = Image.new('RGB', (canvas_w, canvas_h), color=bg_color)
            draw = ImageDraw.Draw(img)

            # 1. Proportional Cover
            cover_max_h = canvas_h - (margin * 2)
            try:
                with Image.open(cover_path) as cover:
                    if cover.mode != 'RGB':
                        cover = cover.convert('RGB')

                    resized_cover, offset_x, offset_y = self._fit_cover_proportional(
                        cover, cover_area_w, cover_max_h
                    )

                    # Place cover with margin
                    paste_x = canvas_w - cover_area_w - margin + offset_x
                    paste_y = margin + offset_y
                    img.paste(resized_cover, (paste_x, paste_y))
            except Exception as e:
                logger.error(f"Failed to process cover image {cover_path}: {e}")
                return False

            # 2. Dynamic Text Layout
            text_area_w = canvas_w - cover_area_w - (margin * 3)
            current_y = margin

            # Title
            title_str = f"{config.title} #{issue.issue_number}"
            title_font, wrapped_title, final_size = self._auto_scale_text(
                title_str, DEFAULT_FONT_BOLD, text_area_w, 150, start_size=48, min_size=24
            )
            draw.multiline_text((margin, current_y), wrapped_title, font=title_font, fill=text_color)
            current_y += draw.multiline_textbbox((0,0), wrapped_title, font=title_font)[3] + 20

            # Credits
            if issue.credits:
                writers = [c['name'] for c in issue.credits if c['role'] and 'writer' in c['role'].lower()]
                artists = [c['name'] for c in issue.credits if c['role'] and 'artist' in c['role'].lower() or 'penciler' in c['role'].lower()]

                credit_font = self._get_font(DEFAULT_FONT_REGULAR, 24)
                if writers:
                    w_text = f"Writer: {', '.join(writers[:2])}"
                    draw.text((margin, current_y), w_text, font=credit_font, fill=(50,50,50))
                    current_y += 35
                if artists:
                    a_text = f"Artist: {', '.join(artists[:2])}"
                    draw.text((margin, current_y), a_text, font=credit_font, fill=(50,50,50))
                    current_y += 35

            current_y += 20

            # Description
            if issue.description:
                desc_clean = re.sub(r'<[^>]+>', '', issue.description)
                max_desc_h = canvas_h - current_y - margin - 50 # 50 for footer

                desc_font, wrapped_desc, _ = self._auto_scale_text(
                    desc_clean, DEFAULT_FONT_REGULAR, text_area_w, max_desc_h, start_size=32, min_size=18
                )
                draw.multiline_text((margin, current_y), wrapped_desc, font=desc_font, fill=text_color)

            # Footer
            if config.custom_footer_text:
                footer_font = self._get_font(DEFAULT_FONT_REGULAR, 16)
                draw.text((margin, canvas_h - margin - 20), config.custom_footer_text, font=footer_font, fill=(100,100,100))

            # Logo
            if config.logo_image_path and os.path.exists(config.logo_image_path):
                try:
                    with Image.open(config.logo_image_path) as logo:
                        if logo.mode != 'RGBA':
                            logo = logo.convert('RGBA')
                        # scale logo to max 100x100
                        logo.thumbnail((100, 100), self.resample_filter)
                        img.paste(logo, (margin, canvas_h - margin - logo.height), logo)
                except Exception as e:
                    logger.warning(f"Failed to apply logo: {e}")

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path, quality=90)
            return True

        except Exception as e:
            logger.error(f"Failed to generate social image: {e}")
            return False
