# -*- coding: utf-8 -*-
import json, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

ref_file = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\references\wb_charcs_schemas.json'
with open(ref_file, 'r', encoding='utf-8') as f:
    schema_map = json.load(f)

for sid in ['1594', '2257', '249', '475', '3659', '5251', '3741', '940', '1274', '511', '384', '812', '983', '1952']:
    charcs = schema_map.get(sid, [])
    print(f"\n==================== Subject {sid} ({len(charcs)} characteristics) ====================")
    for c in charcs:
        print(f"  ID: {c.get('charcID')} | Name: '{c.get('name')}' | req: {c.get('required')} | maxCount: {c.get('maxCount')} | unit: '{c.get('unitName')}'")
