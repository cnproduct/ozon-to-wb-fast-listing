# -*- coding: utf-8 -*-
import json, sys, os, time, requests

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

sys.path.insert(0, r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts')
from wb_uploader import WildberriesAPIClient

client = WildberriesAPIClient()

subjects_to_inspect = [1594, 2257, 1436, 249, 475, 3659, 5251, 3741, 940, 1274, 511, 384, 812, 983, 1952]

ref_file = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\references\wb_charcs_schemas.json'
if os.path.exists(ref_file):
    with open(ref_file, 'r', encoding='utf-8') as f:
        schema_map = json.load(f)
else:
    schema_map = {}

for sid in subjects_to_inspect:
    sid_str = str(sid)
    if sid_str in schema_map and schema_map[sid_str]:
        print(f"Subject {sid} already cached ({len(schema_map[sid_str])} charcs)")
        continue
    
    time.sleep(0.6)
    url = f'https://content-api.wildberries.ru/content/v2/object/charcs/{sid}'
    r = client.session.get(url)
    if r.status_code == 200:
        data = r.json().get('data', [])
        print(f"=== Subject {sid} Characteristics ({len(data)} available) ===")
        schema_map[sid_str] = data
    else:
        print(f"Failed to fetch for {sid}: {r.status_code}")

with open(ref_file, 'w', encoding='utf-8') as f:
    json.dump(schema_map, f, ensure_ascii=False, indent=2)

print("\nSuccessfully updated all schemas to references/wb_charcs_schemas.json")
