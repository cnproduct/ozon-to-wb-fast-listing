# -*- coding: utf-8 -*-
import sys, os, json, time, requests

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

sys.path.insert(0, r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts')
from wb_uploader import WildberriesAPIClient

client = WildberriesAPIClient()

all_subjects = []
offset = 0
limit = 1000

print("Fetching full Wildberries official category database...")
while True:
    r = client.session.get('https://content-api.wildberries.ru/content/v2/object/all', params={'limit': limit, 'offset': offset})
    if r.status_code != 200:
        print(f"Error fetching offset {offset}: {r.status_code} {r.text}")
        break
    data = r.json().get('data', [])
    if not data:
        break
    all_subjects.extend(data)
    print(f"Fetched {len(data)} subjects (total: {len(all_subjects)})...")
    if len(data) < limit:
        break
    offset += limit
    time.sleep(0.2)

ref_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\references\wb_all_subjects.json'
os.makedirs(os.path.dirname(ref_path), exist_ok=True)
with open(ref_path, 'w', encoding='utf-8') as f:
    json.dump(all_subjects, f, ensure_ascii=False, indent=2)

print(f"\nSuccessfully saved {len(all_subjects)} official WB subjects to {ref_path}")
