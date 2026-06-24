import logging
import requests
import time
import json
import hashlib
from typing import List, Dict, Any, Optional
from core.config import AppConfig, IssueMetadata

logger = logging.getLogger(__name__)

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
    BASE_URL = "https://marvel.emreparker.com/v1"

    def __init__(self, config: AppConfig):
        super().__init__(config)

    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Optional[Any]:
        if params is None:
            params = {}
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
            'q': title_query
        }

        # First, search for the issue
        search_results = self._make_request('search/issues', params)
        if not search_results or not isinstance(search_results, list):
            return issue

        matched_issue_id = None
        for item in search_results:
            if str(item.get('issueNumber')) == str(issue.issue_number):
                matched_issue_id = item.get('id')
                break

        if not matched_issue_id:
            return issue

        # Next, fetch the full issue details by ID
        marvel_issue = self._make_request(f'issues/{matched_issue_id}')
        if not marvel_issue:
            return issue

        # High fidelity description
        if marvel_issue.get('description'):
            issue.description = marvel_issue['description']
            issue.source = 'marvel'

        # High fidelity image
        cover = marvel_issue.get('cover')
        if cover and cover.get('path') and cover.get('extension'):
            issue.image_url = f"{cover['path']}.{cover['extension']}"
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
        primary = self.providers.get(self.priorities[0])
        if primary:
            issues = primary.fetch_issues(volume_id, start_date, end_date)

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

        return issues
