# -*- coding: utf-8 -*-
import os
import sys
import re
import textwrap
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from datetime import datetime
import logging

# === MODIFIED IMPORT: Use centralized utility and dataclass ===
from utils import (
    ComicRunConfig, 
    PlatformConfig,
    process_issues_for_platform,
)
# === END MODIFIED IMPORT ===

# === Get a logger for this module ===
logger = logging.getLogger(__name__)
# === END LOGGER INITIALIZATION ===

# --- Configuration for THIS PLATFORM (Facebook) ---
CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 630
CANVAS_BG_COLOR = (255, 255, 255)
MARGIN = 20
COVER_AREA_WIDTH = 450 # This defines the conceptual horizontal space the cover occupies
COVER_MAX_HEIGHT = CANVAS_HEIGHT - (MARGIN * 2)
TEXT_AREA_X_START = MARGIN
TEXT_AREA_WIDTH = CANVAS_WIDTH - COVER_AREA_WIDTH - (MARGIN * 2 + 5) 
DESCRIPTION_AREA_WIDTH = CANVAS_WIDTH - (MARGIN * 2)
TEXT_START_Y = 20
# MODIFIED: Reduce line spacing for metadata
LINE_SPACING_METADATA = 4 # Was 6
LINE_SPACING_DESC = 3
SPACING_AFTER_TITLE = 10 
# MODIFIED: Reduce spacing after metadata blocks
LINE_SPACING_BLOCK_AFTER = 20 # Was 30
FONT_PATH_REGULAR = r"C:\Windows\Fonts\verdana.ttf"
FONT_PATH_BOLD = r"C:\Windows\Fonts\verdanab.ttf"
FONT_PATH_DESC = r"C:\Windows\Fonts\verdana.ttf"
FONT_SIZE_TITLE = 35
FONT_SIZE_METADATA_LABEL = 29
FONT_SIZE_METADATA_VALUE = 29
FONT_SIZE_DESC_LABEL = 30
FONT_SIZE_DESC = 25
MIN_FONT_SIZE_DESC = 17
TEXT_COLOR_METADATA = (50, 50, 50)
TEXT_COLOR_DESC = (0, 0, 0)
SOCIAL_IMAGE_SAVE_QUALITY = 90
try: RESAMPLING_FILTER = Image.Resampling.LANCZOS
except AttributeError: RESAMPLING_FILTER = Image.LANCZOS

# <<< MODIFIED: Footer and Logo Configuration
FONT_SIZE_FOOTER = 14
FOOTER_TEXT_COLOR = (0, 0, 0)
FOOTER_MAX_CHARS = 50 
LOGO_SIZE = (50, 50)  
LOGO_FOOTER_GAP = 15   
# --- End Facebook Configuration ---

def get_user_input():
    print("-" * 30); print("Please provide the following details:"); print("-" * 30)
    while True:
        title = input("  Enter Comic Series Title: ").strip();
        if title: break
        else: print("    Error: Title cannot be empty.")
    while True:
        publisher = input("  Enter Publisher Name: ").strip();
        if publisher: break
        else: print("    Error: Publisher cannot be empty.")
    volume_number = input("  Enter Volume Number (OPTIONAL): ").strip()
    start_year = None
    while True:
        start_year_str = input(f"  Enter Start Year: ").strip()
        try:
            year_val = int(start_year_str)
            if 1800 < year_val < 2100:
                start_year = year_val; break
            else:
                print("    Error: Invalid year.")
        except ValueError:
            print("    Error: Invalid input.")
    end_year = None
    while True:
        end_year_str = input(f"  Enter End Year: ").strip()
        try:
            year_val = int(end_year_str)
            if 1800 < year_val < 2100:
                if year_val >= start_year:
                    end_year = year_val; break
                else:
                    print("    Error: End Year must be >= Start Year.")
            else:
                print("    Error: Invalid year.")
        except ValueError:
            print("    Error: Invalid input.")

    custom_footer_text = input(f"  Enter Custom Footer Text (OPTIONAL, max {FOOTER_MAX_CHARS} chars): ").strip()
    if custom_footer_text:
        custom_footer_text = custom_footer_text[:FOOTER_MAX_CHARS]
    
    logo_path = input(f"  Enter Path to Logo Image (OPTIONAL, e.g., C:\\path\\to\\logo.png): ").strip().strip('"')
    if logo_path and not os.path.isfile(logo_path):
        print(f"    Warning: Logo file '{logo_path}' not found. Will be ignored.")
        logo_path = None
    elif not logo_path:
        logo_path = None

    print("-" * 30); return title, publisher, volume_number, start_year, end_year, custom_footer_text, logo_path


def get_text_height_fb(draw_instance, text, font):
    if not text or not font : return 0
    try: bbox = draw_instance.textbbox((0,0),text,font=font,anchor='lt'); return bbox[3] - bbox[1]
    except AttributeError:
        try: return font.getsize(text)[1]
        except Exception: return 0
    except TypeError:
       logger.debug(f"get_text_height_fb TypeError for text: '{text}'")
       return 0

def get_text_width_fb(draw_instance, text, font):
    if not text or not font: return 0
    try: bbox = draw_instance.textbbox((0,0),text,font=font,anchor='lt'); return bbox[2] - bbox[0]
    except AttributeError:
        try: return font.getsize(text)[0]
        except Exception: return 0
    except TypeError:
       logger.debug(f"get_text_width_fb TypeError for text: '{text}'")
       return 0

def calculate_text_block_height_fb(draw_instance, text, font, line_spacing, narrow_width, wide_width, cover_cutoff_y, start_y):
    if not text: return 0
    words = str(text).split()
    if not words: return 0
    total_height = 0; curr_line = ""; current_line_start_y = start_y
    for w in words:
        current_wrap_width = narrow_width if current_line_start_y < cover_cutoff_y else wide_width
        test_line = curr_line + (" " if curr_line else "") + w
        line_w = get_text_width_fb(draw_instance, test_line, font)
        if line_w <= current_wrap_width:
            curr_line = test_line
        else:
            if curr_line:
                line_h = get_text_height_fb(draw_instance, curr_line, font)
                if line_h > 0: total_height += line_h + line_spacing; current_line_start_y += line_h + line_spacing
            current_wrap_width = narrow_width if current_line_start_y < cover_cutoff_y else wide_width
            if get_text_width_fb(draw_instance, w, font) > current_wrap_width:
                line_h = get_text_height_fb(draw_instance, w, font)
                if line_h > 0: total_height += line_h + line_spacing; current_line_start_y += line_h + line_spacing
                curr_line = ""
            else: curr_line = w
    if curr_line:
        line_h = get_text_height_fb(draw_instance, curr_line, font)
        if line_h > 0: total_height += line_h 
    return total_height

def create_social_image_facebook(config: ComicRunConfig, original_cover_path, issue_details, description_to_use, output_social_path):
    logger.info(f"Creating Facebook social media image: {os.path.basename(output_social_path)}...")
    try:
        canvas = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), CANVAS_BG_COLOR); draw = ImageDraw.Draw(canvas)
        font_desc_final = None; font_desc_label_final = None
        try: font_title = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_TITLE)
        except IOError: font_title = ImageFont.load_default(); logger.warning("Title font fail.")
        try: font_meta_label = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_METADATA_LABEL)
        except IOError: font_meta_label = ImageFont.load_default(); logger.warning("Meta label font fail.")
        try: font_meta_value = ImageFont.truetype(FONT_PATH_REGULAR, FONT_SIZE_METADATA_VALUE)
        except IOError: font_meta_value = ImageFont.load_default(); logger.warning("Meta value font fail.")
        try: font_desc_label_std = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_DESC_LABEL)
        except IOError: font_desc_label_std = ImageFont.load_default(); logger.warning("Desc label font fail.")
        try: font_desc_std = ImageFont.truetype(FONT_PATH_DESC, FONT_SIZE_DESC)
        except IOError: font_desc_std = ImageFont.load_default(); logger.warning("Desc font fail.")
        try: font_footer = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_FOOTER)
        except IOError: font_footer = ImageFont.load_default(); logger.warning("Footer font fail, using default.")


        cover_img = None; resized_width, resized_height = 0, 0; paste_x, paste_y = 0, 0; cover_bottom_y = MARGIN
        try:
            if os.path.exists(original_cover_path):
                cover_img = Image.open(original_cover_path)
                cover_fit_width = COVER_AREA_WIDTH; cover_fit_height = COVER_MAX_HEIGHT
                cover_img.thumbnail((cover_fit_width, cover_fit_height), RESAMPLING_FILTER)
                resized_width, resized_height = cover_img.size; paste_x = CANVAS_WIDTH - MARGIN - resized_width; paste_y = MARGIN + (COVER_MAX_HEIGHT - resized_height) // 2; cover_bottom_y = paste_y + resized_height
                logger.debug(f"Cover Resized: {resized_width}x{resized_height}"); logger.debug(f"Cover Paste Coords (Vert Centered): X={paste_x}, Y={paste_y}, Bottom Y={cover_bottom_y}")
                try:
                    if cover_img.mode == 'RGBA': canvas.paste(cover_img, (paste_x, paste_y), cover_img)
                    elif cover_img.mode == 'P' and 'transparency' in cover_img.info: canvas.paste(cover_img.convert('RGBA'), (paste_x, paste_y), cover_img.convert('RGBA'))
                    else: canvas.paste(cover_img.convert('RGB'), (paste_x, paste_y))
                except Exception as paste_err: logger.error(f"Error pasting cover image: {paste_err}"); cover_img = None
            else:
                logger.debug(f"Original cover file not found: '{original_cover_path}'."); cover_bottom_y = MARGIN
        except (FileNotFoundError, UnidentifiedImageError, Exception) as img_err: logger.error(f"Error loading/resizing cover '{original_cover_path}': {img_err}."); cover_img = None; cover_bottom_y = MARGIN

        title_text=issue_details.get('volume',{}).get('name','?'); issue_num_val=issue_details.get('issue_number','?');
        cover_date_str=issue_details.get('cover_date',''); formatted_cover_date="N/A";
        if cover_date_str:
            try: dt_obj=datetime.strptime(cover_date_str,'%Y-%m-%d'); formatted_cover_date=dt_obj.strftime('%B %d, %Y')
            except ValueError:
                 try: dt_obj=datetime.strptime(cover_date_str,'%Y-%m'); formatted_cover_date=dt_obj.strftime('%B %Y')
                 except ValueError:
                      try: dt_obj=datetime.strptime(cover_date_str,'%Y'); formatted_cover_date=dt_obj.strftime('%Y')
                      except ValueError: formatted_cover_date=cover_date_str or "N/A"

        person_credits=issue_details.get('person_credits',[])
        inkers_cv, colorists_cv, letterers_cv = set(), set(), set()
        if isinstance(person_credits, list):
            for person in person_credits:
                if isinstance(person, dict) and person.get('name'):
                    name=person.get('name'); roles_raw=person.get('role','').lower()
                    if 'inker' in roles_raw or 'inks' in roles_raw: inkers_cv.add(name)
                    if 'colorist' in roles_raw or 'colors' in roles_raw: colorists_cv.add(name)
                    if 'letterer' in roles_raw or 'letters' in roles_raw: letterers_cv.add(name)

        inker_text=", ".join(sorted(list(inkers_cv))) or "N/A"
        colorist_text=", ".join(sorted(list(colorists_cv))) or "N/A"
        letterer_text=", ".join(sorted(list(letterers_cv))) or "N/A"

        def _draw_left_aligned_label_single_value(label_text, value_text, y_pos, font_label, font_value, line_spacing_after_value, max_y=CANVAS_HEIGHT):
            nonlocal draw; empty_values = {"N/A", "?", "Unknown Date", "", "None", None}; label_h = get_text_height_fb(draw, label_text, font_label); value_h = get_text_height_fb(draw, value_text, font_value)
            if value_text in empty_values or value_text is None: return y_pos
            total_h = label_h + (LINE_SPACING_METADATA // 2) + value_h
            if y_pos + total_h > max_y - MARGIN:
                logger.debug(f"Skipping draw '{label_text}' (single val) - hit max_y boundary (Y={y_pos}, TotalH={total_h}, MaxY={max_y - MARGIN}).")
                return y_pos
            draw.text((TEXT_AREA_X_START, y_pos), label_text, font=font_label, fill=TEXT_COLOR_METADATA, anchor='lt'); y_after_label = y_pos + label_h + LINE_SPACING_METADATA // 2
            draw.text((TEXT_AREA_X_START, y_after_label), value_text, font=font_value, fill=TEXT_COLOR_METADATA, anchor='lt'); return y_after_label + value_h + line_spacing_after_value

        def _draw_label_followed_by_wrapped_value(label_text, value_text, y_pos, font_label, font_value, line_spacing_value, section_spacing_after, start_x, wrap_width, text_color=TEXT_COLOR_METADATA, max_y=CANVAS_HEIGHT):
            nonlocal draw; empty_values = {"N/A", "?", "", "Unknown Publisher", "None", None}; label_colon = f"{label_text}:"; label_h = get_text_height_fb(draw, label_colon, font_label)
            if value_text in empty_values or not value_text: return y_pos
            if y_pos + label_h > max_y - MARGIN:
                logger.debug(f"Stopping draw '{label_text}' - label doesn't fit within max_y (Y={y_pos}, LabelH={label_h}, MaxY={max_y - MARGIN}).")
                return y_pos
            draw.text((start_x, y_pos), label_colon, font=font_label, fill=text_color, anchor='lt'); y_after_label = y_pos + label_h + LINE_SPACING_METADATA // 2
            words = str(value_text).split(); lines = []; curr_line = ""
            if not words and value_text: words = [value_text]
            if not words: return y_after_label + section_spacing_after
            for w in words:
                test_line = curr_line + (" " if curr_line else "") + w; line_w = get_text_width_fb(draw, test_line, font_value)
                if line_w <= wrap_width: curr_line = test_line
                else:
                    if curr_line: lines.append(curr_line)
                    if get_text_width_fb(draw, w, font_value) > wrap_width:
                        logger.debug(f"Word '{w[:20]}...' exceeds wrap width {wrap_width}. Adding as single line.")
                        lines.append(w); curr_line = ""
                    else: curr_line = w
            if curr_line: lines.append(curr_line)
            if not lines and value_text: lines.append(value_text)

            curr_y = y_after_label; lines_drawn = 0
            for i, line in enumerate(lines):
                line_h = get_text_height_fb(draw, line, font_value);
                if line_h == 0: continue
                if curr_y + line_h > max_y - MARGIN:
                    logger.debug(f"Stopping draw '{label_text}' value - hit max_y boundary at line {i+1}/{len(lines)} (Y={curr_y}, LineH={line_h}, MaxY={max_y - MARGIN}).")
                    break
                draw.text((start_x, curr_y), line, font=font_value, fill=text_color, anchor='lt'); curr_y += line_h + line_spacing_value; lines_drawn += 1
            if lines_drawn == 0 and len(lines) > 0 : return y_pos + label_h + section_spacing_after
            elif lines_drawn == 0: return y_pos
            else: return curr_y - line_spacing_value + section_spacing_after

        def _draw_dynamic_width_description(label_text, value_text, y_pos, font_label, font_value, line_spacing_value, section_spacing_after, narrow_width, wide_width, cover_cutoff_y, max_y=CANVAS_HEIGHT):
            nonlocal draw; empty_values = {"N/A", "", "No description available.", "None", None}; label_colon = f"{label_text}:"; label_h = get_text_height_fb(draw, label_colon, font_label)
            if value_text in empty_values or not value_text: return y_pos
            if y_pos + label_h > max_y - MARGIN:
                logger.debug(f"Skipping dynamic description - Label doesn't fit (Y={y_pos}, LabelH={label_h}, Max={max_y - MARGIN}).")
                return y_pos
            draw.text((MARGIN, y_pos), label_colon, font=font_label, fill=TEXT_COLOR_DESC, anchor='lt'); y_after_label = y_pos + label_h + LINE_SPACING_METADATA // 2
            words = str(value_text).split(); lines = []; curr_line = ""; current_line_start_y = y_after_label
            if not words: return y_after_label + section_spacing_after
            
            # MODIFIED: Increased max_lines_for_desc
            max_lines_for_desc = 12 

            for w in words:
                current_wrap_width = narrow_width if current_line_start_y < cover_cutoff_y else wide_width; test_line = curr_line + (" " if curr_line else "") + w; line_w = get_text_width_fb(draw, test_line, font_value)
                if line_w <= current_wrap_width: curr_line = test_line
                else:
                    if curr_line: line_h_calc = get_text_height_fb(draw, curr_line, font_value); lines.append(curr_line); current_line_start_y += line_h_calc + line_spacing_value
                    current_wrap_width = narrow_width if current_line_start_y < cover_cutoff_y else wide_width
                    if get_text_width_fb(draw, w, font_value) > current_wrap_width:
                        logger.debug(f"Dynamic Desc: Word '{w[:20]}...' exceeds wrap width {current_wrap_width}. Adding as single line.")
                        lines.append(w); line_h_calc = get_text_height_fb(draw, w, font_value); current_line_start_y += line_h_calc + line_spacing_value; curr_line = ""
                    else: curr_line = w
            if curr_line: lines.append(curr_line)
            curr_y = y_after_label; lines_drawn = 0
            for i, line in enumerate(lines):
                if lines_drawn >= max_lines_for_desc:
                     logger.debug(f"Stopping dynamic description draw - hit max_lines_for_desc ({max_lines_for_desc}).")
                     break
                line_h = get_text_height_fb(draw, line, font_value);
                if line_h == 0: continue
                if curr_y + line_h > max_y - MARGIN : 
                    footer_height_estimate = FONT_SIZE_FOOTER + MARGIN 
                    if config.custom_footer_text or config.logo_image_path:
                        if curr_y + line_h > max_y - MARGIN - footer_height_estimate:
                            logger.debug(f"Stopping dynamic description draw - hit max_y (considering footer) boundary at line {i+1}/{len(lines)}.")
                            break
                    else:
                        logger.debug(f"Stopping dynamic description draw - hit max_y boundary at line {i+1}/{len(lines)}.")
                        break
                draw.text((MARGIN, curr_y), line, font=font_value, fill=TEXT_COLOR_DESC, anchor='lt'); curr_y += line_h + line_spacing_value; lines_drawn += 1

            if lines_drawn == 0 and len(lines)>0 : return y_pos + label_h + section_spacing_after
            elif lines_drawn == 0: return y_pos
            else: return curr_y - line_spacing_value + section_spacing_after

        current_y = TEXT_START_Y; title_full = f"{title_text} #{issue_num_val}"; title_char_width_approx = FONT_SIZE_TITLE * 0.5; title_wrap_chars = int(TEXT_AREA_WIDTH / title_char_width_approx) if title_char_width_approx > 0 else 50; title_lines = textwrap.wrap(title_full, width=title_wrap_chars); title_drawn_height = 0
        logger.debug(f"Title wrap width chars: {title_wrap_chars} for text area width {TEXT_AREA_WIDTH}")
        for line in title_lines:
             line_h = get_text_height_fb(draw, line, font_title)
             if current_y + line_h > CANVAS_HEIGHT - MARGIN:
                 logger.debug(f"Stopping title draw - hit max_y boundary.")
                 break
             draw.text((TEXT_AREA_X_START, current_y), line, font=font_title, fill=TEXT_COLOR_METADATA, anchor='lt'); current_y += line_h + LINE_SPACING_METADATA // 2; title_drawn_height += line_h + LINE_SPACING_METADATA //2
        if title_drawn_height > 0: current_y += SPACING_AFTER_TITLE - (LINE_SPACING_METADATA // 2)
        else: current_y = TEXT_START_Y

        metadata_max_y = CANVAS_HEIGHT - MARGIN
        logger.debug(f"Drawing Metadata Start Y: {current_y}")
        current_y = _draw_left_aligned_label_single_value("Cover Date:", formatted_cover_date, current_y, font_meta_label, font_meta_value, LINE_SPACING_BLOCK_AFTER, max_y=metadata_max_y)
        
        if inker_text not in {"N/A", "?", None, ""} : 
            current_y = _draw_label_followed_by_wrapped_value("Inker(s)", inker_text, current_y, font_meta_label, font_meta_value, LINE_SPACING_METADATA, LINE_SPACING_BLOCK_AFTER, start_x=TEXT_AREA_X_START, wrap_width=TEXT_AREA_WIDTH, max_y=metadata_max_y)
        if colorist_text not in {"N/A", "?", None, ""}: 
            current_y = _draw_label_followed_by_wrapped_value("Colorist(s)", colorist_text, current_y, font_meta_label, font_meta_value, LINE_SPACING_METADATA, LINE_SPACING_BLOCK_AFTER, start_x=TEXT_AREA_X_START, wrap_width=TEXT_AREA_WIDTH, max_y=metadata_max_y)
        if letterer_text not in {"N/A", "?", None, ""}: 
            current_y = _draw_label_followed_by_wrapped_value("Letterer(s)", letterer_text, current_y, font_meta_label, font_meta_value, LINE_SPACING_METADATA, LINE_SPACING_BLOCK_AFTER, start_x=TEXT_AREA_X_START, wrap_width=TEXT_AREA_WIDTH, max_y=metadata_max_y)

        left_block_bottom_y = current_y; description_start_y = left_block_bottom_y
        logger.debug(f"Left Block Bottom Y (Next Draw Pos): {left_block_bottom_y}"); logger.debug(f"Cover Bottom Y (Actual Bottom Pixel): {cover_bottom_y}"); logger.debug(f"Description Start Y Candidate: {description_start_y}")

        final_font_desc = font_desc_std; font_desc_label_final = font_desc_label_std; description_drawn_successfully = False; placeholder_texts = {"No description available.", "", "N/A", None}
        
        footer_height_reservation = 0
        if config.custom_footer_text or config.logo_image_path:
            footer_height_reservation = FONT_SIZE_FOOTER + MARGIN + 5 

        if description_to_use and description_to_use not in placeholder_texts:
            available_height = CANVAS_HEIGHT - MARGIN - footer_height_reservation - description_start_y
            desc_label_h_calc = get_text_height_fb(draw, "Description:", font_desc_label_final);
            available_height_for_text = available_height - (desc_label_h_calc + (LINE_SPACING_METADATA // 2))
            if available_height_for_text > 10: 
                current_font_size = FONT_SIZE_DESC; temp_font_desc = None
                best_fitting_font = font_desc_std

                while current_font_size >= MIN_FONT_SIZE_DESC:
                    try: temp_font_desc = ImageFont.truetype(FONT_PATH_DESC, current_font_size)
                    except IOError:
                        logger.warning(f"Could not load description font size {current_font_size}. Skipping size.")
                        if current_font_size == FONT_SIZE_DESC: best_fitting_font = ImageFont.load_default()
                        current_font_size -=1; continue

                    required_height = calculate_text_block_height_fb(draw, description_to_use, temp_font_desc, LINE_SPACING_DESC, TEXT_AREA_WIDTH, DESCRIPTION_AREA_WIDTH, cover_bottom_y, description_start_y + desc_label_h_calc + (LINE_SPACING_METADATA // 2))
                    logger.debug(f"Font Size {current_font_size}: Required Height = {required_height}, Available Height for text = {available_height_for_text}")

                    if required_height <= available_height_for_text:
                        best_fitting_font = temp_font_desc
                        description_drawn_successfully = True
                        logger.debug(f"Description fits with font size {current_font_size}.")
                        break
                    else: best_fitting_font = temp_font_desc 
                    current_font_size -= 1
                
                final_font_desc = best_fitting_font
                if not description_drawn_successfully and final_font_desc: 
                    logger.warning(f"Description may be truncated. Using smallest attempted font size {final_font_desc.size if hasattr(final_font_desc, 'size') else 'default'}.")
                    description_drawn_successfully = True 
                elif not final_font_desc: 
                     logger.error("Failed to load any description font.")
                     description_drawn_successfully = False
            else:
                 logger.debug(f"Insufficient space for description label & text (Available: {available_height_for_text}, considering footer: {footer_height_reservation}). Skipping."); description_drawn_successfully = False

        description_content_end_y = current_y 
        if description_drawn_successfully and final_font_desc:
             max_y_for_desc_draw = CANVAS_HEIGHT - footer_height_reservation 
             description_content_end_y = _draw_dynamic_width_description(label_text="Description", value_text=description_to_use, y_pos=description_start_y, font_label=font_desc_label_final, font_value=final_font_desc, line_spacing_value=LINE_SPACING_DESC, section_spacing_after=0, narrow_width=TEXT_AREA_WIDTH, wide_width=DESCRIPTION_AREA_WIDTH, cover_cutoff_y=cover_bottom_y, max_y=max_y_for_desc_draw) 
             logger.debug(f"Dynamic Description finished at Y: {description_content_end_y} using font size {final_font_desc.size if hasattr(final_font_desc, 'size') else 'default'}")
        elif description_to_use and description_to_use not in placeholder_texts:
             if description_start_y < CANVAS_HEIGHT - MARGIN - footer_height_reservation - get_text_height_fb(draw, "D", font_desc_label_std):
                 draw.text((MARGIN, description_start_y), "Description:", font=font_desc_label_std, fill=TEXT_COLOR_DESC, anchor='lt')
                 description_content_end_y = description_start_y + get_text_height_fb(draw, "Description:", font_desc_label_std)
                 logger.debug("Drew description label only, as text did not fit or font failed.")
             else:
                 logger.debug("Skipped description entirely as even the label did not fit before footer.")
                 description_content_end_y = description_start_y


        # --- Footer and Logo Drawing (MODIFIED for Facebook) ---
        logo_img_resized = None
        logo_w_actual = 0
        logo_h_actual = 0
        if config.logo_image_path:
            try:
                logo_img_opened = Image.open(config.logo_image_path)
                logo_img_resized = logo_img_opened.resize(LOGO_SIZE, RESAMPLING_FILTER)
                logo_w_actual = LOGO_SIZE[0]
                logo_h_actual = LOGO_SIZE[1]
                logger.debug(f"FB: Loaded and resized logo: {config.logo_image_path}")
            except Exception as e:
                logger.warning(f"FB: Could not load/resize logo '{config.logo_image_path}': {e}")
                logo_img_resized = None
        
        footer_text_to_draw = None
        footer_w_actual = 0
        footer_h_actual = 0
        if config.custom_footer_text:
            footer_text_to_draw = config.custom_footer_text
            footer_w_actual = get_text_width_fb(draw, footer_text_to_draw, font_footer)
            footer_h_actual = get_text_height_fb(draw, footer_text_to_draw, font_footer)

        max_element_height = max(footer_h_actual, logo_h_actual)

        if max_element_height > 0:
            footer_area_top_y = CANVAS_HEIGHT - MARGIN - max_element_height
            min_gap_to_content = 5 
            if footer_area_top_y < description_content_end_y + min_gap_to_content:
                logger.warning(f"FB: Footer area (top y: {footer_area_top_y}) would overlap content (bottom y: {description_content_end_y}). Skipping footer/logo.")
            else:
                current_x_pos_footer = MARGIN
                drawn_something_in_footer = False

                if footer_text_to_draw:
                    if current_x_pos_footer + footer_w_actual <= CANVAS_WIDTH - MARGIN: 
                        text_y_offset = (max_element_height - footer_h_actual) // 2
                        text_y_pos = footer_area_top_y + text_y_offset
                        draw.text((current_x_pos_footer, text_y_pos), footer_text_to_draw, font=font_footer, fill=FOOTER_TEXT_COLOR, anchor='lt')
                        logger.debug(f"FB: Drew footer text '{footer_text_to_draw}' at ({current_x_pos_footer}, {text_y_pos})")
                        current_x_pos_footer += footer_w_actual
                        drawn_something_in_footer = True
                    else:
                        logger.warning(f"FB: Footer text '{footer_text_to_draw}' too wide. Skipping.")
                
                if logo_img_resized:
                    if drawn_something_in_footer:
                        current_x_pos_footer += LOGO_FOOTER_GAP
                    
                    if current_x_pos_footer + logo_w_actual <= CANVAS_WIDTH - MARGIN: 
                        logo_y_offset = (max_element_height - logo_h_actual) // 2
                        logo_y_pos = footer_area_top_y + logo_y_offset
                        
                        paste_alpha_mask = None
                        final_logo_img_to_paste = logo_img_resized
                        if logo_img_resized.mode == 'RGBA':
                            paste_alpha_mask = logo_img_resized
                        elif logo_img_resized.mode == 'P' and 'transparency' in logo_img_resized.info:
                            final_logo_img_to_paste = logo_img_resized.convert('RGBA')
                            paste_alpha_mask = final_logo_img_to_paste
                        
                        canvas.paste(final_logo_img_to_paste, (current_x_pos_footer, logo_y_pos), paste_alpha_mask)
                        logger.debug(f"FB: Pasted logo at ({current_x_pos_footer}, {logo_y_pos})")
                    else:
                        logger.warning(f"FB: Logo too wide to fit. Skipping logo.")
        # --- End Footer and Logo Drawing ---

        output_dir = os.path.dirname(output_social_path)
        if not os.path.exists(output_dir): os.makedirs(output_dir, exist_ok=True)
        canvas.save(output_social_path, quality=SOCIAL_IMAGE_SAVE_QUALITY)
        if not os.path.exists(output_social_path) or os.path.getsize(output_social_path) == 0: logger.error(f"Img missing/empty: '{os.path.basename(output_social_path)}'"); return False
        logger.info(f"OK: {os.path.basename(output_social_path)}"); return True
    except Exception as e:
        logger.error(f"ERROR creating image for {os.path.basename(original_cover_path)}: {e}", exc_info=True)
        return False

def process_and_generate(run_config: ComicRunConfig, issues_data_for_platform: list):
    fb_platform_config = PlatformConfig(
        name="Facebook",
        directory_prefix="fb",
        social_post_filename_prefix="fb",
        social_post_filename_suffix="_post_1200x630.jpg",
        description_word_limit=100, # MODIFIED: Harmonized with main_runner.py
        create_social_image_func=create_social_image_facebook
    )
    process_issues_for_platform(run_config, fb_platform_config, issues_data_for_platform)

if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    standalone_logger = logging.getLogger(__name__ + ".standalone")
    standalone_logger.info("--- Comic Vine Social Image Creator (Facebook - Standalone Run) ---")
    comic_vine_api_key_local=None; mistral_api_key_local=None
    FALLBACK_API_KEY_FILENAME_LOCAL = r"C:\script\api_key.txt"
    FALLBACK_MISTRAL_API_KEY_FILENAME_LOCAL = r"C:\script\mistral_api_key.txt"

    standalone_logger.info("Standalone: Attempting to load API keys...")
    comic_vine_api_key_local = os.environ.get('COMIC_VINE_API_KEY')
    if comic_vine_api_key_local:
        standalone_logger.info("Standalone: Comic Vine Key Loaded from COMIC_VINE_API_KEY environment variable.")
    else:
        standalone_logger.info("Standalone: COMIC_VINE_API_KEY env var not found. Trying file fallback.")
        try:
            with open(FALLBACK_API_KEY_FILENAME_LOCAL,'r',encoding='utf-8') as f:
                comic_vine_api_key_local=f.readline().strip()
            if not comic_vine_api_key_local:
                standalone_logger.warning(f"Standalone: Comic Vine API key file '{FALLBACK_API_KEY_FILENAME_LOCAL}' is empty.")
                comic_vine_api_key_local = None
            else:
                standalone_logger.info(f"Standalone: Comic Vine Key Loaded from file '{FALLBACK_API_KEY_FILENAME_LOCAL}'.")
        except FileNotFoundError:
            standalone_logger.warning(f"Standalone: Comic Vine API key file not found at '{FALLBACK_API_KEY_FILENAME_LOCAL}'.")
        except Exception as e:
            standalone_logger.error(f"Standalone: Error loading Comic Vine API key from file: {e}", exc_info=True)
            comic_vine_api_key_local = None

    if not comic_vine_api_key_local:
        standalone_logger.critical("Standalone: Comic Vine API Key is essential and could not be loaded. Exiting.")
        sys.exit(1)

    mistral_api_key_local = os.environ.get('MISTRAL_API_KEY')
    if mistral_api_key_local:
        standalone_logger.info("Standalone: Mistral API Key loaded from MISTRAL_API_KEY environment variable.")
    else:
        standalone_logger.info("Standalone: MISTRAL_API_KEY env var not found. Trying file fallback.")
        try:
            if os.path.exists(FALLBACK_MISTRAL_API_KEY_FILENAME_LOCAL):
                with open(FALLBACK_MISTRAL_API_KEY_FILENAME_LOCAL,'r',encoding='utf-8') as f:
                    mistral_api_key_local=f.readline().strip()
                if not mistral_api_key_local:
                    standalone_logger.warning(f"Standalone: Mistral key file '{FALLBACK_MISTRAL_API_KEY_FILENAME_LOCAL}' found but is empty.")
                    mistral_api_key_local = None
                else:
                    standalone_logger.info(f"Standalone: Mistral API Key loaded from file '{FALLBACK_MISTRAL_API_KEY_FILENAME_LOCAL}'.")
            else:
                 standalone_logger.warning(f"Standalone: Mistral key file not found at '{FALLBACK_MISTRAL_API_KEY_FILENAME_LOCAL}'.")
        except Exception as e:
            standalone_logger.error(f"Standalone: Error reading Mistral key file: {e}.", exc_info=True)
            mistral_api_key_local = None

    if not mistral_api_key_local:
        standalone_logger.warning("Standalone: Mistral API Key not loaded. AI features may be limited.")

    title_local,publisher_local,volume_number_local,start_year_local,end_year_local, footer_text_local, logo_path_local =get_user_input() 

    try:
        from utils import find_volume_id as find_volume_id_standalone
        from utils import get_filtered_issue_details as get_filtered_issues_standalone
        from utils import query_mistral_for_role_util as query_ai_role_standalone
    except ModuleNotFoundError:
        standalone_logger.critical("utils.py or its functions not found. It's needed for standalone execution.")
        sys.exit(1)

    standalone_logger.info("--- Standalone: Locating Volume ID ---")
    volume_id_local = find_volume_id_standalone(comic_vine_api_key_local, title_local, publisher_local, volume_number_local, start_year_local)
    if not volume_id_local:
        standalone_logger.critical("!!! Standalone ERROR: Could not determine Volume ID. Exiting. !!!")
        sys.exit(1)
    else:
        standalone_logger.info(f"--- Standalone: Using Volume ID: {volume_id_local} ---")

    standalone_run_config = ComicRunConfig(
        comic_vine_api_key=comic_vine_api_key_local,
        mistral_api_key=mistral_api_key_local,
        title=title_local,
        publisher=publisher_local,
        volume_number=volume_number_local if volume_number_local else "",
        start_year=start_year_local,
        end_year=end_year_local,
        volume_id=str(volume_id_local),
        custom_footer_text=footer_text_local,
        logo_image_path=logo_path_local
    )

    start_date_str_local = f"{standalone_run_config.start_year}-01-01"
    end_date_str_local = f"{standalone_run_config.end_year}-12-31"
    issues_data_local = get_filtered_issues_standalone(
        standalone_run_config.comic_vine_api_key,
        standalone_run_config.volume_id,
        start_date_str_local,
        end_date_str_local
    )
    if mistral_api_key_local and issues_data_local:
        standalone_logger.info(f"--- Standalone: Pre-fetching AI roles for {len(issues_data_local)} issues ---")
        for issue_item in issues_data_local:
            vol_name_ai_local = issue_item.get('volume', {}).get('name', '?')
            iss_num_ai_local = issue_item.get('issue_number', '?')
            cov_date_ai_local = issue_item.get('cover_date', '?')
            roles_map_local = {} 
            for key_suffix, query_text in roles_map_local.items():
                ai_name = query_ai_role_standalone(mistral_api_key_local, vol_name_ai_local, iss_num_ai_local, cov_date_ai_local, query_text, key_suffix)
                if ai_name: issue_item[f'ai_{key_suffix}'] = ai_name
        standalone_logger.info("--- Standalone: AI Role Pre-fetching Complete ---")

    process_and_generate(standalone_run_config, issues_data_local)

    standalone_logger.info("--- Facebook Standalone Script Finished ---")