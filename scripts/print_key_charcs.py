# -*- coding: utf-8 -*-
import json, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

ref_file = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\references\wb_charcs_schemas.json'
with open(ref_file, 'r', encoding='utf-8') as f:
    schema_map = json.load(f)

for sid in ['1594', '2257', '249', '475', '3659', '5251', '3741', '940']:
    charcs = schema_map.get(sid, [])
    print(f"\n==================== Subject {sid} ({len(charcs)} characteristics) ====================")
    for c in charcs:
        cid = c.get('charcID')
        name = c.get('name')
        max_c = c.get('maxCount')
        unit = c.get('unitName', '')
        if cid < 1000000: # filter out internal IDs
            print(f"  ID: {cid:6d} | max: {max_c:2d} | unit: '{unit:3s}' | '{name}'")
