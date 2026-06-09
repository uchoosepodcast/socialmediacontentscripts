# --- START OF FILE utils.py ---
import os
import requests
import sys
import json
import re
import time
from urllib.parse import urlencode
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, List
from PIL import Image, UnidentifiedImageError
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
API_DELAY_SECONDS = 1.1
AI_CALL_DELAY_SECONDS = 2.0
PREFERRED_IMAGE_QUALITY = 'super_url'
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-tiny" # or your preferred model like "mistral-small-latest"
try: RESAMPLING_FILTER = Image.Resampling.LANCZOS
except AttributeError: RESAMPLING_FILTER = Image.LANCZOS

MISTRAL_API_SEMAPHORE = threading.Semaphore(1)

@dataclass
class ComicRunConfig:
    comic_vine_api_key: str
    mistral_api_key: Optional[str]
    title: str
    publisher: str
    volume_number: str
    start_year: int
    end_year: int
    volume_id: str
    custom_footer_text: Optional[str] = None
    logo_image_path: Optional[str] = None

    def __post_init__(self):
        if self.volume_id is not None and not isinstance(self.volume_id, str):
            self.volume_id = str(self.volume_id)
        if self.volume_number is None:
            self.volume_number = ""
        if self.custom_footer_text and len(self.custom_footer_text) > 50: 
            logger.warning(f"Custom footer text was longer than 50 chars, truncated: '{self.custom_footer_text[:50]}'") 
            self.custom_footer_text = self.custom_footer_text[:50] 
        
        if self.logo_image_path:
            normalized_path = os.path.normpath(self.logo_image_path)
            if not os.path.isfile(normalized_path):
                logger.warning(f"Logo image path specified ('{self.logo_image_path}') but file not found or is not a regular file. Logo will not be used.")
                self.logo_image_path = None
            else:
                self.logo_image_path = normalized_path


@dataclass
class PlatformConfig:
    name: str
    directory_prefix: str
    social_post_filename_prefix: str
    social_post_filename_suffix: str
    description_word_limit: int
    create_social_image_func: Callable[['ComicRunConfig', str, Dict[str, Any], Optional[str], str], bool]

def make_api_request(url, params, headers):
    try:
        response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        if not response.text:
            logger.error("Comic Vine API returned empty response.")
            return None
        data = response.json()
        if data.get('error') != 'OK':
            logger.error(f"Comic Vine API returned error: {data.get('error')} (Code: {data.get('status_code')}) for URL: {url} with params: {params.get('query', '')}")
            return None
        return data
    except requests.exceptions.Timeout:
        logger.error(f"Comic Vine API request timed out for URL: {url}", exc_info=False)
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"Comic Vine API HTTP Error {e.response.status_code} - {e.response.reason} for URL: {url}", exc_info=False)
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Comic Vine API request failed - {e} for URL: {url}", exc_info=True)
        return None
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON response from Comic Vine API for URL: {url}. Response text (first 200 chars): {response.text[:200]}...", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during Comic Vine API request for URL: {url}: {e}", exc_info=True)
        return None

def find_volume_id(api_key, series_title, publisher_name, volume_number, user_start_year):
    log_volume_str = f" Vol. '{volume_number}'" if volume_number else ""
    logger.info(f"Searching for Volume ID for '{series_title}'{log_volume_str} by '{publisher_name}'...")
    search_url = "https://comicvine.gamespot.com/api/search/"
    headers = {'User-Agent': 'ComicSocialCreator/1.0 PythonScript'}
    params = {'api_key': api_key, 'format': 'json', 'resources': 'volume', 'query': series_title, 'limit': 25}
    data = make_api_request(search_url, params, headers)
    if not data:
        logger.error("make_api_request failed in find_volume_id.")
        return None
    results = data.get('results', [])
    if not results:
        logger.info(f"No volumes found on Comic Vine matching search query '{series_title}'.")
        return None
    candidate_volumes = []
    simplified_user_title = re.sub(r'[\s\-:]+', '', series_title).lower()
    for volume in results:
        vol_name = volume.get('name', 'N/A')
        pub_info = volume.get('publisher', {})
        pub_name = pub_info.get('name', 'N/A')
        vol_start_year_str = volume.get('start_year', 'N/A')
        pub_match = publisher_name.lower() in pub_name.lower()
        if not pub_match:
            logger.debug(f"Skipping volume '{vol_name}' due to publisher mismatch ('{pub_name}' vs '{publisher_name}').")
            continue
        simplified_vol_name = re.sub(r'[\s\-:]+', '', vol_name).lower()
        title_match = (simplified_user_title in simplified_vol_name or
                       simplified_vol_name in simplified_user_title or
                       series_title.lower() in vol_name.lower())
        if not title_match:
            logger.debug(f"Skipping volume '{vol_name}' due to title mismatch.")
            continue
        vol_num_explicitly_matched = False
        if volume_number:
            patterns = [
                rf" v{re.escape(volume_number)}\b", rf" vol {re.escape(volume_number)}\b",
                rf" vol\. {re.escape(volume_number)}\b", rf" volume {re.escape(volume_number)}\b"
            ]
            end_pattern = rf"[\s\-]+{re.escape(volume_number)}\b"; vol_name_lower = vol_name.lower()
            if any(re.search(p, vol_name_lower) for p in patterns) or re.search(end_pattern, vol_name_lower):
                vol_num_explicitly_matched = True
        vol_start_year = None
        try:
            if vol_start_year_str and vol_start_year_str != 'N/A': vol_start_year = int(vol_start_year_str)
        except ValueError:
            logger.warning(f"Could not parse start_year '{vol_start_year_str}' for volume '{vol_name}'.")
        volume['parsed_start_year'] = vol_start_year
        volume['vol_num_explicitly_matched'] = vol_num_explicitly_matched
        candidate_volumes.append(volume)
    logger.debug(f"Found {len(candidate_volumes)} candidates after initial publisher/title filtering.")
    if not candidate_volumes:
        logger.info(f"No volumes found passed initial publisher/title checks for '{series_title}'.")
        return None
    valid_candidates = [v for v in candidate_volumes if v.get('parsed_start_year') is not None and v['parsed_start_year'] <= user_start_year]
    if not valid_candidates:
        logger.info(f"Found {len(candidate_volumes)} candidate(s), but none started on or before user's target start year {user_start_year}.")
        return None
    logger.debug(f"{len(valid_candidates)} candidates after filtering by start year <= {user_start_year}.")
    selection_list = valid_candidates
    if volume_number:
        preferred_candidates = [v for v in valid_candidates if v['vol_num_explicitly_matched']]
        if preferred_candidates:
            logger.info(f"Prioritizing {len(preferred_candidates)} candidate(s) matching Vol '{volume_number}'.")
            selection_list = preferred_candidates
        else:
            logger.warning(f"No candidates explicitly matched Vol '{volume_number}'. Selecting from all {len(valid_candidates)} valid year candidates.")
    best_match_id = None
    if not selection_list:
        logger.info("No suitable candidates remaining after all filters.")
        return None
    elif len(selection_list) == 1:
        best_match = selection_list[0]
        best_match_id = best_match.get('id')
        logger.info(f"Found one match: '{best_match.get('name')}' (ID: {best_match_id}, Year: {best_match.get('start_year')})")
    else:
        print(f"\n  Found {len(selection_list)} potential volumes. Please choose:")
        selection_list.sort(key=lambda x: (x.get('parsed_start_year', 0), x.get('name', '')), reverse=True)
        valid_choices = {}
        for i, vol in enumerate(selection_list):
            vol_id = vol.get('id'); vol_name = vol.get('name', 'N/A'); start_year_display = vol.get('start_year', 'N/A')
            info = "(Explicit Vol# Match)" if vol['vol_num_explicitly_matched'] else ""
            valid_choices[str(i+1)] = vol; valid_choices[str(vol_id)] = vol
            print(f"    [{i+1}] '{vol_name}' (ID: {vol_id}, Year: {start_year_display}) {info}")
        while True:
            choice = input(f"  Enter number [1-{len(selection_list)}] or exact ID: ").strip()
            selected_volume = valid_choices.get(choice)
            if selected_volume:
                best_match_id = selected_volume.get('id')
                print(f"  Selected: '{selected_volume.get('name')}' (ID: {best_match_id})")
                break
            else:
                print(f"    Invalid selection.")
    if best_match_id:
        logger.debug(f"Sleeping for {API_DELAY_SECONDS}s after volume selection.")
        time.sleep(API_DELAY_SECONDS)
        return str(best_match_id)
    else:
        logger.warning("No volume selected by user or automatically.")
        return None

def get_filtered_issue_details(api_key, volume_id, start_date, end_date):
    logger.info(f"Fetching issue details for Volume ID {volume_id} between {start_date} and {end_date}...")
    all_issue_details = []; offset = 0; limit = 100
    base_url = "https://comicvine.gamespot.com/api/issues/"
    headers = {'User-Agent': 'ComicSocialCreator/1.0 PythonScript'}
    field_list = "id,issue_number,name,cover_date,volume,description,image,person_credits"; date_filter = f"{start_date}|{end_date}"
    while True:
        params = {
            'api_key': api_key, 'format': 'json',
            'filter': f"volume:{volume_id},cover_date:{date_filter}",
            'sort': 'cover_date:asc,issue_number:asc', 'limit': limit,
            'offset': offset, 'field_list': field_list
        }
        data = make_api_request(base_url, params, headers)
        if not data:
            logger.error("Failed batch fetch in get_filtered_issue_details.")
            return [] if offset == 0 else all_issue_details
        results = data.get('results')
        if results is None: results = []
        elif not isinstance(results, list):
            logger.warning(f"API results not list. Type: {type(results)}. Treating as empty.")
            results = []
        if not results and offset == 0:
            logger.info("No issues found matching criteria.")
            return []
        for issue_dict in results:
            try:
                if not isinstance(issue_dict, dict):
                    logger.warning(f"Skipping non-dict item in issue results: {issue_dict}")
                    continue
                all_issue_details.append(issue_dict)
            except Exception as e:
                logger.error(f"ERROR processing issue (ID {issue_dict.get('id', 'N/A')}): {e}", exc_info=True)
        total_results = data.get('number_of_total_results', 0)
        page_results = data.get('number_of_page_results', len(results))
        logger.info(f"Batch: {len(results)}. Total issues fetched: {len(all_issue_details)} / {total_results}")
        if (total_results > 0 and len(all_issue_details) >= total_results) or page_results < limit:
            logger.info("Finished fetching all issues for this volume/date range.")
            break
        else:
            offset = len(all_issue_details)
            logger.debug(f"Fetching next batch of issues. New offset: {offset}. Sleeping for {API_DELAY_SECONDS}s.")
            time.sleep(API_DELAY_SECONDS)
    return all_issue_details

def download_cover_util(url, output_path):
    if not url: logger.warning("Skipping Download: No URL."); return False
    logger.info(f"Downloading: {os.path.basename(output_path)} ..."); headers = {'User-Agent': 'ComicSocialCreator/1.0 PythonScript'}
    try:
        response = requests.get(url, stream=True, headers=headers, timeout=REQUEST_TIMEOUT); response.raise_for_status()
        ct = response.headers.get('content-type', '').lower()
        if not ct.startswith('image/') and ct != 'application/octet-stream':
            logger.warning(f"Blocking download due to unexpected content type ('{ct}').")
            return False
        elif ct == 'application/octet-stream':
             logger.info(f"Content type is 'application/octet-stream'. Proceeding with download attempt.")
        output_dir = os.path.dirname(output_path);
        if not os.path.exists(output_dir): os.makedirs(output_dir, exist_ok=True)
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0: time.sleep(0.01); return True
        else:
            logger.error(f"Downloaded file empty/not saved: {output_path}");
            if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
                try: os.remove(output_path); logger.info(f"Cleaned up empty file: {output_path}")
                except Exception as e_rm: logger.error(f"Error cleaning up empty file {output_path}: {e_rm}")
            return False
    except requests.exceptions.Timeout: logger.error("Download timed out.", exc_info=False); return False
    except requests.exceptions.RequestException as e: logger.error(f"Error downloading: {e}", exc_info=True); return False
    except IOError as e: logger.error(f"Error saving file '{output_path}': {e}", exc_info=True); return False
    except Exception as e: logger.error(f"Unexpected download error: {e}", exc_info=True); return False

def sanitize_filename_util(name):
    name = str(name); name = re.sub(r'[<>:"/\\|?*]', '_', name); name = name.replace(' ', '_')
    name = re.sub(r'[^a-zA-Z0-9_\-.]', '', name); name = re.sub(r'__+', '_', name); name = re.sub(r'-+', '-', name)
    name = name.strip('_-'); return name if name else "untitled"

def clean_html_util(raw_html):
    if not raw_html: return ""
    text = re.sub(r'<br\s*/?>', '\n', raw_html, flags=re.IGNORECASE)
    cleanr = re.compile('<.*?>'); text = re.sub(cleanr, '', text)
    try: import html; text = html.unescape(text)
    except ImportError: pass
    text = re.sub(r'\s+', ' ', text).strip(); return text

def clean_ai_name_response_util(ai_response, role):
    if role.lower() in ["penciler", "interior artist"]:
        logger.debug(f"RAW AI Response for role '{role}': '{ai_response}'")
    if not ai_response:
        logger.debug(f"clean_ai_name_util ({role}): Input empty.")
        return None
    cleaned_name = ai_response.strip()
    logger.debug(f"clean_ai_name_util ({role}): Initial='{cleaned_name[:150]}...'")
    cleaned_name = re.sub(r'\s*Confidence:\s*\d+%.*$', '', cleaned_name, flags=re.I | re.S).strip()
    cleaned_name = re.sub(r'\s*Note:.*$', '', cleaned_name, flags=re.I | re.S).strip()
    cleaned_name = re.sub(r'\s*Please note that.*$', '', cleaned_name, flags=re.I | re.S).strip()
    cleaned_name = re.sub(r'\s*Source(s)?:\s*.*$', '', cleaned_name, flags=re.I | re.S).strip()
    cleaned_name = re.sub(r'\s*https?://\S+.*$', '', cleaned_name, flags=re.I | re.S).strip()
    cleaned_name = re.sub(r'\s*www\.\S+.*$', '', cleaned_name, flags=re.I | re.S).strip()
    cleaned_name = re.sub(r'\s*/imagine Prompt:.*$', '', cleaned_name, flags=re.I | re.S).strip()
    intro_phrases_to_remove = [
        r'^\s*The\s+interior\s+artist\s+for\s+.*?\s+issue\s+#\d+.*?is\s*', r'^\s*The\s+cover\s+artist\s+for\s+.*?\s+issue\s+#\d+.*?is\s*',
        r'^\s*The\s+writer\s+for\s+.*?\s+issue\s+#\d+.*?is\s*', r'^\s*The\s+{re.escape(role)}(s)?\s+for\s+.*?\s+is\s*',
        r'^\s*The\s+{re.escape(role)}(s)?\s*is\s+usually\s+credited\s+as\s*', r'^\s*The\s+{re.escape(role)}(s)?\s*(?:is|are)\s*',
        r'^\s*Usually,\s+the\s+{re.escape(role)}(s)?\s*(?:is|are)\s*',
        r'^\s*It\s+appears\s+to\s+be\s*', r'^\s*It\s*is\s*', r'^\s*Looks\s+like\s*',
        r'^\s*The\s+', r'^\s*Is\s+', r'^\s*Are\s+',
        rf'\b(is|are)\s+the\s+interior\s+artist(s)?\s+for\s+.*?\s+issue\s+#\d+.*$', rf'\b(is|are)\s+the\s+cover\s+artist(s)?\s+for\s+.*?\s+issue\s+#\d+.*$',
        rf'\b(is|are)\s+the\s+writer(s)?\s+for\s+.*?\s+issue\s+#\d+.*$', rf'\b(is|are)\s+the\s+{re.escape(role)}(s)?\s+for\s+.*$',
        rf'\b(is|are)\s+listed\s+as\s+the\s+{re.escape(role)}(s)?.*$',
        r'\.\s*The\s+comic\s+was\s+released.*$',
    ]
    for pattern in intro_phrases_to_remove:
         cleaned_name = re.sub(pattern, ' ', cleaned_name, flags=re.I | re.S).strip()
         cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    suffix_patterns_to_remove = [
        r'\s*-\s*.*?(?:issue|iss\.?|vol\.?|v\.?|#)\s*\d+.*$',
        r'\s*for\s*.*?(?:issue|iss\.?|vol\.?|v\.?|#)\s*\d+.*$',
        r'\s*from\s*.*?(?:issue|iss\.?|vol\.?|v\.?|#)\s*\d+.*$',
        r'\s*\(based on.*?\)$',
        r'\s*as\s+credited\s+on.*$',
        r'\s*on\s+the\s+cover\s+of.*$',
        r'\s+in\s+(?:the\s+)?(?:issue|iss\.?|vol\.?|v\.?)\s*#?\d+.*$',
        r',\s*(?:issue|iss\.?|vol\.?|v\.?)\s*#?\d+.*$',
        r'\s+(?:issue|iss\.?|vol\.?|v\.?)\s*#?\d+.*$',
        r'\.\s*However.*$',
        r'\s*are\s+the\s+two\s+most\s+commonly\s+cited.*$',
        r'\s+are\s+often\s+cited\s+for.*$',
        r'\s+was\s+done\s+by.*$',
        r'\s*according\s+to\s+most\s+sources.*$',
        r'\s*is\s+credited\s+as\s+the\s+writer.*$',
    ]
    name_before_suffix_removal = cleaned_name
    for pattern in suffix_patterns_to_remove:
        temp_name = cleaned_name
        cleaned_name = re.sub(pattern + '$', '', temp_name, flags=re.I | re.S).strip()
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
        if temp_name != cleaned_name:
            logger.debug(f"clean_ai_name_util ({role}): Applied suffix pattern '{pattern}', new='{cleaned_name}' (was: '{temp_name}')")
    if name_before_suffix_removal != cleaned_name:
        logger.debug(f"clean_ai_name_util ({role}): Overall after specific suffix removal='{cleaned_name}' (was: '{name_before_suffix_removal}')")
    cleaned_name = re.sub(r'\s*\([^)]*\)\s*', ' ', cleaned_name).strip()
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    logger.debug(f"clean_ai_name_util ({role}): After paren removal='{cleaned_name}'")
    cleaned_name = re.sub(r'(?<=[a-zA-Z])and(?=[A-Z])', r' and ', cleaned_name, flags=re.IGNORECASE).strip()
    cleaned_name = re.sub(r'\s*&\s*', ', ', cleaned_name).strip()
    cleaned_name = re.sub(r'\s+(?:and|or)\s+', ', ', cleaned_name, flags=re.IGNORECASE).strip()
    cleaned_name = re.sub(r'(?<=[a-z])(?=[A-Z])', r' ', cleaned_name).strip()
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    logger.debug(f"clean_ai_name_util ({role}): After conjunction handling='{cleaned_name}'")
    names_list = [name.strip() for name in re.split(r',(?!\s*(?:Jr|Sr|II|III|IV|V)\.?)', cleaned_name) if name and name.strip()]
    logger.debug(f"clean_ai_name_util ({role}): Potential names list after split='{names_list}'")
    junk_and_role_words_post_split = {
        'n/a', 'unknown', 'not available', 'none', 'it', 'is', 'was', 'for', 'by',
        'issue', 'writer', 'artist', 'penciler', 'penciller', 'coverartist', 'inker', 'colorist', 'letterer',
        'the', 'and', 'or',
        'credited', 'uncredited', 'various', 'multiple artists', 'various writers'
    }
    temp_names_list = []
    for name_part in names_list:
        name_part_cleaned = re.sub(r'\s*\((?:writer|artist|penciler|cover|inker|colorist|letterer)\s*\)$', '', name_part, flags=re.I).strip()
        if name_part_cleaned and name_part_cleaned.lower() not in junk_and_role_words_post_split and (len(name_part_cleaned.split()) >= 1 and len(name_part_cleaned) > 1):
            temp_names_list.append(name_part_cleaned)
    names_list = temp_names_list
    logger.debug(f"clean_ai_name_util ({role}): Names list after junk filter='{names_list}'")
    selected_name = names_list[0] if names_list else None
    if not selected_name:
        logger.debug(f"clean_ai_name_util ({role}): No valid name found after filtering.")
        return None
    logger.debug(f"clean_ai_name_util ({role}): Selected first name='{selected_name}'")
    final_name = selected_name.strip(' ,;:-&.').strip()
    logger.debug(f"clean_ai_name_util ({role}): After final strip='{final_name}'")
    if final_name and ' (' in final_name:
        parts = final_name.split(' (', 1)
        potential_suffix_in_paren = parts[1] if len(parts) > 1 else ""
        if not re.match(r'^(Jr|Sr|II|III|IV|V)\s*\)?$', potential_suffix_in_paren.strip(), re.IGNORECASE):
            logger.debug(f"clean_ai_name_util ({role}): Found ' (' and content after doesn't look like a standard name suffix. Original: '{final_name}'. Taking first part: '{parts[0]}'")
            final_name = parts[0].strip()
        else:
            logger.debug(f"clean_ai_name_util ({role}): Found ' (' but content after looks like a standard name suffix ('{potential_suffix_in_paren}'). Keeping original: '{final_name}'")
    lowercase_connectors = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'so', 'yet', 'at', 'by', 'for', 'from', 'in', 'into', 'of', 'on', 'onto', 'out', 'over', 'past', 'to', 'up', 'with', 'de', 'van', 'von', 'da', 'di', 'do', 'le', 'la', 'du', 'o\''}
    if final_name:
        words = final_name.split(); proc_words = []
        for i, w in enumerate(words):
            if "-" in w:
                parts = [p.capitalize() for p in w.split("-")]; proc_words.append("-".join(parts))
            elif "'" in w and w.lower().startswith(('o\'', 'd\'', 'l\'')):
                parts = w.split("'"); proc_words.append(parts[0].capitalize()+"'"+"'".join([p.capitalize() for p in parts[1:]]))
            elif w.lower() in lowercase_connectors and i > 0: proc_words.append(w.lower())
            elif re.match(r'^(jr|sr|ii|iii|iv|v)\.?$', w, re.IGNORECASE):
                 suffix_val = w.lower().replace('.', '')
                 if suffix_val in ['jr', 'sr']: proc_words.append(suffix_val.capitalize() + '.')
                 else: proc_words.append(suffix_val.upper())
            else: proc_words.append(w.capitalize())
        final_name = " ".join(proc_words).strip()
    if not final_name:
         logger.debug(f"clean_ai_name_util ({role}): Empty after title casing?")
         return None
    final_name = re.sub(r'^(is|are)\s+', '', final_name, flags=re.I).strip()
    logger.debug(f"clean_ai_name_util ({role}): Final Cleaned Name: '{final_name}'.")
    return final_name

def query_mistral_with_retry(api_url, headers, payload, timeout, max_retries=3, initial_backoff=AI_CALL_DELAY_SECONDS):
    retries = 0
    backoff_time = initial_backoff
    while retries < max_retries:
        try:
            logger.debug(f"Attempting API call to {api_url} (Attempt {retries + 1})")
            response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning(f"Rate limit hit (429) for {api_url}. Retrying in {backoff_time:.2f}s... (Attempt {retries + 1}/{max_retries})")
                time.sleep(backoff_time)
                backoff_time = min(backoff_time * 2, 60)
                retries += 1
            elif e.response.status_code >= 500:
                 logger.warning(f"Server error {e.response.status_code} for {api_url}. Retrying in {backoff_time:.2f}s... (Attempt {retries + 1}/{max_retries})")
                 time.sleep(backoff_time)
                 backoff_time = min(backoff_time * 2, 60)
                 retries += 1
            else:
                logger.error(f"HTTP Error {e.response.status_code} for {api_url}: {e}", exc_info=False)
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {api_url}: {e}", exc_info=True)
            if retries < max_retries -1 :
                 logger.warning(f"Request error. Retrying in {backoff_time:.2f}s... (Attempt {retries + 1}/{max_retries})")
                 time.sleep(backoff_time)
                 backoff_time = min(backoff_time * 2, 60)
                 retries +=1
            else:
                return None
        except Exception as e:
            logger.error(f"Unexpected error during API request to {api_url}: {e}", exc_info=True)
            return None
    logger.error(f"Max retries reached for API call to {api_url}.")
    return None

def query_mistral_for_role_util(api_key, volume_name, issue_num, cover_date, role_name_query, target_role_key_suffix):
    if not api_key: return None
    prompt = f"Who is the {role_name_query} for {volume_name} issue #{issue_num} ({cover_date})? Only display the name, nothing else."
    logger.debug(f"Query Mistral Role: '{role_name_query}' for {volume_name} #{issue_num}...")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {"model": MISTRAL_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 75, "temperature": 0.01}
    data = None
    with MISTRAL_API_SEMAPHORE:
        logger.debug(f"Semaphore acquired for role: {role_name_query}")
        data = query_mistral_with_retry(MISTRAL_API_URL, headers, payload, REQUEST_TIMEOUT)
        logger.debug(f"Semaphore released for role: {role_name_query}. Sleeping for {AI_CALL_DELAY_SECONDS:.2f}s.")
        time.sleep(AI_CALL_DELAY_SECONDS)
    if data:
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        if content:
            cleaned = clean_ai_name_response_util(content, role_name_query)
            if cleaned:
                logger.debug(f"Mistral Role OK for '{role_name_query}': '{cleaned}'")
                return cleaned
            else:
                logger.debug(f"Mistral Role cleaning failed for raw: '{content}' for role '{role_name_query}'")
                return None
        logger.debug(f"Mistral Role response empty/unparsable for '{role_name_query}'."); return None
    else:
        logger.error(f"Failed to get data from Mistral for role '{role_name_query}' after retries.")
        return None

def clean_ai_summary_response_util(ai_response, volume_name_context=None, issue_num_context=None):
    if not ai_response: return None
    cleaned = ai_response.strip()
    
    # General boilerplate removal
    cleaned = re.sub(r"^\s*(here's|here is|certainly, here's|sure, here's|okay, here's)\s*a summary:?\s*", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"^\s*summary:\s*", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s*I hope this helps!?.*$", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s*Let me know if you need anything else.*$", "", cleaned, flags=re.I).strip()

    # MODIFICATION: Attempt to remove contextual prefixes related to issue/volume if provided
    if volume_name_context and issue_num_context:
        # Escape special characters in volume name for regex
        escaped_volume_name = re.escape(volume_name_context)
        escaped_issue_num = re.escape(str(issue_num_context))

        # Patterns to remove common introductory phrases with issue context
        # Example: "In Spawn #8, ..." or "Spawn issue #8 features..."
        context_patterns = [
            rf"^\s*In\s+(?:issue\s*)?{escaped_volume_name}\s*(?:issue\s*)?#{escaped_issue_num}[,:]?\s*",
            rf"^\s*{escaped_volume_name}\s*(?:issue\s*)?#{escaped_issue_num}\s*(?:features|begins with|opens with|details|concerns|is about)\s*",
            rf"^\s*The\s+plot\s+of\s+{escaped_volume_name}\s*(?:issue\s*)?#{escaped_issue_num}\s*(?:is|revolves around|centers on)\s*",
            rf"^\s*Issue\s+#?{escaped_issue_num}\s+of\s+{escaped_volume_name}\s*(?:sees|shows|finds)\s*",
            # More generic pattern to catch "In <Title> #<Number> (<Date>): " - less precise
            rf"^\s*In\s+\"[^\"]+\"\s*\(Issue\s*#{escaped_issue_num},\s*\d{{4}}-\d{{2}}-\d{{2}}\)[,:]?\s*",
            rf"^\s*In\s+{escaped_volume_name}\s*\(Issue\s*#{escaped_issue_num},\s*\d{{4}}-\d{{2}}-\d{{2}}\)[,:]?\s*",
        ]
        original_cleaned_length = len(cleaned)
        for pattern in context_patterns:
            cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.I).strip()
        
        if len(cleaned) < original_cleaned_length:
            logger.debug(f"AI summary: Removed contextual prefix. Original start: '{ai_response[:100]}...', New start: '{cleaned[:100]}...'")


    if cleaned != ai_response: # Log if any cleaning happened (original or new)
        logger.debug(f"Cleaned AI summary/generation. Original: '{ai_response[:50]}...', Cleaned: '{cleaned[:50]}...'")
    else:
        logger.debug(f"AI summary/generation needed no significant cleaning beyond initial boilerplate.")
    return cleaned if cleaned else None

def query_mistral_for_summary_util(api_key, text_to_summarize, word_limit, volume_name_context=None, issue_num_context=None):
    if not api_key or not text_to_summarize: return None
    # MODIFICATION: Added instruction to not repeat title/issue info.
    prompt = (
        f"Summarize the following comic book plot description. Your summary MUST be {word_limit} words or fewer. "
        f"Strictly adhere to this {word_limit}-word maximum. Output only the summary text. "
        f"Do NOT repeat the comic title, issue number, or cover date in your summary, focus only on the plot events."
        f"\n\nPlot Description:\n{text_to_summarize}"
    )
    logger.debug(f"Query Mistral Summary (Target: {word_limit} words for '{volume_name_context} #{issue_num_context}')...")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {"model": MISTRAL_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": int(word_limit * 2.5), "temperature": 0.2}
    data = None
    with MISTRAL_API_SEMAPHORE:
        logger.debug(f"Semaphore acquired for summary ({volume_name_context} #{issue_num_context})")
        data = query_mistral_with_retry(MISTRAL_API_URL, headers, payload, REQUEST_TIMEOUT + 10)
        time.sleep(AI_CALL_DELAY_SECONDS)
        logger.debug(f"Semaphore released for summary ({volume_name_context} #{issue_num_context})")
    if data:
        summary = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        if summary:
             logger.debug(f"Mistral Summary OK (Raw for '{volume_name_context} #{issue_num_context}'): '{summary[:150]}...'")
             # Pass context for more specific cleaning
             cleaned_summary = clean_ai_summary_response_util(summary, volume_name_context, issue_num_context)
             return cleaned_summary
        logger.debug(f"Mistral Summary empty/unparsable for '{volume_name_context} #{issue_num_context}'."); return None
    else:
        logger.error(f"Failed to get data from Mistral for summary ({volume_name_context} #{issue_num_context}) after retries.")
        return None

def query_mistral_for_generation_util(api_key, volume_name, issue_num, cover_date, word_limit):
    if not api_key:
        logger.debug("Mistral API key not loaded. Skipping AI generation.")
        return None
    # MODIFICATION: Added instruction to not repeat title/issue info.
    prompt = (
        f"Provide a concise plot summary for {volume_name} issue #{issue_num} ({cover_date}). "
        f"The summary MUST be {word_limit} words or fewer. Strictly adhere to this {word_limit}-word maximum. "
        f"Output only the plot summary text. Do NOT include the title '{volume_name}', issue number '#{issue_num}', or date '{cover_date}' in your response."
    )
    logger.debug(f"Querying Mistral for description generation (Target: {word_limit} words for '{volume_name} #{issue_num}')...");
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {"model": MISTRAL_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": int(word_limit * 2.7), "temperature": 0.2}
    data = None
    with MISTRAL_API_SEMAPHORE:
        logger.debug(f"Semaphore acquired for generation ({volume_name} #{issue_num})")
        data = query_mistral_with_retry(MISTRAL_API_URL, headers, payload, REQUEST_TIMEOUT + 15)
        time.sleep(AI_CALL_DELAY_SECONDS)
        logger.debug(f"Semaphore released for generation ({volume_name} #{issue_num})")
    if data:
        ai_generated_desc = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        if ai_generated_desc:
            logger.debug(f"Mistral generation query finished. Raw response for '{volume_name} #{issue_num}': '{ai_generated_desc[:150]}...'")
            # Pass context for more specific cleaning
            cleaned_desc = clean_ai_summary_response_util(ai_generated_desc, volume_name, issue_num)
            return cleaned_desc
        logger.debug(f"Mistral generation response was empty or unparsable for '{volume_name} #{issue_num}'."); return None
    else:
        logger.error(f"Failed to get data from Mistral for generation ({volume_name} #{issue_num}) after retries.")
        return None

def process_issues_for_platform(
    run_config: 'ComicRunConfig',
    platform_specific_config: 'PlatformConfig',
    issues_data: List[Dict[str, Any]] 
) -> Dict[str, Any]:

    platform_name = platform_specific_config.name
    stats = {
        "status": "INIT", "issues_considered": 0, "covers_dl_ok": 0, "covers_dl_fail": 0,
        "social_created_ok": 0, "social_created_fail": 0, "desc_original": 0,
        "desc_ai_generated": 0, "desc_ai_summarized": 0, "desc_unavailable": 0,
        "ai_summary_queries": 0, "ai_summary_success": 0,
        "ai_summary_fail": 0, "ai_generation_queries": 0, "ai_generation_success": 0,
        "ai_generation_fail": 0,
        "error_message": None
    }

    logger.info(f"--- Starting {platform_name} Processing for: {run_config.title} ({run_config.start_year}-{run_config.end_year}) ---")
    logger.info(f"--- Using pre-determined Volume ID: {run_config.volume_id} ---")
    if run_config.custom_footer_text:
        logger.info(f"--- Custom Footer Text for {platform_name}: '{run_config.custom_footer_text}' ---")
    if run_config.logo_image_path: 
        logger.info(f"--- Custom Logo Path for {platform_name}: '{run_config.logo_image_path}' ---")


    if run_config.mistral_api_key: logger.debug(f"{platform_name}: Mistral API Key available.")
    else: logger.debug(f"{platform_name}: Mistral API Key not available.")

    safe_title = sanitize_filename_util(run_config.title)
    safe_publisher = sanitize_filename_util(run_config.publisher)
    vol_suffix = f"_v{sanitize_filename_util(run_config.volume_number)}" if run_config.volume_number else ""

    base_output_dir_name = f"{safe_title}{vol_suffix}_{safe_publisher}_{run_config.start_year}-{run_config.end_year}"
    
    originals_dir = os.path.join(base_output_dir_name, "Original_Covers")
    social_dir = os.path.join(base_output_dir_name, "Social_Posts")

    try:
        os.makedirs(originals_dir, exist_ok=True)
        os.makedirs(social_dir, exist_ok=True)
        logger.info(f"{platform_name}: Output folders ready: '{base_output_dir_name}'")
    except OSError as e:
        logger.error(f"{platform_name}: Error creating output folders: {e}")
        stats["status"] = "FAILED"; stats["error_message"] = f"Error creating output folders: {e}"
        return stats

    issues_to_process = issues_data

    if not issues_to_process:
        logger.info(f"{platform_name}: No matching issues found (from pre-fetched data). Ending processing.")
        stats["status"] = "SUCCESS"; return stats

    stats["issues_considered"] = len(issues_to_process)
    logger.info(f"{platform_name}: Processing {stats['issues_considered']} issues (from pre-fetched data)...")


    for issue_details in issues_to_process:
        issue_num_raw = issue_details.get('issue_number', 'Unk') # Keep raw for context
        issue_num_for_display = str(issue_num_raw) # For display in logs, etc.
        cv_id = issue_details.get('id', 'NoID')
        cover_date = issue_details.get('cover_date', 'NoDate'); 
        volume_name_for_ai = issue_details.get('volume', {}).get('name', run_config.title) # Fallback to run_config title

        pub_year = "NoDate"
        if cover_date and len(cover_date) >= 4:
             try:
                 if re.match(r"^\d{4}-\d{2}-\d{2}$", cover_date): pub_year = cover_date[:4]
                 elif re.match(r"^\d{4}-\d{2}$", cover_date): pub_year = cover_date[:4]
                 elif re.match(r"^\d{4}$", cover_date): pub_year = cover_date
                 else:
                     try: dt_obj_yr = datetime.strptime(cover_date, '%B %d, %Y'); pub_year = dt_obj_yr.strftime('%Y')
                     except ValueError:
                         try: dt_obj_yr = datetime.strptime(cover_date, '%B %Y'); pub_year = dt_obj_yr.strftime('%Y')
                         except ValueError:
                              try: dt_obj_yr = datetime.strptime(cover_date.split()[0], '%Y'); pub_year = dt_obj_yr.strftime('%Y')
                              except (ValueError, IndexError): logger.debug(f"{platform_name}: Could not reliably extract pub_year from cover_date: {cover_date}"); pub_year="NoDate"
             except Exception as e_date: logger.error(f"{platform_name}: Unexpected error extracting year from cover_date '{cover_date}': {e_date}"); pub_year = "NoDate"

        logger.info("-" * 20)
        logger.info(f"{platform_name}: Processing Issue #{issue_num_for_display} (ID: {cv_id}, Date: {cover_date}, Extracted Year: {pub_year})")

        img_url = None; image_data = issue_details.get('image', None)
        if isinstance(image_data, dict):
            img_url = image_data.get(PREFERRED_IMAGE_QUALITY) or image_data.get('original_url') or \
                      image_data.get('screen_url') or image_data.get('medium_url') or \
                      image_data.get('small_url') or image_data.get('thumb_url') or image_data.get('tiny_url')

        if img_url:
            safe_year = sanitize_filename_util(pub_year); safe_issue_num = sanitize_filename_util(issue_num_for_display)
            file_ext = os.path.splitext(img_url)[1]; valid_ext = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
            save_ext = file_ext.lower() if file_ext.lower() in valid_ext else ".jpg"
            orig_fn = f"{safe_title}{vol_suffix}_{safe_issue_num}_{safe_year}{save_ext}"
            orig_path = os.path.join(originals_dir, orig_fn)
            social_fn_base = f"{platform_specific_config.social_post_filename_prefix}_{safe_title}{vol_suffix}_{safe_issue_num}_{safe_year}"
            social_fn = f"{social_fn_base}{platform_specific_config.social_post_filename_suffix}"
            social_path = os.path.join(social_dir, social_fn)

            if os.path.exists(social_path):
                logger.info(f"{platform_name}: Exists: '{os.path.basename(social_path)}'. Skip.")
                stats["social_created_ok"] += 1
                if os.path.exists(orig_path):
                    stats["covers_dl_ok"] +=1
                else:
                    if download_cover_util(img_url, orig_path):
                        stats["covers_dl_ok"] += 1
                    else:
                        stats["covers_dl_fail"] += 1
                continue

            if download_cover_util(img_url, orig_path):
                stats["covers_dl_ok"] += 1
                raw_desc = issue_details.get('description', '')
                cleaned_desc = clean_html_util(raw_desc or '')
                
                final_desc = "No description available."
                desc_source_type = "unavailable"

                if cleaned_desc:
                    final_desc = cleaned_desc
                    desc_source_type = "original"
                    logger.debug(f"{platform_name}: Initial final_desc from cleaned_desc ({len(final_desc.split())} words).")
                else:
                    logger.debug(f"{platform_name}: No cleaned_desc from Comic Vine, final_desc is '{final_desc}'.")

                if run_config.mistral_api_key:
                    if not cleaned_desc:
                        logger.info(f"{platform_name}: Description missing from CV for {volume_name_for_ai} #{issue_num_for_display}. Attempting AI generation...")
                        stats["ai_generation_queries"] += 1
                        generated_text = query_mistral_for_generation_util(
                            run_config.mistral_api_key, 
                            volume_name_for_ai, 
                            issue_num_raw, # Pass raw issue_num for context
                            cover_date, 
                            platform_specific_config.description_word_limit
                        )
                        if generated_text: # clean_ai_summary_response_util is now called inside query_mistral_for_generation_util
                            final_desc = generated_text
                            desc_source_type = "ai_generated"
                            logger.info(f"{platform_name}: Using AI generated description ({len(final_desc.split())} words) for {volume_name_for_ai} #{issue_num_for_display}.")
                            stats["ai_generation_success"] += 1
                        else:
                            logger.warning(f"{platform_name}: AI generation failed for {volume_name_for_ai} #{issue_num_for_display}.");
                            desc_source_type = "unavailable" 
                            stats["ai_generation_fail"] += 1
                    else: 
                        word_count = len(cleaned_desc.split())
                        if word_count > platform_specific_config.description_word_limit:
                            logger.info(f"{platform_name}: Desc long ({word_count} words) for {volume_name_for_ai} #{issue_num_for_display}. Summarizing..."); 
                            stats["ai_summary_queries"] += 1
                            summary_text = query_mistral_for_summary_util(
                                run_config.mistral_api_key, 
                                cleaned_desc, 
                                platform_specific_config.description_word_limit,
                                volume_name_for_ai, # Pass context for cleaning
                                issue_num_raw       # Pass context for cleaning
                            )
                            if summary_text: # clean_ai_summary_response_util is now called inside query_mistral_for_summary_util
                                final_desc = summary_text
                                desc_source_type = "ai_summarized"
                                logger.info(f"{platform_name}: Using AI summary ({len(final_desc.split())} words) for {volume_name_for_ai} #{issue_num_for_display}.")
                                stats["ai_summary_success"] +=1
                            else:
                                logger.warning(f"{platform_name}: AI summarization failed for {volume_name_for_ai} #{issue_num_for_display}. Using original.");
                                final_desc = cleaned_desc 
                                desc_source_type = "original" 
                                stats["ai_summary_fail"] += 1
                        else: 
                            desc_source_type = "original"
                            logger.info(f"{platform_name}: Using original description for {volume_name_for_ai} #{issue_num_for_display} as it's within word limits ({word_count} words).")
                
                if desc_source_type == "original":
                    stats["desc_original"] += 1
                elif desc_source_type == "ai_generated":
                    stats["desc_ai_generated"] += 1
                elif desc_source_type == "ai_summarized":
                    stats["desc_ai_summarized"] += 1
                elif desc_source_type == "unavailable":
                    stats["desc_unavailable"] += 1

                if final_desc and final_desc.strip() and final_desc not in {"No description available."}:
                    words = final_desc.split()
                    current_word_limit = platform_specific_config.description_word_limit

                    if len(words) > current_word_limit:
                        logger.warning(
                            f"{platform_name}: Description (source: '{desc_source_type}', length: {len(words)} words for {volume_name_for_ai} #{issue_num_for_display}) "
                            f"exceeds limit of {current_word_limit}. Applying hard truncation."
                        )
                        candidate_words = words[:current_word_limit]
                        candidate_desc = " ".join(candidate_words)
                        last_period = candidate_desc.rfind('.')
                        last_question = candidate_desc.rfind('?')
                        last_exclamation = candidate_desc.rfind('!')
                        last_sentence_end_char_index = max(last_period, last_question, last_exclamation)

                        if last_sentence_end_char_index > 0:
                            temp_truncated_desc = candidate_desc[:last_sentence_end_char_index + 1]
                            if len(temp_truncated_desc.split()) > 0 :
                                final_desc = temp_truncated_desc
                                logger.info(f"{platform_name}: Truncated description for {volume_name_for_ai} #{issue_num_for_display} at sentence end: '{final_desc[:100]}...' ({len(final_desc.split())} words)")
                            else:
                                logger.debug(f"{platform_name}: Sentence boundary truncation resulted in too few words for {volume_name_for_ai} #{issue_num_for_display}. Falling back to word count with ellipsis.")
                                if current_word_limit > 1:
                                    final_desc = " ".join(words[:current_word_limit - 1]) + "..."
                                elif current_word_limit == 1 and words:
                                     final_desc = words[0] + "..."
                                else:
                                     final_desc = "..." if words else ""
                                logger.info(f"{platform_name}: Truncated description for {volume_name_for_ai} #{issue_num_for_display} with ellipsis (fallback): '{final_desc[:100]}...' ({len(final_desc.split())} words)")
                        else:
                            logger.debug(f"{platform_name}: No suitable sentence boundary found for truncation for {volume_name_for_ai} #{issue_num_for_display}. Using word count with ellipsis.")
                            if current_word_limit > 1:
                                final_desc = " ".join(words[:current_word_limit - 1]) + "..."
                            elif current_word_limit == 1 and words:
                                 final_desc = words[0] + "..."
                            else:
                                 final_desc = "..." if words else ""
                            logger.info(f"{platform_name}: Truncated description for {volume_name_for_ai} #{issue_num_for_display} with ellipsis: '{final_desc[:100]}...' ({len(final_desc.split())} words)")
                    else:
                        logger.debug(f"{platform_name}: Description (source: '{desc_source_type}', length: {len(words)} words for {volume_name_for_ai} #{issue_num_for_display}) is within limit of {current_word_limit}.")


                logger.debug(f"{platform_name}: PRE-CALL FINAL_DESC for {volume_name_for_ai} #{issue_num_for_display} (len {len(final_desc) if final_desc else 0}): '{str(final_desc)[:100]}...'")
                
                if platform_specific_config.create_social_image_func(run_config, orig_path, issue_details, final_desc, social_path):
                    stats["social_created_ok"] += 1
                else: stats["social_created_fail"] += 1
            else:
                logger.error(f"{platform_name}: Download failed for {volume_name_for_ai} #{issue_num_for_display}, skip social."); stats["covers_dl_fail"] += 1; stats["social_created_fail"] += 1
        else:
            logger.warning(f"{platform_name}: Skipping {volume_name_for_ai} #{issue_num_for_display}: No image URL."); stats["covers_dl_fail"] += 1; stats["social_created_fail"] += 1

    logger.info(f"--- {platform_name} Processing Complete ---")
    stats["status"] = "SUCCESS"
    return stats
# --- END OF MODIFIED FILE utils.py ---