# --- START OF FILE main_runner.py ---

import os
import sys
import configparser
import time
import threading
import logging
import argparse # For command-line arguments

# === INITIALIZE LOGGING ===
LOG_FILENAME = 'comic_runner.log'
# Ensure the log file is in the same directory as the script
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOG_FILENAME)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)-8s - %(name)-25s - %(threadName)-12s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_file_path, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
# Set console handler to a higher level (e.g., INFO)
if logging.getLogger().handlers:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
            handler.setLevel(logging.INFO)
            break
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
# === END LOGGING INITIALIZATION ===


# Import the refactored modules
import insta_social_media as insta_script 
import fb_social_media as fb_script
import twitter_social_media as twitter_script

from utils import (
    find_volume_id,
    ComicRunConfig,
    PlatformConfig,
    process_issues_for_platform,
    get_filtered_issue_details,
    query_mistral_for_role_util
)
# === END MODIFIED IMPORT ===

# --- Configuration for the Runner ---
FALLBACK_API_KEY_FILENAME = r"C:\script\api_key.txt"
FALLBACK_MISTRAL_API_KEY_FILENAME = r"C:\script\mistral_api_key.txt"
CONFIG_FILENAME = 'comic_input.ini'
FOOTER_MAX_CHARS = 50 # Max characters for footer text - UPDATED
# --- End Configuration ---

def load_keys():
    comic_vine_key = None
    mistral_key = None
    logger.info("Attempting to load API Keys...")

    comic_vine_key = os.environ.get('COMIC_VINE_API_KEY')
    if comic_vine_key:
        logger.info("Comic Vine Key: Loaded from COMIC_VINE_API_KEY environment variable.")
    else:
        logger.info("COMIC_VINE_API_KEY environment variable not found. Attempting to load from file...")
        try:
            with open(FALLBACK_API_KEY_FILENAME, 'r', encoding='utf-8') as f:
                comic_vine_key = f.readline().strip()
            if not comic_vine_key:
                logger.warning(f"Comic Vine API key file '{FALLBACK_API_KEY_FILENAME}' is empty.")
                comic_vine_key = None
            else:
                logger.info(f"Comic Vine Key: Loaded from file '{FALLBACK_API_KEY_FILENAME}'.")
        except FileNotFoundError:
            logger.warning(f"Comic Vine API key file not found at '{FALLBACK_API_KEY_FILENAME}'.")
        except Exception as e:
            logger.error(f"Error loading Comic Vine API key from file: {e}", exc_info=True)
            comic_vine_key = None

    if not comic_vine_key:
        logger.critical("Comic Vine API Key is essential and could not be loaded from environment variable or file. Exiting.")
        sys.exit(1)

    mistral_key = os.environ.get('MISTRAL_API_KEY')
    if mistral_key:
        logger.info("Mistral Key: Loaded from MISTRAL_API_KEY environment variable.")
    else:
        logger.info("MISTRAL_API_KEY environment variable not found. Attempting to load from file...")
        try:
            if os.path.exists(FALLBACK_MISTRAL_API_KEY_FILENAME):
                with open(FALLBACK_MISTRAL_API_KEY_FILENAME, 'r', encoding='utf-8') as f:
                    mistral_key = f.readline().strip()
                if not mistral_key:
                    logger.warning(f"Mistral API key file '{FALLBACK_MISTRAL_API_KEY_FILENAME}' found but is empty.")
                    mistral_key = None
                else:
                    logger.info(f"Mistral Key: Loaded from file '{FALLBACK_MISTRAL_API_KEY_FILENAME}'.")
            else:
                logger.warning(f"Mistral API key file not found at '{FALLBACK_MISTRAL_API_KEY_FILENAME}'.")
        except Exception as e:
            logger.warning(f"Error reading Mistral API key file: {e}. AI features requiring it may be disabled.", exc_info=True)
            mistral_key = None
            
    if not mistral_key:
         logger.warning("Mistral API Key not loaded. AI features requiring it will be disabled.")
        
    return comic_vine_key, mistral_key

def get_comic_details(cli_args):
    config_parser = configparser.ConfigParser()
    
    ini_title, ini_publisher, ini_volume, ini_start_year, ini_end_year, ini_footer_text, ini_logo_path = None, None, None, None, None, None, None
    
    if os.path.exists(CONFIG_FILENAME):
        try:
            config_parser.read(CONFIG_FILENAME)
            if 'ComicInput' in config_parser:
                ini_section = config_parser['ComicInput']
                ini_title = ini_section.get('Title')
                ini_publisher = ini_section.get('Publisher')
                ini_volume = ini_section.get('VolumeNumber', None)
                ini_start_year_str = ini_section.get('StartYear')
                ini_end_year_str = ini_section.get('EndYear')
                ini_footer_text = ini_section.get('CustomFooterText', None)
                if ini_footer_text == "": ini_footer_text = None
                ini_logo_path = ini_section.get('LogoImagePath', None)
                if ini_logo_path == "": ini_logo_path = None

                if ini_start_year_str: 
                    try: ini_start_year = int(ini_start_year_str)
                    except ValueError: logger.warning(f"Invalid StartYear in {CONFIG_FILENAME}, ignoring.")
                if ini_end_year_str:
                    try: ini_end_year = int(ini_end_year_str)
                    except ValueError: logger.warning(f"Invalid EndYear in {CONFIG_FILENAME}, ignoring.")
                logger.info(f"Successfully loaded configuration from '{CONFIG_FILENAME}'.")
        except Exception as e:
            logger.warning(f"Could not properly read or parse '{CONFIG_FILENAME}': {e}")

    title = cli_args.title
    publisher = cli_args.publisher
    volume_number = cli_args.volume
    start_year = cli_args.start_year
    end_year = cli_args.end_year
    footer_text = cli_args.footer_text 
    logo_path = cli_args.logo_image_path   

    kept_ini_footer = False
    kept_ini_logo = False

    if not cli_args.no_prompt:
        if ini_title or ini_publisher or ini_start_year or ini_end_year: 
            print("-" * 30)
            print("Previous run used these main settings:")
            if ini_title: print(f"  Title: {ini_title}")
            if ini_publisher: print(f"  Publisher: {ini_publisher}")
            if ini_volume: print(f"  Volume: {ini_volume if ini_volume else 'N/A'}")
            if ini_start_year: print(f"  Start Year: {ini_start_year}")
            if ini_end_year: print(f"  End Year: {ini_end_year}")
            
            use_saved_main = input("  Use these main settings (Title, Publisher, Years, etc.)? (y/n, Enter for n): ").strip().lower()
            if use_saved_main == 'y':
                logger.info("User opted to use saved main settings from INI.")
                if title is None: title = ini_title
                if publisher is None: publisher = ini_publisher
                if volume_number is None: volume_number = ini_volume 
                if start_year is None: start_year = ini_start_year
                if end_year is None: end_year = ini_end_year
            else:
                logger.info("User opted NOT to use saved main settings from INI or provided no input.")
                if title is None: title = None
                if publisher is None: publisher = None
                if volume_number is None : volume_number = None
                if start_year is None: start_year = None
                if end_year is None: end_year = None
        
        prompt_custom_elements = False
        if ini_footer_text and cli_args.footer_text is None: 
            prompt_custom_elements = True
        if ini_logo_path and cli_args.logo_image_path is None: 
            prompt_custom_elements = True

        if prompt_custom_elements:
            print("-" * 30)
            print("Previous run also used these custom elements:")
            
            can_offer_footer = ini_footer_text and cli_args.footer_text is None
            can_offer_logo = ini_logo_path and cli_args.logo_image_path is None

            if can_offer_footer: print(f"  Footer Text: '{ini_footer_text}'")
            if can_offer_logo: print(f"  Logo Path: '{ini_logo_path}'")
            
            if can_offer_footer or can_offer_logo: 
                prompt_msg_parts = []
                if can_offer_footer: prompt_msg_parts.append("footer text")
                if can_offer_logo: prompt_msg_parts.append("logo path")
                prompt_msg = f"  Keep these custom { ' and '.join(prompt_msg_parts) } settings? (y/n, Enter for n): "

                use_saved_custom = input(prompt_msg).strip().lower()
                if use_saved_custom == 'y':
                    logger.info("User opted to keep custom footer/logo settings from INI.")
                    if can_offer_footer: 
                        footer_text = ini_footer_text
                        kept_ini_footer = True 
                    if can_offer_logo: 
                        logo_path = ini_logo_path
                        kept_ini_logo = True
                else: 
                    logger.info("User opted NOT to keep some/all offered custom footer/logo from INI.")
                    if can_offer_footer: footer_text = None 
                    if can_offer_logo: logo_path = None
        
    needs_prompt_title = title is None
    needs_prompt_publisher = publisher is None
    # Volume is optional, so we don't force prompt if it's None unless other things are prompted
    needs_prompt_start_year = start_year is None
    needs_prompt_end_year = end_year is None
    
    # Footer/Logo only need prompting if NOT set by CLI AND NOT explicitly kept from INI
    needs_prompt_footer = (cli_args.footer_text is None) and (not kept_ini_footer)
    needs_prompt_logo = (cli_args.logo_image_path is None) and (not kept_ini_logo)

    # Determine if the full prompt_user_for_input function needs to be called
    # It's needed if any required field is missing, OR if an optional field (footer/logo) needs prompting.
    should_call_prompt_function = (
        needs_prompt_title or 
        needs_prompt_publisher or 
        needs_prompt_start_year or 
        needs_prompt_end_year or
        (volume_number is None and (needs_prompt_title or needs_prompt_publisher or needs_prompt_start_year or needs_prompt_end_year)) or # Prompt volume if other required fields are prompted and volume is None
        needs_prompt_footer or 
        needs_prompt_logo
    )
    
    if should_call_prompt_function and not cli_args.no_prompt:
        logger.info("One or more inputs missing or requires confirmation. Prompting user.")
        title, publisher, volume_number, start_year, end_year, footer_text, logo_path = prompt_user_for_input(
            current_title=title, 
            current_publisher=publisher, 
            current_volume=volume_number, 
            current_start_year=start_year, 
            current_end_year=end_year,
            current_footer_text=footer_text, 
            current_logo_path=logo_path,     
            skip_prompt_footer=kept_ini_footer, # Skip if user said 'y' to keep INI footer
            skip_prompt_logo=kept_ini_logo     # Skip if user said 'y' to keep INI logo
        )
    elif should_call_prompt_function and cli_args.no_prompt:
        if needs_prompt_title or needs_prompt_publisher or needs_prompt_start_year or needs_prompt_end_year:
            logger.critical("Required fields (Title, Publisher, Start/End Year) are missing, and --no-prompt is active. Cannot proceed.")
            sys.exit(1)

    if not title or not isinstance(title, str): logger.critical("Title is missing or invalid after all input methods."); sys.exit(1)
    if not publisher or not isinstance(publisher, str): logger.critical("Publisher is missing or invalid after all input methods."); sys.exit(1)
    if start_year is None or not (isinstance(start_year, int) and 1800 < start_year < 2100): logger.critical(f"Start year '{start_year}' is missing or invalid after all input methods."); sys.exit(1)
    if end_year is None or not (isinstance(end_year, int) and 1800 < end_year < 2100): logger.critical(f"End year '{end_year}' is missing or invalid after all input methods."); sys.exit(1)
    if end_year < start_year: logger.critical(f"End year {end_year} must be >= start year {start_year}."); sys.exit(1)
    
    final_volume_number_str = volume_number if volume_number and volume_number.strip() else ""
    final_footer_text_str = (footer_text[:FOOTER_MAX_CHARS] if footer_text else None)

    final_logo_path_str = None
    if logo_path and logo_path.strip():
        normalized_logo_path = os.path.normpath(logo_path.strip())
        if os.path.isfile(normalized_logo_path):
            final_logo_path_str = normalized_logo_path
        else:
            logger.warning(f"Logo path '{logo_path}' was provided but the file was not found or is not a regular file. Logo will not be used.")
            final_logo_path_str = None 
    
    config_to_save = configparser.ConfigParser()
    config_to_save['ComicInput'] = {
        'Title': title, 
        'Publisher': publisher, 
        'VolumeNumber': final_volume_number_str,
        'StartYear': str(start_year), 
        'EndYear': str(end_year),
        'CustomFooterText': final_footer_text_str if final_footer_text_str else "", 
        'LogoImagePath': final_logo_path_str if final_logo_path_str else ""      
    }
    try:
        with open(CONFIG_FILENAME, 'w', encoding='utf-8') as configfile: 
            config_to_save.write(configfile)
        logger.info(f"Final input details saved to '{CONFIG_FILENAME}' for reference.")
    except IOError as e: 
        logger.warning(f"Could not write config file '{CONFIG_FILENAME}': {e}")
        
    return title, publisher, final_volume_number_str, start_year, end_year, final_footer_text_str, final_logo_path_str

def prompt_user_for_input(current_title=None, current_publisher=None, current_volume=None,
                          current_start_year=None, current_end_year=None, current_footer_text=None,
                          current_logo_path=None, skip_prompt_footer=False, skip_prompt_logo=False):
    print("-" * 30); print("Please provide/confirm the following details:"); print("-" * 30)
    
    title = current_title
    while True:
        prompt_text = f"  Enter Comic Series Title [{title or ''}]: "
        title_in = input(prompt_text).strip()
        if title_in: title = title_in; break
        elif title: break 
        else: print("    Error: Title cannot be empty.")
    
    publisher = current_publisher
    while True:
        prompt_text = f"  Enter Publisher Name [{publisher or ''}]: "
        publisher_in = input(prompt_text).strip()
        if publisher_in: publisher = publisher_in; break
        elif publisher: break
        else: print("    Error: Publisher cannot be empty.")
        
    volume_number = current_volume # Start with current value
    prompt_text_vol = f"  Enter Volume Number (OPTIONAL) [{volume_number or ''}]: "
    volume_in = input(prompt_text_vol).strip()
    if volume_in: # User typed something new for volume
        volume_number = volume_in
    elif not volume_in and current_volume is not None: # User pressed Enter, and there was a current value
        volume_number = current_volume # Keep current
    elif not volume_in and current_volume is None: # User pressed Enter, and there was no current value
        volume_number = "" # Set to empty string (optional field)
    # If volume_in is "" and current_volume was already "", it stays ""

    start_year_val = current_start_year
    while True:
        prompt_text_sy = f"  Enter Start Year [{start_year_val or ''}]: "
        start_year_str = input(prompt_text_sy).strip()
        if not start_year_str and start_year_val is not None: break 
        if start_year_str:
            try: 
                year_val_int = int(start_year_str)
                if 1800 < year_val_int < 2100: start_year_val = year_val_int; break
                else: print("    Error: Invalid year.")
            except ValueError: print("    Error: Invalid input for year.")
        elif start_year_val is None:
             print("    Error: Start Year cannot be empty.")

    end_year_val = current_end_year
    while True:
        prompt_text_ey = f"  Enter End Year [{end_year_val or ''}]: "
        end_year_str = input(prompt_text_ey).strip()
        if not end_year_str and end_year_val is not None: 
            if end_year_val >= start_year_val: break
            else: print(f"    Error: Current End Year ({end_year_val}) is less than Start Year ({start_year_val}). Please re-enter."); end_year_val = None; continue
        if end_year_str:
            try: 
                year_val_int = int(end_year_str)
                if 1800 < year_val_int < 2100:
                    if year_val_int >= start_year_val: end_year_val = year_val_int; break
                    else: print(f"    Error: End Year must be >= Start Year ({start_year_val}).")
                else: print("    Error: Invalid year.")
            except ValueError: print("    Error: Invalid input for year.")
        elif end_year_val is None:
            print("    Error: End Year cannot be empty.")

    footer_text_val = current_footer_text
    if not skip_prompt_footer:
        prompt_text_footer = f"  Enter Custom Footer Text (OPTIONAL, max {FOOTER_MAX_CHARS} chars) [{footer_text_val or ''}]: "
        temp_footer_text = input(prompt_text_footer).strip()
        if temp_footer_text: 
            footer_text_val = temp_footer_text[:FOOTER_MAX_CHARS]
        elif not temp_footer_text: 
            if current_footer_text is not None: 
                footer_text_val = current_footer_text 
            else: 
                footer_text_val = None 
    else:
        logger.info(f"Skipping footer prompt, using value: '{footer_text_val or ''}'")
     
    logo_path_val = current_logo_path
    if not skip_prompt_logo:
        prompt_text_logo = f"  Enter Path to Logo Image (OPTIONAL) [{logo_path_val or ''}]: "
        temp_logo_path = input(prompt_text_logo).strip().strip('"') 
        if temp_logo_path: 
            normalized_temp_path = os.path.normpath(temp_logo_path)
            if os.path.isfile(normalized_temp_path):
                logo_path_val = normalized_temp_path
            else:
                print(f"    Warning: Logo file '{temp_logo_path}' not found. Input ignored. Keeping previous: [{current_logo_path or ''}]")
                logo_path_val = current_logo_path 
        elif not temp_logo_path: 
            if current_logo_path is not None: 
                 logo_path_val = current_logo_path 
            else: 
                logo_path_val = None 
    else:
        logger.info(f"Skipping logo prompt, using value: '{logo_path_val or ''}'")
            
    print("-" * 30)
    return title, publisher, volume_number, start_year_val, end_year_val, footer_text_val, logo_path_val


if __name__ == "__main__":
    logger.info("--- Comic Vine Multi-Platform Social Image Runner ---")
    parser = argparse.ArgumentParser(description="Generates social media images for comic book series.")
    parser.add_argument("-t", "--title", type=str, help="Comic Series Title")
    parser.add_argument("-p", "--publisher", type=str, help="Publisher Name")
    parser.add_argument("-v", "--volume", type=str, default=None, help="Volume Number (Optional)")
    parser.add_argument("-sy", "--start-year", type=int, help="Start Year for processing issues")
    parser.add_argument("-ey", "--end-year", type=int, help="End Year for processing issues")
    parser.add_argument("-ft", "--footer-text", type=str, default=None, help=f"Custom footer text (max {FOOTER_MAX_CHARS} chars, Optional)")
    parser.add_argument("-lip", "--logo-image-path", type=str, default=None, help="Path to a logo image (Optional, e.g., C:\\path\\logo.png)") 
    parser.add_argument("--no-prompt", action="store_true", help="Suppress interactive prompts if CLI args are incomplete.")
    cli_args = parser.parse_args()

    title, publisher, volume_number, start_year, end_year, footer_text, logo_image_path_main = get_comic_details(cli_args)

    comic_vine_key, mistral_key = load_keys()

    logger.info("--- Locating Volume ID ---")
    volume_id_str = find_volume_id(comic_vine_key, title, publisher, volume_number, start_year)
    if not volume_id_str: logger.critical("RUNNER ERROR: Could not determine Volume ID. Exiting."); sys.exit(1)
    else: logger.info(f"--- Using Volume ID: {volume_id_str} for all platforms ---")

    run_config_main = ComicRunConfig(
        comic_vine_api_key=comic_vine_key, mistral_api_key=mistral_key,
        title=title, publisher=publisher, volume_number=volume_number,
        start_year=start_year, end_year=end_year, volume_id=volume_id_str,
        custom_footer_text=footer_text,
        logo_image_path=logo_image_path_main 
    )

    logger.info("Processing With Input (from run_config):")
    logger.info(f"  Title: {run_config_main.title}")
    logger.info(f"  Publisher: {run_config_main.publisher}")
    if run_config_main.volume_number: logger.info(f"  Volume: {run_config_main.volume_number}")
    logger.info(f"  Years: {run_config_main.start_year}-{run_config_main.end_year}")
    logger.info(f"  Volume ID: {run_config_main.volume_id}")
    if run_config_main.custom_footer_text: logger.info(f"  Custom Footer: '{run_config_main.custom_footer_text}'")
    if run_config_main.logo_image_path: logger.info(f"  Logo Image Path: '{run_config_main.logo_image_path}'") 

    # --- Fetch all issue details ONCE ---
    start_date_str = f"{run_config_main.start_year}-01-01"
    end_date_str = f"{run_config_main.end_year}-12-31"
    issues_to_process_globally = get_filtered_issue_details(
        run_config_main.comic_vine_api_key,
        run_config_main.volume_id,
        start_date_str,
        end_date_str
    )

    if not issues_to_process_globally:
        logger.info("No matching issues found for the given criteria. Exiting.")
        sys.exit(0)
    logger.info(f"Globally fetched {len(issues_to_process_globally)} issues for processing.")

    # --- Global AI Role Pre-fetching ---
    global_ai_role_stats = {"queries": 0, "success": 0, "fail": 0}
    if run_config_main.mistral_api_key and issues_to_process_globally:
        logger.info(f"--- Pre-fetching AI roles for {len(issues_to_process_globally)} issues globally ---")
        for issue_detail_item in issues_to_process_globally:
            vol_name_ai = issue_detail_item.get('volume', {}).get('name', '?')
            iss_num_ai = issue_detail_item.get('issue_number', '?')
            cov_date_ai = issue_detail_item.get('cover_date', '?')
            roles_to_query_map = {} 

            for generic_key_suffix, query_role_text in roles_to_query_map.items():
                global_ai_role_stats["queries"] += 1
                ai_role_name = query_mistral_for_role_util(
                    run_config_main.mistral_api_key,
                    vol_name_ai, iss_num_ai, cov_date_ai,
                    query_role_text,
                    generic_key_suffix
                )
                if ai_role_name:
                    issue_detail_item[f'ai_{generic_key_suffix}'] = ai_role_name
                    global_ai_role_stats["success"] += 1
                else:
                    global_ai_role_stats["fail"] += 1
        logger.info(f"--- Global AI Role Pre-fetching Complete ---")
        logger.info(f"Global AI Role Stats: Queries={global_ai_role_stats['queries']}, Success={global_ai_role_stats['success']}, Fail={global_ai_role_stats['fail']}")
    else:
        if not run_config_main.mistral_api_key:
            logger.info("Mistral API key not available, skipping global AI role pre-fetching.")
        elif not issues_to_process_globally:
            logger.info("No issues to process, skipping global AI role pre-fetching.")

    logger.info("--- Starting Parallel Platform Processing ---")

    platform_configurations = [
        PlatformConfig(
            name="Instagram",
            directory_prefix="inst",
            social_post_filename_prefix="inst",
            social_post_filename_suffix="_post.jpg",
            description_word_limit=82, 
            create_social_image_func=insta_script.create_social_image_instagram
        ),
        PlatformConfig(
            name="Facebook",
            directory_prefix="fb",
            social_post_filename_prefix="fb",
            social_post_filename_suffix="_post_1200x630.jpg",
            description_word_limit=100, 
            create_social_image_func=fb_script.create_social_image_facebook
        ),
        PlatformConfig(
            name="Twitter",
            directory_prefix="X",
            social_post_filename_prefix="X",
            social_post_filename_suffix="_post_16x9.jpg",
            description_word_limit=95, 
            create_social_image_func=twitter_script.create_social_image_twitter
        )
    ]

    threads = []
    platform_results = {}

    def thread_wrapper(platform_name, target_func, general_run_config, platform_spec_config, issues_data, results_dict):
        logger.info(f"THREAD START: {platform_name} Processing " + "="*10)
        try:
            stats_or_error = target_func(general_run_config, platform_spec_config, issues_data)
            results_dict[platform_name] = stats_or_error
            if isinstance(stats_or_error, dict) and stats_or_error.get("status") == "SUCCESS":
                logger.info(f"THREAD END: {platform_name} processing finished successfully.")
            else:
                error_msg = "Unknown error"
                if isinstance(stats_or_error, dict) and stats_or_error.get("error_message"):
                    error_msg = stats_or_error.get("error_message")
                elif isinstance(stats_or_error, str):
                    error_msg = stats_or_error
                logger.error(f"THREAD END: {platform_name} processing finished with errors. Error: {error_msg}")

        except Exception as e:
            logger.error(f"THREAD ERROR during {platform_name} processing (uncaught in target): {e}", exc_info=True)
            results_dict[platform_name] = {
                "status": "FAILED", "error_message": f"Unhandled exception: {e}",
                "issues_considered": 0, "covers_dl_ok": 0, "covers_dl_fail": 0,
                "social_created_ok": 0, "social_created_fail": 0,
                "desc_original": 0, "desc_ai_generated": 0, "desc_ai_summarized": 0, "desc_unavailable": 0,
                "ai_summary_queries": 0, "ai_summary_success": 0,
                "ai_summary_fail": 0, "ai_generation_queries": 0, "ai_generation_success": 0,
                "ai_generation_fail": 0,
            }
            logger.info(f"THREAD END: {platform_name} processing finished with unhandled errors.")

    for plat_config in platform_configurations:
        thread = threading.Thread(
            target=thread_wrapper,
            name=f"{plat_config.name}Thread",
            args=(
                plat_config.name,
                process_issues_for_platform,
                run_config_main,
                plat_config,
                issues_to_process_globally,
                platform_results
            )
        )
        threads.append(thread); thread.start()

    logger.info("Main thread waiting for all platform processing threads to complete...")
    for i, thread in enumerate(threads):
        thread.join(); logger.info(f"Thread for {platform_configurations[i].name} has completed.")

    logger.info("="*20 + " All Platform Processing Threads Complete " + "="*20)
    logger.info("--- Detailed Summary of Platform Runs: ---")
    if run_config_main.mistral_api_key:
        logger.info(f"  --- Global AI Role Query Stats ---")
        logger.info(f"    Total Queries: {global_ai_role_stats['queries']}")
        logger.info(f"    Successful:    {global_ai_role_stats['success']}")
        logger.info(f"    Failed:        {global_ai_role_stats['fail']}")
        logger.info(f"  --------------------------------")


    overall_success = True
    for platform_name, results in platform_results.items():
        logger.info(f"  --- Platform: {platform_name} ---")
        if isinstance(results, dict):
            logger.info(f"    Status: {results.get('status', 'UNKNOWN')}")
            if results.get('status') != "SUCCESS":
                overall_success = False
                if results.get('error_message'):
                    logger.warning(f"    Error: {results.get('error_message')}")

            logger.info(f"    Issues Considered: {results.get('issues_considered', 0)}")
            logger.info(f"    Cover Downloads: OK={results.get('covers_dl_ok', 0)}, Fail={results.get('covers_dl_fail', 0)}")
            logger.info(f"    Social Images Created: OK={results.get('social_created_ok', 0)}, Fail={results.get('social_created_fail', 0)}")
            logger.info(f"    Descriptions: Original={results.get('desc_original', 0)}, AI Gen={results.get('desc_ai_generated', 0)}, AI Sum={results.get('desc_ai_summarized', 0)}, Unavailable={results.get('desc_unavailable', 0)}")

            if run_config_main.mistral_api_key:
                logger.info(f"    AI Summary Queries: Total={results.get('ai_summary_queries',0)}, Success={results.get('ai_summary_success',0)}, Fail={results.get('ai_summary_fail',0)}")
                logger.info(f"    AI Generation Queries: Total={results.get('ai_generation_queries',0)}, Success={results.get('ai_generation_success',0)}, Fail={results.get('ai_generation_fail',0)}")
        else:
            logger.warning(f"    Unexpected result format: {results}")
            overall_success = False
        logger.info(f"  --- End Platform: {platform_name} ---")

    if overall_success:
        logger.info("OVERALL SUCCESS: All platforms reported successful completion of their main processing workflow.")
    else:
        logger.warning("OVERALL ATTENTION: One or more platforms encountered errors or did not complete successfully. Review logs.")
    logger.info("--- Main Runner Script Complete ---")

# --- END OF FILE main_runner.py ---