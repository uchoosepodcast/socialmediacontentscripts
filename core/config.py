from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, List

@dataclass
class AppConfig:
    comic_vine_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None

@dataclass
class RunConfig:
    title: str
    publisher: str
    volume_number: str
    start_year: int
    end_year: int
    volume_id: Optional[str] = None
    custom_footer_text: Optional[str] = None
    logo_image_path: Optional[str] = None
    platforms: List[str] = field(default_factory=list)
    sources_priority: List[str] = field(default_factory=lambda: ["comicvine", "marvel", "googlebooks"])

    def __post_init__(self):
        if self.volume_id is not None and not isinstance(self.volume_id, str):
            self.volume_id = str(self.volume_id)
        if self.volume_number is None:
            self.volume_number = ""
        if self.custom_footer_text and len(self.custom_footer_text) > 50:
            self.custom_footer_text = self.custom_footer_text[:50]

@dataclass
class PlatformConfig:
    name: str
    directory_prefix: str
    social_post_filename_prefix: str
    social_post_filename_suffix: str
    description_word_limit: int
    create_social_image_func: Optional[Callable] = None

@dataclass
class IssueMetadata:
    id: str
    issue_number: str
    name: Optional[str]
    cover_date: Optional[str]
    description: Optional[str]
    image_url: Optional[str]
    volume_name: Optional[str] = None
    credits: List[Dict[str, str]] = field(default_factory=list)
    source: str = ""
