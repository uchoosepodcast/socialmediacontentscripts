import logging
import requests
import time
import json
import hashlib
from typing import List, Dict, Any, Optional
from core.config import AppConfig, IssueMetadata

logger = logging.getLogger(__name__)

import re

def summarize_description(api_key: str, text: str, word_limit: int = 40) -> Optional[str]:
    if not api_key or not text:
        return text

    MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
    prompt = (
        f"Summarize the following comic book plot description. Your summary MUST be {word_limit} words or fewer. "
        f"Strictly adhere to this {word_limit}-word maximum. Output only the summary text. "
        f"Do NOT repeat the comic title, issue number, or cover date in your summary, focus only on the plot events."
        f"\n\nPlot Description:\n{text}"
    )

    payload = {
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": int(word_limit * 2.5),
        "temperature": 0.2
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(MISTRAL_API_URL, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        summary = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        if summary:
            cleaned = re.sub(r"^\s*(here's|here is|certainly, here's|sure, here's|okay, here's)\s*a summary:?\s*", "", summary, flags=re.I).strip()
            cleaned = re.sub(r"^\s*summary:\s*", "", cleaned, flags=re.I).strip()
            return cleaned
    except Exception as e:
        logger.error(f"Mistral API request failed: {e}")

    return text

class DataFetcher:
    def __init__(self, config: AppConfig):
        self.config = config

    def find_volume_id(self, title: str, publisher: str, start_year: int) -> List[Dict[str, Any]]:
        return []

    def fetch_issues(self, volume_id: str, start_date: str, end_date: str) -> List[IssueMetadata]:
        return []

    def fetch_issue_details(self, issue: IssueMetadata) -> IssueMetadata:
        return issue

class ComicVineProvider(DataFetcher):
    BASE_URL = "https://comicvine.gamespot.com/api"

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.api_key = config.comic_vine_api_key
        self.headers = {'User-Agent': 'ComicSocialCreator/2.0 PythonScript'}
        self.delay = 1.1 # 1 request per second
        self.last_request_time = 0

    def _rate_limit(self):
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.error("Comic Vine API key is missing.")
            return None

        params['api_key'] = self.api_key
        params['format'] = 'json'

        self._rate_limit()
        try:
            url = f"{self.BASE_URL}/{endpoint}/"
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get('error') != 'OK':
                logger.error(f"Comic Vine Error: {data.get('error')}")
                return None
            return data
        except Exception as e:
            logger.error(f"Comic Vine API request failed: {e}")
            return None

    def find_volume_id(self, title: str, publisher: str, start_year: int) -> List[Dict[str, Any]]:
        params = {'resources': 'volume', 'query': title, 'limit': 25}
        data = self._make_request('search', params)
        if not data:
            return []

        results = data.get('results', [])
        candidates = []

        for vol in results:
            pub_name = vol.get('publisher', {}).get('name', '')
            if pub_name and publisher.lower() in pub_name.lower():
                try:
                    vol_year = int(vol.get('start_year', 0))
                    if vol_year <= start_year:
                        candidates.append({
                            'id': str(vol.get('id')),
                            'name': vol.get('name', 'Unknown'),
                            'start_year': vol_year,
                            'publisher': pub_name,
                            'source': 'comicvine'
                        })
                except ValueError:
                    pass

        return candidates

    def fetch_issues(self, volume_id: str, start_date: str, end_date: str) -> List[IssueMetadata]:
        field_list = "id,issue_number,name,cover_date,volume,description,image,person_credits"
        date_filter = f"{start_date}|{end_date}"
        params = {
            'filter': f"volume:{volume_id},cover_date:{date_filter}",
            'sort': 'cover_date:asc,issue_number:asc',
            'field_list': field_list,
            'limit': 100
        }

        data = self._make_request('issues', params)
        if not data:
            return []

        issues = []
        for issue_dict in data.get('results', []):
            img_url = issue_dict.get('image', {}).get('super_url') or issue_dict.get('image', {}).get('original_url')

            credits = []
            for credit in issue_dict.get('person_credits', []):
                credits.append({
                    'name': credit.get('name'),
                    'role': credit.get('role')
                })

            issues.append(IssueMetadata(
                id=str(issue_dict.get('id')),
                issue_number=issue_dict.get('issue_number', ''),
                name=issue_dict.get('name'),
                cover_date=issue_dict.get('cover_date'),
                description=issue_dict.get('description'),
                image_url=img_url,
                volume_name=issue_dict.get('volume', {}).get('name'),
                credits=credits,
                source='comicvine'
            ))

        return issues

class MarvelProvider(DataFetcher):
    BASE_URL = "https://gateway.marvel.com/v1/public"

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.public_key = config.marvel_public_key
        self.private_key = config.marvel_private_key

    def _get_auth_params(self) -> Dict[str, str]:
        if not self.public_key or not self.private_key:
            return {}
        ts = str(int(time.time()))
        hash_str = ts + self.private_key + self.public_key
        hash_md5 = hashlib.md5(hash_str.encode('utf-8')).hexdigest()
        return {
            'ts': ts,
            'apikey': self.public_key,
            'hash': hash_md5
        }

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        auth = self._get_auth_params()
        if not auth:
            logger.warning("Marvel API keys missing.")
            return None

        params.update(auth)
        try:
            url = f"{self.BASE_URL}/{endpoint}"
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Marvel API request failed: {e}")
            return None

    def fetch_issue_details(self, issue: IssueMetadata) -> IssueMetadata:
        # Specialized fallback to grab high res cover and description
        if not issue.name and not issue.volume_name:
            return issue

        title_query = f"{issue.volume_name or ''} {issue.name or ''}".strip()
        params = {
            'titleStartsWith': title_query[:50], # Marvel limits title search
            'issueNumber': issue.issue_number,
            'limit': 1
        }

        data = self._make_request('comics', params)
        if not data or not data.get('data', {}).get('results'):
            return issue

        marvel_issue = data['data']['results'][0]

        # High fidelity description
        if marvel_issue.get('description'):
            issue.description = marvel_issue['description']
            issue.source = 'marvel'

        # High fidelity image
        images = marvel_issue.get('images', [])
        if images:
            img = images[0]
            issue.image_url = f"{img['path']}.{img['extension']}"
            issue.source = 'marvel'

        return issue

class GoogleBooksProvider(DataFetcher):
    BASE_URL = "https://www.googleapis.com/books/v1/volumes"

    def fetch_issue_details(self, issue: IssueMetadata) -> IssueMetadata:
        query = f"intitle:{issue.volume_name or ''} issue {issue.issue_number}"
        params = {'q': query, 'maxResults': 1}

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                volume_info = data['items'][0].get('volumeInfo', {})
                if volume_info.get('description'):
                    issue.description = volume_info['description']
                    issue.source = 'googlebooks'

        except Exception as e:
            logger.error(f"Google Books API request failed: {e}")

        return issue

class PipelineFetcher:
    def __init__(self, config: AppConfig, priorities: List[str]):
        self.config = config
        self.providers = {}
        if "comicvine" in priorities:
            self.providers["comicvine"] = ComicVineProvider(config)
        if "marvel" in priorities:
            self.providers["marvel"] = MarvelProvider(config)
        if "googlebooks" in priorities:
            self.providers["googlebooks"] = GoogleBooksProvider(config)

        self.priorities = priorities

    def find_volume_id(self, title: str, publisher: str, start_year: int) -> List[Dict[str, Any]]:
        for source in self.priorities:
            provider = self.providers.get(source)
            if provider:
                results = provider.find_volume_id(title, publisher, start_year)
                if results:
                    return results
        return []

    def fetch_issues(self, volume_id: str, start_date: str, end_date: str, publisher: str = "") -> List[IssueMetadata]:
        # Baseline is always Comic Vine for the bulk list if possible, or whatever is first
        issues = []
        # Fallback cascade to find a provider that can bulk fetch
        for provider_name in self.priorities:
            provider = self.providers.get(provider_name)
            if provider:
                issues = provider.fetch_issues(volume_id, start_date, end_date)
                if issues:
                    break

        # Enhance with fallbacks if data is missing
        for issue in issues:
            if not issue.description or not issue.image_url:
                for fallback_source in self.priorities[1:]:
                    provider = self.providers.get(fallback_source)
                    if provider:
                        # Only use marvel fallback for Marvel comics
                        if fallback_source == "marvel" and "marvel" not in publisher.lower():
                            continue

                        issue = provider.fetch_issue_details(issue)
                        if issue.description and issue.image_url:
                            break # Found what we needed

            # Use Mistral to summarize description if configured
            if issue.description and self.config.mistral_api_key:
                logger.info(f"Summarizing description for issue {issue.issue_number}...")
                summarized = summarize_description(self.config.mistral_api_key, issue.description, word_limit=45)
                if summarized:
                    issue.description = summarized

        return issues
