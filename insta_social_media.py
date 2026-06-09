# --- START OF MODIFIED FILE intsa_social_medai.py ---
# -*- coding: utf-8 -*-
import os
import sys
import re
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError # Ensure Image is imported
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

# --- Configuration for THIS PLATFORM (Instagram) ---
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1080
CANVAS_BG_COLOR = (255, 255, 255)
COVER_AREA_WIDTH = 550
MARGIN = 25
TEXT_AREA_X_START = MARGIN
TEXT_AREA_WIDTH = CANVAS_WIDTH - COVER_AREA_WIDTH - (MARGIN * 2) 
COVER_MAX_HEIGHT = 809 
TEXT_START_Y = MARGIN + 20
LINE_SPACING_METADATA = 8
LINE_SPACING_DESC = 5
LINE_SPACING_BLOCK_AFTER = 30
FONT_PATH_REGULAR = r"C:\Windows\Fonts\verdana.ttf"
FONT_PATH_BOLD = r"C:\Windows\Fonts\verdanab.ttf"
FONT_PATH_DESC = r"C:\Windows\Fonts\verdana.ttf"
FONT_SIZE_TITLE = 39
FONT_SIZE_METADATA_LABEL = 38
FONT_SIZE_METADATA_VALUE = 38
FONT_SIZE_DESC_LABEL = 44
FONT_SIZE_DESC = 32
TEXT_COLOR_METADATA = (50, 50, 50)
TEXT_COLOR_DESC = (0, 0, 0)
SOCIAL_IMAGE_SAVE_QUALITY = 90
try: RESAMPLING_FILTER = Image.Resampling.LANCZOS
except AttributeError: RESAMPLING_FILTER = Image.LANCZOS

# <<< MODIFIED: Footer and Logo Configuration
FONT_SIZE_FOOTER = 14
FOOTER_TEXT_COLOR = (0, 0, 0)
FOOTER_MAX_CHARS = 50 # MODIFIED from 30
LOGO_SIZE = (50, 50)  # Size for the logo if displayed
LOGO_FOOTER_GAP = 15   # Horizontal gap between text and logo
# --- End Instagram Configuration ---

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

def create_social_image_instagram(config: ComicRunConfig, original_cover_path, issue_details, description_to_use, output_social_path):
    logger.info(f"Creating Instagram social media image: {os.path.basename(output_social_path)}...")
    logger.debug(f"Insta Config: COVER_AREA_WIDTH={COVER_AREA_WIDTH}, COVER_MAX_HEIGHT={COVER_MAX_HEIGHT}, TEXT_AREA_WIDTH={TEXT_AREA_WIDTH}")
    try:
        try: font_title = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_TITLE)
        except IOError: font_title = ImageFont.load_default(); logger.warning("Title font fail, using default.")
        try: font_meta_label = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_METADATA_LABEL)
        except IOError: font_meta_label = ImageFont.load_default(); logger.warning("Meta label font fail, using default.")
        try: font_meta_value = ImageFont.truetype(FONT_PATH_REGULAR, FONT_SIZE_METADATA_VALUE)
        except IOError: font_meta_value = ImageFont.load_default(); logger.warning("Meta value font fail, using default.")
        try: font_desc_label = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_DESC_LABEL)
        except IOError: font_desc_label = ImageFont.load_default(); logger.warning("Desc label font fail, using default.")
        try: font_desc = ImageFont.truetype(FONT_PATH_DESC, FONT_SIZE_DESC)
        except IOError: font_desc = ImageFont.load_default(); logger.warning("Desc font fail, using default.")
        try: font_footer = ImageFont.truetype(FONT_PATH_BOLD, FONT_SIZE_FOOTER)
        except IOError: font_footer = ImageFont.load_default(); logger.warning("Footer font fail, using default.")


        canvas = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), CANVAS_BG_COLOR); draw = ImageDraw.Draw(canvas)

        processed_cover_img = None 
        final_cover_width, final_cover_height = 0, 0

        try:
            if os.path.exists(original_cover_path):
                cover_img_opened = Image.open(original_cover_path)
                original_width, original_height = cover_img_opened.size
                logger.debug(f"Original cover dimensions: {original_width}x{original_height}")

                target_slot_width = COVER_AREA_WIDTH - MARGIN 
                target_slot_height = COVER_MAX_HEIGHT     

                if original_height == 0 or original_width == 0:
                    logger.warning(f"Cover image '{original_cover_path}' has zero dimension.")
                else:
                    scale_factor_for_height = target_slot_height / original_height
                    scaled_width_at_target_h = int(original_width * scale_factor_for_height)
                    
                    logger.debug(f"Scaling to height {target_slot_height}: new width would be {scaled_width_at_target_h}")
                    temp_resized_img = cover_img_opened.resize((scaled_width_at_target_h, target_slot_height), RESAMPLING_FILTER)

                    if scaled_width_at_target_h > target_slot_width:
                        excess_width = scaled_width_at_target_h - target_slot_width
                        crop_left = excess_width // 2
                        crop_right = scaled_width_at_target_h - (excess_width - crop_left) 
                        
                        logger.debug(f"Width {scaled_width_at_target_h} > {target_slot_width}. Cropping. Left: {crop_left}, Right based: {crop_right}. Excess: {excess_width}")
                        processed_cover_img = temp_resized_img.crop((crop_left, 0, crop_right, target_slot_height))
                        logger.debug(f"Cover cropped to: {processed_cover_img.size}")
                    else:
                        processed_cover_img = temp_resized_img
                        logger.debug(f"Cover width {scaled_width_at_target_h} <= {target_slot_width}. No horizontal crop needed.")
                    
                    final_cover_width, final_cover_height = processed_cover_img.size
            else:
                 logger.debug(f"Original cover file not found: '{original_cover_path}'.")
        except (FileNotFoundError, UnidentifiedImageError, Exception) as img_err:
             logger.error(f"Error loading/resizing cover '{original_cover_path}': {img_err}.")

        if processed_cover_img:
            slot_visual_start_x = CANVAS_WIDTH - COVER_AREA_WIDTH 
            actual_slot_width = COVER_AREA_WIDTH - MARGIN
            
            horizontal_offset_in_slot = (actual_slot_width - final_cover_width) // 2
            paste_x = slot_visual_start_x + horizontal_offset_in_slot
            paste_y = MARGIN + (COVER_MAX_HEIGHT - final_cover_height) // 2 
            logger.debug(f"Pasting cover (size {final_cover_width}x{final_cover_height}) at x={paste_x}, y={paste_y} (Slot visual start x={slot_visual_start_x}, slot actual width={actual_slot_width})")
            
            try:
                if processed_cover_img.mode == 'RGBA': canvas.paste(processed_cover_img, (paste_x, paste_y), processed_cover_img)
                elif processed_cover_img.mode == 'P' and 'transparency' in processed_cover_img.info: canvas.paste(processed_cover_img.convert('RGBA'),(paste_x, paste_y), processed_cover_img.convert('RGBA'))
                else: canvas.paste(processed_cover_img.convert('RGB'), (paste_x, paste_y))
            except Exception as paste_err: logger.error(f"Error pasting cover image: {paste_err}")

        series_title_component = issue_details.get('volume',{}).get('name','?')
        issue_num_val = issue_details.get('issue_number','?')

        title_to_draw_on_image = series_title_component
        if issue_num_val and issue_num_val != '?':
            title_to_draw_on_image += f" #{issue_num_val}"

        cover_date_str=issue_details.get('cover_date',''); formatted_cover_date="N/A";
        if cover_date_str:
            try: dt_obj=datetime.strptime(cover_date_str,'%Y-%m-%d'); formatted_cover_date=dt_obj.strftime('%m/%d/%Y')
            except ValueError:
                 try: dt_obj=datetime.strptime(cover_date_str,'%Y-%m'); formatted_cover_date=dt_obj.strftime('%m/--/%Y')
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

        def _get_text_height_local(text,font):
             if not text or not font: return 0
             try: return draw.textbbox((0,0),text,font=font,anchor='lt')[3]-draw.textbbox((0,0),text,font=font,anchor='lt')[1]
             except AttributeError: return font.getsize(text)[1]
             except TypeError: logger.error(f"TypeError in _get_text_height_local for text '{text}'"); return 0
        def _get_text_width_local(text,font):
             if not text or not font: return 0
             try: return draw.textbbox((0,0),text,font=font,anchor='lt')[2]-draw.textbbox((0,0),text,font=font,anchor='lt')[0]
             except AttributeError: return font.getsize(text)[0]
             except TypeError: logger.error(f"TypeError in _get_text_width_local for text '{text}'"); return 0

        def _draw_left_aligned_label_single_value(label_text,value_text,y_pos,font_label,font_value,line_spacing_after_value):
            empty_values={"N/A","?","Unknown Date","","None", None};
            if value_text in empty_values or value_text is None: return y_pos
            draw.text((TEXT_AREA_X_START,y_pos),label_text,font=font_label,fill=TEXT_COLOR_METADATA,anchor='lt')
            y_after_label=y_pos+_get_text_height_local(label_text,font_label)+LINE_SPACING_METADATA//2
            draw.text((TEXT_AREA_X_START,y_after_label),value_text,font=font_value,fill=TEXT_COLOR_METADATA,anchor='lt')
            return y_after_label+_get_text_height_local(value_text,font_value)+line_spacing_after_value

        def _draw_label_followed_by_wrapped_value(label_text,value_text,y_pos,font_label,font_value,line_spacing_value,section_spacing_after,start_x,wrap_width):
            empty_values={"N/A","","Unknown Publisher","None", None};
            if value_text in empty_values or value_text is None: return y_pos
            label_colon=f"{label_text}:";draw.text((start_x,y_pos),label_colon,font=font_label,fill=TEXT_COLOR_METADATA,anchor='lt')
            y_after_label=y_pos+_get_text_height_local(label_colon,font_label)+LINE_SPACING_METADATA//2;words=str(value_text).split();lines=[];curr_line=""
            if not words and value_text: words = [value_text]
            if not words: return y_after_label+section_spacing_after
            for w in words:
                test=curr_line+(" " if curr_line else "")+w;line_w=_get_text_width_local(test,font_value)
                if line_w<=wrap_width: curr_line=test
                else:
                    if curr_line: lines.append(curr_line)
                    if _get_text_width_local(w, font_value) > wrap_width:
                        lines.append(w); curr_line = ""
                    else:
                        curr_line=w
            if curr_line: lines.append(curr_line)
            if not lines and value_text: lines.append(value_text)

            curr_y_draw=y_after_label;drawn_lines_count=0
            for line_idx, line_content in enumerate(lines):
                line_h=_get_text_height_local(line_content,font_value);
                if curr_y_draw + line_h > CANVAS_HEIGHT - MARGIN : 
                    logger.debug(f"INSTAGRAM: Metadata value for '{label_text}' truncated. Line '{line_content[:20]}...' would exceed canvas margin.")
                    break
                draw.text((start_x, curr_y_draw), line_content, font=font_value, fill=TEXT_COLOR_METADATA, anchor='lt')
                curr_y_draw+=line_h
                drawn_lines_count+=1
                if line_idx < len(lines) - 1: 
                    if curr_y_draw + line_spacing_value <= CANVAS_HEIGHT - MARGIN:
                         curr_y_draw += line_spacing_value
                    else: break 

            if drawn_lines_count == 0 and len(lines) > 0 : 
                return y_pos + _get_text_height_local(label_colon,font_label) + section_spacing_after
            elif drawn_lines_count == 0: 
                return y_pos 
            
            return curr_y_draw + section_spacing_after


        def _draw_description_block(label_text,value_text,y_pos,font_label,font_value,line_spacing_value,section_spacing_after,start_x,wrap_width):
             empty_values={"N/A","","No description available.","None", None};
             if value_text in empty_values or value_text is None: return y_pos
             
             max_y_for_block = CANVAS_HEIGHT - MARGIN 
             label_h = _get_text_height_local(label_text,font_label)

             if y_pos + label_h > max_y_for_block: 
                 logger.warning(f"INSTAGRAM: Not enough space to draw description label at y={y_pos}. Max_y for block: {max_y_for_block}")
                 return y_pos
                 
             draw.text((start_x,y_pos),label_text,font=font_label,fill=TEXT_COLOR_DESC,anchor='lt')
             y_after_label=y_pos + label_h + LINE_SPACING_DESC*2

             words=str(value_text).split();lines=[];curr_line=""
             if not words and value_text: words = [value_text]
             if not words: return y_after_label + section_spacing_after 

             for w in words:
                 test=curr_line+(" " if curr_line else "")+w;line_w=_get_text_width_local(test,font_value)
                 if line_w<=wrap_width: curr_line=test
                 else:
                     if curr_line: lines.append(curr_line)
                     if _get_text_width_local(w, font_value) > wrap_width:
                        lines.append(w); curr_line = ""
                     else:
                        curr_line=w
             if curr_line: lines.append(curr_line)
             if not lines and value_text: lines.append(value_text)

             curr_y_draw=y_after_label
             drawn_lines_count = 0
             for i, line_content in enumerate(lines):
                 line_h = _get_text_height_local(line_content, font_value)
                 if line_h == 0: continue

                 if curr_y_draw + line_h > max_y_for_block:
                     logger.debug(f"INSTAGRAM: Stopping drawing description text - line {i+1} ('{line_content[:20]}...') (h={line_h}) would exceed max_y_for_block ({max_y_for_block}) at curr_y_draw {curr_y_draw}.")
                     break 
                 
                 draw.text((start_x, curr_y_draw), line_content, font=font_value, fill=TEXT_COLOR_DESC, anchor='lt')
                 curr_y_draw += line_h 
                 drawn_lines_count += 1
                 
                 if i < len(lines) - 1: 
                     if curr_y_draw + line_spacing_value <= max_y_for_block: 
                         curr_y_draw += line_spacing_value
                     else: 
                         logger.debug(f"INSTAGRAM: Not enough space for line_spacing_value after line {i+1}. Breaking after drawing line.")
                         break 
            
             if drawn_lines_count == 0 and len(lines) > 0: 
                 return y_pos + label_h + section_spacing_after 
             elif drawn_lines_count == 0: 
                 return y_pos 
             
             return curr_y_draw + section_spacing_after 

        current_y=TEXT_START_Y; title_x=TEXT_AREA_X_START
        title_wrap_width = TEXT_AREA_WIDTH ; words = title_to_draw_on_image.split(); wrapped_title_lines = []; current_line_for_title = ""
        if not words and title_to_draw_on_image: wrapped_title_lines.append(title_to_draw_on_image)
        else:
            for word in words:
                test_line = current_line_for_title + (" " if current_line_for_title else "") + word; line_width = _get_text_width_local(test_line, font_title)
                if line_width <= title_wrap_width: current_line_for_title = test_line
                else:
                    if current_line_for_title: wrapped_title_lines.append(current_line_for_title)
                    current_line_for_title = word
            if current_line_for_title: wrapped_title_lines.append(current_line_for_title)

        if not wrapped_title_lines and title_to_draw_on_image:
             wrapped_title_lines.append(title_to_draw_on_image)
             logger.debug(f"Title '{title_to_draw_on_image}' could not be wrapped, using as single line.")

        title_drawn_height = 0
        if wrapped_title_lines:
            logger.debug(f"Wrapped title: {wrapped_title_lines}")
            for line_idx, line_content in enumerate(wrapped_title_lines):
                line_h_title = _get_text_height_local(line_content, font_title)
                if current_y + line_h_title > CANVAS_HEIGHT - MARGIN : break
                draw.text((title_x, current_y), line_content, font=font_title, fill=TEXT_COLOR_METADATA, anchor='lt')
                current_y += line_h_title
                title_drawn_height += line_h_title
                if line_idx < len(wrapped_title_lines) - 1:
                    current_y += LINE_SPACING_METADATA
                    title_drawn_height += LINE_SPACING_METADATA
            if title_drawn_height > 0:
                current_y += LINE_SPACING_BLOCK_AFTER
        elif title_to_draw_on_image:
            line_h_title = _get_text_height_local(title_to_draw_on_image, font_title)
            if current_y + line_h_title <= CANVAS_HEIGHT - MARGIN:
                draw.text((title_x,current_y), title_to_draw_on_image, font=font_title, fill=TEXT_COLOR_METADATA,anchor='lt')
                current_y += line_h_title + LINE_SPACING_BLOCK_AFTER
                title_drawn_height += line_h_title
        if title_drawn_height == 0: # Fallback if title couldn't be drawn
            current_y = TEXT_START_Y            

        current_y=_draw_left_aligned_label_single_value("Cover Date:",formatted_cover_date,current_y,font_meta_label,font_meta_value,LINE_SPACING_BLOCK_AFTER)
        creator_x=TEXT_AREA_X_START;creator_w=TEXT_AREA_WIDTH
        
        metadata_vertical_limit = CANVAS_HEIGHT - MARGIN - (FONT_SIZE_DESC_LABEL * 3) 

        if current_y < metadata_vertical_limit:
            if inker_text not in {"N/A", "?", None, ""} : 
                current_y=_draw_label_followed_by_wrapped_value("Inker(s)",inker_text,current_y,font_meta_label,font_meta_value,LINE_SPACING_METADATA,LINE_SPACING_BLOCK_AFTER,start_x=creator_x,wrap_width=creator_w)
            if colorist_text not in {"N/A", "?", None, ""} and current_y < metadata_vertical_limit:
                 current_y=_draw_label_followed_by_wrapped_value("Colorist(s)",colorist_text,current_y,font_meta_label,font_meta_value,LINE_SPACING_METADATA,LINE_SPACING_BLOCK_AFTER,start_x=creator_x,wrap_width=creator_w)
            if letterer_text not in {"N/A", "?", None, ""} and current_y < metadata_vertical_limit:
                current_y=_draw_label_followed_by_wrapped_value("Letterer(s)",letterer_text,current_y,font_meta_label,font_meta_value,LINE_SPACING_METADATA,LINE_SPACING_BLOCK_AFTER,start_x=creator_x,wrap_width=creator_w)
        
        description_start_y = current_y 
        logger.debug(f"Calculated description start_y: {description_start_y}")

        description_x = TEXT_AREA_X_START
        description_wrap_width = TEXT_AREA_WIDTH 
        current_y_after_content = _draw_description_block( 
            "Issue description:", description_to_use, description_start_y,
            font_desc_label, font_desc, LINE_SPACING_DESC, 
            0, 
            start_x=description_x, wrap_width=description_wrap_width
        )
        logger.debug(f"Main content (description block or metadata if no desc) drawn, next available Y from top: {current_y_after_content}")

        # --- Footer and Logo Drawing (MODIFIED) ---
        logo_img_resized = None
        logo_w_actual = 0
        logo_h_actual = 0
        if config.logo_image_path: 
            try:
                logo_img_opened = Image.open(config.logo_image_path)
                logo_img_resized = logo_img_opened.resize(LOGO_SIZE, RESAMPLING_FILTER)
                logo_w_actual = LOGO_SIZE[0]
                logo_h_actual = LOGO_SIZE[1]
                logger.debug(f"Insta: Loaded and resized logo: {config.logo_image_path}")
            except Exception as e:
                logger.warning(f"Insta: Could not load/resize logo '{config.logo_image_path}': {e}")
                logo_img_resized = None 
        
        footer_text_to_draw = None
        footer_w_actual = 0
        footer_h_actual = 0
        if config.custom_footer_text:
            footer_text_to_draw = config.custom_footer_text
            footer_w_actual = _get_text_width_local(footer_text_to_draw, font_footer)
            footer_h_actual = _get_text_height_local(footer_text_to_draw, font_footer)

        max_element_height = max(footer_h_actual, logo_h_actual)
        
        if max_element_height > 0: 
            footer_area_top_y = CANVAS_HEIGHT - MARGIN - max_element_height
            min_gap_to_content = 5 
            if footer_area_top_y < current_y_after_content + min_gap_to_content:
                logger.warning(f"Insta: Footer area (top y: {footer_area_top_y}) would overlap content (bottom y: {current_y_after_content}). Skipping footer/logo.")
            else:
                current_x_pos_footer = MARGIN
                drawn_something_in_footer = False

                if footer_text_to_draw:
                    if current_x_pos_footer + footer_w_actual <= CANVAS_WIDTH - MARGIN: 
                        text_y_offset = (max_element_height - footer_h_actual) // 2
                        text_y_pos = footer_area_top_y + text_y_offset
                        draw.text((current_x_pos_footer, text_y_pos), footer_text_to_draw, font=font_footer, fill=FOOTER_TEXT_COLOR, anchor='lt')
                        logger.debug(f"Insta: Drew footer text '{footer_text_to_draw}' at ({current_x_pos_footer}, {text_y_pos})")
                        current_x_pos_footer += footer_w_actual
                        drawn_something_in_footer = True
                    else:
                        logger.warning(f"Insta: Footer text '{footer_text_to_draw}' too wide. Skipping.")

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
                        logger.debug(f"Insta: Pasted logo at ({current_x_pos_footer}, {logo_y_pos})")
                    else:
                        logger.warning(f"Insta: Logo too wide to fit. Skipping logo.")
        # --- End Footer and Logo Drawing ---

        output_dir=os.path.dirname(output_social_path);
        if not os.path.exists(output_dir): os.makedirs(output_dir, exist_ok=True)
        canvas.save(output_social_path, quality=SOCIAL_IMAGE_SAVE_QUALITY)
        if not os.path.exists(output_social_path) or os.path.getsize(output_social_path)==0: logger.error(f"Img missing/empty: '{os.path.basename(output_social_path)}'"); return False
        logger.info(f"OK: {os.path.basename(output_social_path)}"); return True
    except Exception as e:
        logger.error(f"ERROR creating image for {os.path.basename(original_cover_path)}: {e}", exc_info=True)
        return False

def process_and_generate(run_config: ComicRunConfig, issues_data_for_platform: list):
    insta_platform_config = PlatformConfig(
        name="Instagram",
        directory_prefix="inst",
        social_post_filename_prefix="inst",
        social_post_filename_suffix="_post.jpg",
        description_word_limit=90, 
        create_social_image_func=create_social_image_instagram
    )
    process_issues_for_platform(run_config, insta_platform_config, issues_data_for_platform)

if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    standalone_logger = logging.getLogger(__name__ + ".standalone")
    standalone_logger.info("--- Comic Vine Social Image Creator (Instagram - Standalone Run) ---")

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

    standalone_logger.info("--- Instagram Standalone Script Finished ---")

# --- END OF MODIFIED FILE intsa_social_medai.py ---