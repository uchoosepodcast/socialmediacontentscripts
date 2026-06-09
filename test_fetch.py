import os
import json
import requests

cv_key = ""
try:
    with open(r"api_key.txt", 'r', encoding='utf-8') as f:
        cv_key = f.readline().strip()
except Exception:
    pass

if not cv_key:
    cv_key = os.environ.get("COMIC_VINE_API_KEY", "")

url = f"https://comicvine.gamespot.com/api/issues/?api_key={cv_key}&format=json&filter=volume:45404,issue_number:25&field_list=id,issue_number,name,person_credits"

headers = {'User-Agent': 'ComicSocialCreator/2.0 PythonScript'}
response = requests.get(url, headers=headers)
print(json.dumps(response.json(), indent=2))
