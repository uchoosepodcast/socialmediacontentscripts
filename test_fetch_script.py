import os
import sys
import tempfile
from core.config import AppConfig, RunConfig
from core.data_fetcher import PipelineFetcher
from core.image_renderer import ImageRenderer

cv_key = ""
try:
    with open(r"api_key.txt", 'r', encoding='utf-8') as f:
        cv_key = f.readline().strip()
except Exception:
    pass
if not cv_key:
    cv_key = os.environ.get("COMIC_VINE_API_KEY", "")

app_config = AppConfig(comic_vine_api_key=cv_key)
fetcher = PipelineFetcher(app_config, ["comicvine"])

# Use Spawn volume ID: 45404
issues = fetcher.fetch_issues("45404", "1994-01-01", "1994-12-31")

target_issue = None
for iss in issues:
    if iss.issue_number == "25":
        target_issue = iss
        break

if target_issue:
    print(f"Found issue: {target_issue.name}")
    print(f"Credits: {target_issue.credits}")
else:
    print("Issue not found")
