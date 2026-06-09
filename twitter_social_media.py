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


# --- Configuration for THIS PLATFORM (Twitter) ---
CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 900
CANVAS_BG_COLOR = (255, 255, 255)
MARGIN = 20
COVER_AREA_WIDTH = 600 
COVER_MAX_HEIGHT = CANVAS_HEIGHT - (MARGIN * 2)
TEXT_AREA_X_START = MARGIN
TEXT_AREA_WIDTH = CANVAS_WIDTH - COVER_AREA_WIDTH - (MARGIN * 2 + 10) 

COLUMN_GUTTER = 20
TEXT_AREA_X_START_COL1 = TEXT_AREA_X_START
COLUMN_WIDTH = (TEXT_AREA_WIDTH - COLUMN_GUTTER) // 2
TEXT_AREA_X_START_COL2 = TEXT_AREA_X_START_COL1 + COLUMN_WIDTH + COLUMN_GUTTER

DESCRIPTION_AREA_WIDTH = CANVAS_WIDTH - (MARGIN * 2)
TEXT_START_Y = MARGIN + 8
# MODIFIED: Reduce line spacing for metadata
LINE_SPACING_METADATA = 8 # Was 11
LINE_SPACING_DESC = 9
# MODIFIED: Reduce spacing after metadata blocks
LINE_SPACING_BLOCK_AFTER = 20 # Was 30, previously 50
FONT_PATH_REGULAR = r"C:\Windows\Fonts\verdana.ttf"
FONT_PATH_BOLD = r"C:\Windows\Fonts\verdanab.ttf"
FONT_PATH_ITALIC = r"C:\Windows\Fonts\verdanai.ttf"
FONT_PATH_DESC = r"C:\Windows\Fonts\verdana.ttf"
FONT_SIZE_TITLE = 41
FONT_SIZE_METADATA_LABEL = 32
FONT_SIZE_METADATA_VALUE = 32
FONT_SIZE_DESC_LABEL = 45
FONT_SIZE_DESC = 35
TWITTER_MIN_FONT_SIZE_DESC = 17
TARGET_EXPANDED_LINE_SPACING_DESC = LINE_SPACING_DESC + 2
DESCRIPTION_FILL_THRESHOLD = 0.70

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

# MODIFICATION: Increased wrap safety margin
WRAP_SAFETY_MARGIN = 8 # Pixels to subtract from wrap width for safety
# --- End Twitter Configuration ---

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
            if 1800 < year_val < 2100: start_year = year_val; break
            else: print("    Error: Invalid year.")
        except ValueError: print("    Error: Invalid input.")
    end_year = None
    while True:
        end_year_str = input(f"  Enter End Year: ").strip()
        try:
            year_val = int(end_year_str)
            if 1800 < year_val < 2100:
                if year_val >= start_year: end_year = year_val; break
                else: print("    Error: End Year must be >= Start Year.")
            else: print("    Error: Invalid year.")
        except ValueError: print("    Error: Invalid input.")

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


def get_text_height_twitter(draw_instance, text, font):
    if not text or not font : return 0
    try: bbox = draw_instance.textbbox((0,0),text,font=font,anchor='lt'); return bbox[3] - bbox[1]
    except AttributeError:
        try: return font.getsize(text)[1]
        except Exception: return 0
    except TypeError:
       logger.debug(f"get_text_height_twitter TypeError for text: '{text}'")
       return 0

def get_text_width_twitter(draw_instance, text, font):
    if not text or not font: return 0
    try: bbox = draw_instance.textbbox((0,0),text,font=font,anchor='lt'); return bbox[2] - bbox[0]
    except AttributeError:
        try: return font.getsize(text)[0]
        except Exception: return 0
    except TypeError:
       logger.debug(f"get_text_width_twitter TypeError for text: '{text}'")
       return 0

def calculate_text_block_height_twitter(draw_instance, text, font, line_spacing, narrow_width, wide_width, cover_cutoff_y, start_y_for_calc):
    if not text: return 0
    words = str(text).split()
    if not words: return 0
    total_height = 0
    current_line_text = ""
    current_line_y_offset = 0
    for word in words:
        actual_current_line_y = start_y_for_calc + current_line_y_offset
        current_wrap_width = narrow_width if actual_current_line_y < cover_cutoff_y else wide_width
        test_line = current_line_text + (" " if current_line_text else "") + word
        line_w = get_text_width_twitter(draw_instance, test_line, font)
        
        if line_w <= (current_wrap_width - WRAP_SAFETY_MARGIN):
            current_line_text = test_line
        else:
            if current_line_text:
                line_h = get_text_height_twitter(draw_instance, current_line_text, font)
                if line_h > 0:
                    total_height += line_h + line_spacing
                    current_line_y_offset += line_h + line_spacing
            
            current_wrap_width_for_word = narrow_width if (start_y_for_calc + current_line_y_offset) < cover_cutoff_y else wide_width
            if get_text_width_twitter(draw_instance, word, font) > (current_wrap_width_for_word - WRAP_SAFETY_MARGIN):
                line_h = get_text_height_twitter(draw_instance, word, font)
                if line_h > 0:
                    total_height += line_h + line_spacing
                    current_line_y_offset += line_h + line_spacing
                current_line_text = ""
            else:
                current_line_text = word
    if current_line_text:
        line_h = get_text_height_twitter(draw_instance, current_line_text, font)
        if line_h > 0: total_height += line_h
    return total_height

def _draw_left_aligned_label_single_value(draw_instance, label_text, value_text, x_pos, y_pos, font_label, font_value, line_spacing_after_value, max_y=CANVAS_HEIGHT, col_width=COLUMN_WIDTH):
    empty_values = {"N/A", "?", "Unknown Date", "", "None", None}
    if value_text in empty_values or value_text is None: return y_pos, 0
    label_h = get_text_height_twitter(draw_instance, label_text, font_label)
    wrapped_value_lines = []
    current_line = ""
    words = str(value_text).split()
    if not words and value_text: words = [value_text]

    if not words: value_h_total = 0
    else:
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if get_text_width_twitter(draw_instance, test_line, font_value) <= (col_width - WRAP_SAFETY_MARGIN):
                current_line = test_line
            else:
                if current_line: wrapped_value_lines.append(current_line)
                if get_text_width_twitter(draw_instance, word, font_value) > (col_width - WRAP_SAFETY_MARGIN): 
                    wrapped_value_lines.append(word) 
                    current_line = ""
                else:
                    current_line = word

        if current_line: wrapped_value_lines.append(current_line)
        if not wrapped_value_lines and value_text:
             wrapped_value_lines.append(value_text)

    value_h_total = 0
    if wrapped_value_lines:
        for i, line in enumerate(wrapped_value_lines):
            value_h_total += get_text_height_twitter(draw_instance, line, font_value)
            if i < len(wrapped_value_lines) - 1:
                 value_h_total += LINE_SPACING_METADATA // 2
    total_item_height = label_h + (LINE_SPACING_METADATA // 2) + value_h_total
    if y_pos + total_item_height > max_y - MARGIN:
        logger.debug(f"Skipping draw '{label_text}' (single val) for column - hit max_y boundary (Y={y_pos}, ItemH={total_item_height}, MaxY={max_y - MARGIN}).")
        return y_pos, 0
    draw_instance.text((x_pos, y_pos), label_text, font=font_label, fill=TEXT_COLOR_METADATA, anchor='lt')
    y_after_label = y_pos + label_h + LINE_SPACING_METADATA // 2
    current_line_y = y_after_label
    for i, line in enumerate(wrapped_value_lines):
        draw_instance.text((x_pos, current_line_y), line, font=font_value, fill=TEXT_COLOR_METADATA, anchor='lt')
        current_line_y += get_text_height_twitter(draw_instance, line, font_value)
        if i < len(wrapped_value_lines) -1:
            current_line_y += LINE_SPACING_METADATA // 2
    final_y_for_next_item = y_pos + total_item_height
    return final_y_for_next_item, total_item_height

def _draw_label_followed_by_wrapped_value(draw_instance, label_text, value_text, y_pos, font_label, font_value, line_spacing_value, section_spacing_after, start_x, wrap_width, text_color=TEXT_COLOR_METADATA, max_y=CANVAS_HEIGHT):
    empty_values = {"N/A", "?", "", "Unknown Publisher", "None", None}
    if value_text in empty_values or not value_text: return y_pos, 0

    label_colon = f"{label_text}:"
    label_h = get_text_height_twitter(draw_instance, label_colon, font_label)
    item_start_y = y_pos

    if y_pos + label_h > max_y - MARGIN:
        logger.debug(f"Stopping draw '{label_text}' - label doesn't fit (Y={y_pos}, LabelH={label_h}, MaxY={max_y - MARGIN}).")
        return y_pos, 0

    draw_instance.text((start_x, y_pos), label_colon, font=font_label, fill=text_color, anchor='lt')
    y_after_label = y_pos + label_h + LINE_SPACING_METADATA // 2
    words = str(value_text).split(); lines = []; curr_line = ""

    if not words and value_text: words = [value_text]

    if not words:
        total_item_height_only_label = label_h
        return item_start_y + total_item_height_only_label, total_item_height_only_label

    for w in words:
        test_line = curr_line + (" " if curr_line else "") + w
        line_w = get_text_width_twitter(draw_instance, test_line, font_value)
        if line_w <= (wrap_width - WRAP_SAFETY_MARGIN):
            curr_line = test_line
        else:
            if curr_line: lines.append(curr_line)
            if get_text_width_twitter(draw_instance, w, font_value) > (wrap_width - WRAP_SAFETY_MARGIN):
                lines.append(w); curr_line = "" 
            else:
                curr_line = w
    if curr_line: lines.append(curr_line)
    if not lines and value_text: lines.append(value_text)

    curr_y_draw = y_after_label; lines_drawn_height = 0
    num_lines_actually_drawn = 0
    for i, line in enumerate(lines):
        line_h = get_text_height_twitter(draw_instance, line, font_value)
        if line_h == 0: continue
        if curr_y_draw + line_h > max_y - MARGIN:
            logger.debug(f"Stopping draw '{label_text}' value - hit max_y at line {i+1} (Y={curr_y_draw}, LineH={line_h}, MaxY={max_y - MARGIN}).")
            break
        draw_instance.text((start_x, curr_y_draw), line, font=font_value, fill=text_color, anchor='lt')
        curr_y_draw += line_h
        lines_drawn_height += line_h
        num_lines_actually_drawn +=1
        if i < len(lines) - 1:
             if num_lines_actually_drawn < len(lines) and (curr_y_draw + get_text_height_twitter(draw_instance, lines[i+1], font_value) <= max_y - MARGIN) :
                curr_y_draw += line_spacing_value
                lines_drawn_height += line_spacing_value

    total_item_height = label_h + (LINE_SPACING_METADATA // 2) + lines_drawn_height if lines_drawn_height > 0 else label_h

    if lines_drawn_height == 0 and len(lines) > 0 :
         logger.debug(f"No lines of value text fit for '{label_text}'. Only label drawn.")
         return item_start_y + total_item_height, total_item_height

    final_y_pos_for_next_item = item_start_y + total_item_height
    return final_y_pos_for_next_item, total_item_height

def _draw_dynamic_width_description(draw_instance, label_text, value_text, y_pos, font_label, font_value, line_spacing_value, section_spacing_after, narrow_width, wide_width, cover_cutoff_y, max_y=CANVAS_HEIGHT, current_config=None):
    empty_values = {"N/A", "", "No description available.", "None", None}; label_colon = f"{label_text}:"; label_h = get_text_height_twitter(draw_instance, label_colon, font_label)
    logger.debug(f"_draw_dynamic_width_description: label='{label_text}', value_text IS EMPTY/PLACEHOLDER: {value_text in empty_values or not value_text}, value_text='{str(value_text)[:50]}...'")
    
    footer_height_estimate = 0
    if current_config and (current_config.custom_footer_text or current_config.logo_image_path):
        footer_height_estimate = FONT_SIZE_FOOTER + MARGIN + 5 

    effective_max_y = max_y - footer_height_estimate

    if value_text in empty_values or not value_text: return y_pos
    if y_pos + label_h > effective_max_y - MARGIN: 
        logger.debug(f"Skipping dynamic description - Label doesn't fit (Y={y_pos}, LabelH={label_h}, Max={effective_max_y - MARGIN}).")
        return y_pos
        
    draw_instance.text((MARGIN, y_pos), label_colon, font=font_label, fill=TEXT_COLOR_DESC, anchor='lt'); y_after_label = y_pos + label_h + LINE_SPACING_METADATA // 2
    words = str(value_text).split(); lines = []; curr_line = ""; current_line_start_y = y_after_label
    if not words: return y_after_label + section_spacing_after
    
    # MODIFICATION: Increased max_lines_for_desc
    max_lines_for_desc = 12 

    for w in words:
        current_wrap_width_for_line = narrow_width if current_line_start_y < cover_cutoff_y else wide_width
        test_line = curr_line + (" " if curr_line else "") + w
        line_w = get_text_width_twitter(draw_instance, test_line, font_value)
        
        if line_w <= (current_wrap_width_for_line - WRAP_SAFETY_MARGIN):
            curr_line = test_line
        else:
            if curr_line: 
                line_h_calc = get_text_height_twitter(draw_instance, curr_line, font_value)
                lines.append(curr_line)
                current_line_start_y += line_h_calc + line_spacing_value
            
            current_wrap_width_for_w = narrow_width if current_line_start_y < cover_cutoff_y else wide_width
            
            if get_text_width_twitter(draw_instance, w, font_value) > (current_wrap_width_for_w - WRAP_SAFETY_MARGIN):
                logger.debug(f"Dynamic Desc: Word '{w[:20]}...' exceeds wrap width {current_wrap_width_for_w - WRAP_SAFETY_MARGIN}. Adding as single line.")
                lines.append(w)
                line_h_calc = get_text_height_twitter(draw_instance, w, font_value)
                current_line_start_y += line_h_calc + line_spacing_value
                curr_line = ""
            else: 
                curr_line = w
    if curr_line: lines.append(curr_line)
    
    curr_y = y_after_label; lines_drawn = 0
    
    for i, line in enumerate(lines):
        if lines_drawn >= max_lines_for_desc:
             logger.debug(f"Stopping dynamic description draw - hit max_lines_for_desc ({max_lines_for_desc}).")
             break
        line_h = get_text_height_twitter(draw_instance, line, font_value);
        if line_h == 0: continue
        if curr_y + line_h > effective_max_y: 
            logger.debug(f"Stopping dynamic description draw - hit max_y boundary (considering footer) at line {i+1}/{len(lines)} (curr_y={curr_y}, line_h={line_h}, effective_max_y={effective_max_y}).")
            break
        draw_instance.text((MARGIN, curr_y), line, font=font_value, fill=TEXT_COLOR_DESC, anchor='lt'); curr_y += line_h + line_spacing_value; lines_drawn += 1
    
    if lines_drawn == 0 and len(lines) > 0:
         logger.debug(f"Dynamic Description: First line of text did not fit at Y={y_after_label}.")
         return y_pos 
    elif lines_drawn == 0: 
        return y_after_label 
    else:
        return curr_y - line_spacing_value 

def create_social_image_twitter(config: ComicRunConfig, original_cover_path, issue_details, description_to_use, output_social_path):
    logger.info(f"Creating Twitter social media image: {os.path.basename(output_social_path)}...")
    try:
        canvas = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), CANVAS_BG_COLOR); draw = ImageDraw.Draw(canvas)

        try: font_title = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_TITLE)
        except IOError: font_title = ImageFont.load_default(); logger.warning("Title font fail.")
        try: font_meta_label = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_METADATA_LABEL)
        except IOError: font_meta_label = ImageFont.load_default(); logger.warning("Meta label font fail.")
        try: font_meta_value = ImageFont.truetype(FONT_PATH_REGULAR, FONT_SIZE_METADATA_VALUE)
        except IOError: font_meta_value = ImageFont.load_default(); logger.warning("Meta value font fail.")
        try: font_desc_label_default = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_DESC_LABEL)
        except IOError: font_desc_label_default = ImageFont.load_default(); logger.warning("Desc label font fail.")
        try: font_desc_default = ImageFont.truetype(FONT_PATH_DESC, FONT_SIZE_DESC)
        except IOError: font_desc_default = ImageFont.load_default(); logger.warning("Desc font fail.")
        try: font_footer = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_FOOTER)
        except IOError: font_footer = ImageFont.load_default(); logger.warning("Footer font fail, using default.")


        cover_img = None; resized_width, resized_height = 0, 0; paste_x, paste_y = 0, 0; cover_bottom_y = MARGIN
        try:
            if os.path.exists(original_cover_path):
                cover_img = Image.open(original_cover_path)
                original_width, original_height = cover_img.size
                target_box_width = COVER_AREA_WIDTH; target_box_height = COVER_MAX_HEIGHT
                if original_width == 0 or original_height == 0:
                    logger.warning(f"Cover image '{original_cover_path}' has zero dimension."); resized_width = max(1, original_width); resized_height = max(1, original_height)
                else:
                    scale_w = target_box_width / original_width; scale_h = target_box_height / original_height
                    scale_factor = min(scale_w, scale_h)
                    resized_width = int(original_width * scale_factor); resized_height = int(original_height * scale_factor)
                    if resized_width < 1: resized_width = 1
                    if resized_height < 1: resized_height = 1
                    if cover_img.size != (resized_width, resized_height): cover_img = cover_img.resize((resized_width, resized_height), RESAMPLING_FILTER)
                paste_x = CANVAS_WIDTH - MARGIN - resized_width; paste_y = MARGIN
                cover_bottom_y = paste_y + resized_height
                logger.debug(f"Cover Scaled: {resized_width}x{resized_height}. Paste: X={paste_x}, Y={paste_y}, BottomY={cover_bottom_y}")
                try:
                    if cover_img.mode == 'RGBA': canvas.paste(cover_img, (paste_x, paste_y), cover_img)
                    elif cover_img.mode == 'P' and 'transparency' in cover_img.info: canvas.paste(cover_img.convert('RGBA'), (paste_x, paste_y), cover_img.convert('RGBA'))
                    else: canvas.paste(cover_img.convert('RGB'), (paste_x, paste_y))
                except Exception as paste_err: logger.error(f"Error pasting cover: {paste_err}"); cover_img = None
            else: logger.debug(f"Cover file not found: '{original_cover_path}'.")
        except (FileNotFoundError, UnidentifiedImageError, Exception) as img_err:
            logger.error(f"Error loading/scaling cover '{original_cover_path}': {img_err}."); cover_img = None; resized_width, resized_height, paste_x, paste_y = 0,0,0,0; cover_bottom_y = MARGIN

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

        current_y = TEXT_START_Y
        title_full = f"{title_text} #{issue_num_val}"
        title_wrap_chars = int((TEXT_AREA_WIDTH - WRAP_SAFETY_MARGIN) / (FONT_SIZE_TITLE * 0.55)) if FONT_SIZE_TITLE > 0 else 50
        title_lines = textwrap.wrap(title_full, width=title_wrap_chars)
        title_drawn_height = 0
        for line in title_lines:
            line_h = get_text_height_twitter(draw, line, font_title)
            if current_y + line_h > CANVAS_HEIGHT - MARGIN: break
            draw.text((TEXT_AREA_X_START, current_y), line, font=font_title, fill=TEXT_COLOR_METADATA, anchor='lt')
            current_y += line_h + LINE_SPACING_METADATA // 2
            title_drawn_height += line_h + LINE_SPACING_METADATA //2
        if title_drawn_height > 0:
            current_y += LINE_SPACING_BLOCK_AFTER - (LINE_SPACING_METADATA // 2)
        else:
            current_y = TEXT_START_Y

        metadata_max_y = CANVAS_HEIGHT
        if cover_img: metadata_max_y = cover_bottom_y

        current_y_before_block1 = current_y 
        y_col1_current = current_y_before_block1
        
        next_y_col1, h_cdate = _draw_left_aligned_label_single_value(draw, "Cover Date:", formatted_cover_date, TEXT_AREA_X_START_COL1, y_col1_current, font_meta_label, font_meta_value, 0, max_y=metadata_max_y, col_width=COLUMN_WIDTH)
        
        _max_y_this_row = current_y_before_block1 
        if h_cdate > 0:
            _max_y_this_row = max(_max_y_this_row, next_y_col1)
        
        current_y = _max_y_this_row
        if h_cdate > 0: 
            current_y += LINE_SPACING_BLOCK_AFTER
        
        optional_fields_to_draw = []
        if inker_text not in {"N/A", "?", None, ""} : optional_fields_to_draw.append(("Inker(s)", inker_text)) 
        if colorist_text not in {"N/A", "?", None, ""}: optional_fields_to_draw.append(("Colorist(s)", colorist_text))
        if letterer_text not in {"N/A", "?", None, ""}: optional_fields_to_draw.append(("Letterer(s)", letterer_text))

        y_col1_opt_current = current_y; y_col2_opt_current = current_y
        for i in range(0, len(optional_fields_to_draw), 2):
            h_opt1 = 0; h_opt2 = 0
            temp_y_col1 = y_col1_opt_current
            temp_y_col2 = y_col2_opt_current

            if i < len(optional_fields_to_draw):
                label1, value1 = optional_fields_to_draw[i]
                y_col1_opt_current, h_opt1 = _draw_label_followed_by_wrapped_value(draw, label1, value1, temp_y_col1, font_meta_label, font_meta_value, LINE_SPACING_METADATA, 0, TEXT_AREA_X_START_COL1, COLUMN_WIDTH, max_y=metadata_max_y)
            if i + 1 < len(optional_fields_to_draw):
                label2, value2 = optional_fields_to_draw[i+1]
                y_col2_opt_current, h_opt2 = _draw_label_followed_by_wrapped_value(draw, label2, value2, temp_y_col2, font_meta_label, font_meta_value, LINE_SPACING_METADATA, 0, TEXT_AREA_X_START_COL2, COLUMN_WIDTH, max_y=metadata_max_y)
            
            current_y = max(y_col1_opt_current if h_opt1 > 0 else temp_y_col1, 
                            y_col2_opt_current if h_opt2 > 0 else temp_y_col2)
            if h_opt1 > 0 or h_opt2 > 0 :
                 current_y += LINE_SPACING_BLOCK_AFTER
            
            y_col1_opt_current = current_y
            y_col2_opt_current = current_y

        left_block_bottom_y = current_y
        description_start_y = left_block_bottom_y
        logger.debug(f"Desc Start Y after metadata: {description_start_y}, Cover Bottom: {cover_bottom_y}")

        final_font_desc = font_desc_default
        font_desc_label_to_use = font_desc_label_default
        description_drawn_successfully = False
        final_desc_line_spacing = LINE_SPACING_DESC

        placeholder_desc_texts = {"N/A", "", "No description available.", "None", None}
        description_content_end_y = description_start_y 

        footer_height_reservation = 0
        if config.custom_footer_text or config.logo_image_path:
            footer_height_reservation = FONT_SIZE_FOOTER + MARGIN + 5 


        if description_to_use and description_to_use not in placeholder_desc_texts:
            available_height_for_desc_block = (CANVAS_HEIGHT - MARGIN - footer_height_reservation) - description_start_y
            desc_label_h = get_text_height_twitter(draw, "Description:", font_desc_label_to_use)
            available_height_for_text_only = available_height_for_desc_block - (desc_label_h + (LINE_SPACING_METADATA // 2))

            if available_height_for_text_only > 20: 
                current_font_size_try = FONT_SIZE_DESC
                best_fitting_font = font_desc_default
                required_text_height_at_best_fit = float('inf')

                while current_font_size_try >= TWITTER_MIN_FONT_SIZE_DESC:
                    try: temp_font_desc_to_try = ImageFont.truetype(FONT_PATH_DESC, current_font_size_try)
                    except IOError: logger.warning(f"Twitter: Could not load desc font {current_font_size_try}."); current_font_size_try -=1; continue

                    required_text_height_at_current_try = calculate_text_block_height_twitter(draw, description_to_use, temp_font_desc_to_try, LINE_SPACING_DESC, TEXT_AREA_WIDTH, DESCRIPTION_AREA_WIDTH, cover_bottom_y if cover_img else 0, description_start_y + desc_label_h + (LINE_SPACING_METADATA // 2))

                    if required_text_height_at_current_try <= available_height_for_text_only:
                        best_fitting_font = temp_font_desc_to_try
                        required_text_height_at_best_fit = required_text_height_at_current_try
                        description_drawn_successfully = True; break
                    else: best_fitting_font = temp_font_desc_to_try; required_text_height_at_best_fit = required_text_height_at_current_try
                    current_font_size_try -= 1

                final_font_desc = best_fitting_font
                if not description_drawn_successfully and final_font_desc: 
                    logger.warning(f"Twitter: Description will be truncated. Using font {final_font_desc.size if hasattr(final_font_desc, 'size') else 'default'}px.")
                    description_drawn_successfully = True 
                elif not final_font_desc:
                    logger.error("Twitter: Failed to load any description font.")
                    description_drawn_successfully = False


                if description_drawn_successfully: 
                    is_short_for_expansion = False
                    current_best_fit_font_size = final_font_desc.size if hasattr(final_font_desc, 'size') else FONT_SIZE_DESC


                    if current_best_fit_font_size < FONT_SIZE_DESC:
                        is_short_for_expansion = True
                        logger.debug(f"Desc expansion candidate: font {current_best_fit_font_size}px < default {FONT_SIZE_DESC}px.")
                    elif current_best_fit_font_size == FONT_SIZE_DESC and available_height_for_text_only > 0 and \
                         (required_text_height_at_best_fit / available_height_for_text_only) < DESCRIPTION_FILL_THRESHOLD:
                        is_short_for_expansion = True
                        logger.debug(f"Desc expansion candidate: default font used, fill ratio {required_text_height_at_best_fit / available_height_for_text_only:.2f} < threshold {DESCRIPTION_FILL_THRESHOLD}.")

                    if is_short_for_expansion:
                        logger.info(f"Attempting to expand short description. Current font: {current_best_fit_font_size}px, spacing: {LINE_SPACING_DESC}px.")
                        try:
                            font_try_expand_size = ImageFont.truetype(FONT_PATH_DESC, FONT_SIZE_DESC)
                            height_at_expanded_size_and_spacing = calculate_text_block_height_twitter(draw, description_to_use, font_try_expand_size, TARGET_EXPANDED_LINE_SPACING_DESC, TEXT_AREA_WIDTH, DESCRIPTION_AREA_WIDTH, cover_bottom_y if cover_img else 0, description_start_y + desc_label_h + (LINE_SPACING_METADATA // 2))

                            if height_at_expanded_size_and_spacing <= available_height_for_text_only:
                                final_font_desc = font_try_expand_size
                                final_desc_line_spacing = TARGET_EXPANDED_LINE_SPACING_DESC
                                logger.info(f"Successfully expanded desc to font {final_font_desc.size}px, spacing {final_desc_line_spacing}px.")
                            else: 
                                height_at_current_size_expanded_spacing = calculate_text_block_height_twitter(draw, description_to_use, final_font_desc, TARGET_EXPANDED_LINE_SPACING_DESC, TEXT_AREA_WIDTH, DESCRIPTION_AREA_WIDTH, cover_bottom_y if cover_img else 0, description_start_y + desc_label_h + (LINE_SPACING_METADATA // 2))
                                if height_at_current_size_expanded_spacing <= available_height_for_text_only:
                                    final_desc_line_spacing = TARGET_EXPANDED_LINE_SPACING_DESC
                                    logger.info(f"Expanded desc line spacing to {final_desc_line_spacing}px with font {final_font_desc.size}px.")
                                else:
                                    logger.info(f"Could not expand description further. Using font {final_font_desc.size}px, spacing {LINE_SPACING_DESC}px.")
                        except IOError:
                            logger.warning(f"Could not load font for expansion (size {FONT_SIZE_DESC}). Sticking with initial fit.")
            else:
                logger.debug(f"Twitter: Insufficient space for description label and text. Skipping description.")
                description_drawn_successfully = False

        if description_drawn_successfully:
            max_y_for_desc_draw = CANVAS_HEIGHT - footer_height_reservation 
            description_content_end_y = _draw_dynamic_width_description(draw, "Description", description_to_use, description_start_y, font_desc_label_to_use, final_font_desc, final_desc_line_spacing, 0, TEXT_AREA_WIDTH, DESCRIPTION_AREA_WIDTH, cover_bottom_y if cover_img else 0, max_y_for_desc_draw, current_config=config) 
        elif description_to_use and description_to_use not in placeholder_desc_texts:
             logger.debug(f"Description text present but not drawn due to space constraints.")
             if description_start_y < CANVAS_HEIGHT - MARGIN - footer_height_reservation - get_text_height_twitter(draw, "D", font_desc_label_default):
                 draw.text((MARGIN, description_start_y), "Description:", font=font_desc_label_default, fill=TEXT_COLOR_DESC, anchor='lt')
                 description_content_end_y = description_start_y + get_text_height_twitter(draw, "Description:", font_desc_label_default)
        else:
             logger.debug(f"Skipping Dynamic Description draw - no usable description text or failed initial fit severely.")


        # --- Footer and Logo Drawing (MODIFIED for Twitter) ---
        logo_img_resized = None
        logo_w_actual = 0
        logo_h_actual = 0
        if config.logo_image_path:
            try:
                logo_img_opened = Image.open(config.logo_image_path)
                logo_img_resized = logo_img_opened.resize(LOGO_SIZE, RESAMPLING_FILTER)
                logo_w_actual = LOGO_SIZE[0]
                logo_h_actual = LOGO_SIZE[1]
                logger.debug(f"Twitter: Loaded and resized logo: {config.logo_image_path}")
            except Exception as e:
                logger.warning(f"Twitter: Could not load/resize logo '{config.logo_image_path}': {e}")
                logo_img_resized = None
        
        footer_text_to_draw = None
        footer_w_actual = 0
        footer_h_actual = 0
        if config.custom_footer_text:
            footer_text_to_draw = config.custom_footer_text
            footer_w_actual = get_text_width_twitter(draw, footer_text_to_draw, font_footer)
            footer_h_actual = get_text_height_twitter(draw, footer_text_to_draw, font_footer)

        max_element_height = max(footer_h_actual, logo_h_actual)

        if max_element_height > 0:
            footer_area_top_y = CANVAS_HEIGHT - MARGIN - max_element_height
            min_gap_to_content = 5 
            if footer_area_top_y < description_content_end_y + min_gap_to_content:
                logger.warning(f"Twitter: Footer area (top y: {footer_area_top_y}) would overlap content (bottom y: {description_content_end_y}). Skipping footer/logo.")
            else:
                current_x_pos_footer = MARGIN
                drawn_something_in_footer = False

                if footer_text_to_draw:
                    if current_x_pos_footer + footer_w_actual <= CANVAS_WIDTH - MARGIN: 
                        text_y_offset = (max_element_height - footer_h_actual) // 2
                        text_y_pos = footer_area_top_y + text_y_offset
                        draw.text((current_x_pos_footer, text_y_pos), footer_text_to_draw, font=font_footer, fill=FOOTER_TEXT_COLOR, anchor='lt')
                        logger.debug(f"Twitter: Drew footer text '{footer_text_to_draw}' at ({current_x_pos_footer}, {text_y_pos})")
                        current_x_pos_footer += footer_w_actual
                        drawn_something_in_footer = True
                    else:
                        logger.warning(f"Twitter: Footer text '{footer_text_to_draw}' too wide. Skipping.")
                
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
                        logger.debug(f"Twitter: Pasted logo at ({current_x_pos_footer}, {logo_y_pos})")
                    else:
                        logger.warning(f"Twitter: Logo too wide to fit. Skipping logo.")
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
    twitter_platform_config = PlatformConfig(
        name="Twitter",
        directory_prefix="X",
        social_post_filename_prefix="X",
        social_post_filename_suffix="_post_16x9.jpg",
        description_word_limit=95, # MODIFIED: Harmonized with main_runner.py
        create_social_image_func=create_social_image_twitter
    )
    process_issues_for_platform(run_config, twitter_platform_config, issues_data_for_platform)

if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    standalone_logger = logging.getLogger(__name__ + ".standalone")
    standalone_logger.info("--- Comic Vine Social Image Creator (Twitter - Standalone Run) ---")

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

    standalone_logger.info("--- Twitter Standalone Script Finished ---")