import os
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'scripts')
from parse_batch_06 import parse_item

steps_dir = r"C:\Users\Administrator\.gemini\antigravity\brain\9156122e-90c7-4c9f-b786-d7db068e7c1d\.system_generated\steps"

sku_step_map = [
    ("3879961068", 20, 36),
    ("4227555683", 72, None),
    ("398463464", 73, None),
    ("2365331552", 74, None),
    ("4308889892", 75, None),
    ("5380247988", 76, None),
    ("976171147", 77, None),
    ("5382566242", 78, None),
    ("1423221240", 79, None),
    ("4831125625", 81, None),
    ("3507652443", 82, None),
    ("4829896188", 83, None),
    ("170756267", 84, None),
    ("2797173283", 85, None),
    ("1744662863", 86, None),
    ("3517839275", 87, None),
    ("1897473836", 88, 104),
    ("2040092908", 90, None),
    ("5353631663", 91, None),
    ("2259821852", 92, 105),
    ("1919411699", 93, None),
    ("2829215330", 94, None),
    ("2137254259", 95, None),
    ("3047783043", 96, None),
    ("4549751827", 97, 106),
]

parsed_items = []

for sku, pdp_step, feat_step in sku_step_map:
    pdp_html = ""
    feat_html = ""
    
    if pdp_step:
        p_path = os.path.join(steps_dir, str(pdp_step), "content.md")
        if os.path.exists(p_path):
            with open(p_path, "r", encoding="utf-8", errors="ignore") as f:
                pdp_html = f.read()
    
    if feat_step:
        f_path = os.path.join(steps_dir, str(feat_step), "content.md")
        if os.path.exists(f_path):
            with open(f_path, "r", encoding="utf-8", errors="ignore") as f:
                feat_html = f.read()

    item = parse_item(sku, pdp_html, feat_html)
    parsed_items.append(item)
    print(f"SKU: {sku:10} | Price: {item['ozon_price']:7.1f} | Photos: {len(item['photos']):2} | Brand: {item['brand'][:15]:15} | Title: {item['title'][:50]}")

out_path = r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\batches_remaining\rem_batch_06_parsed.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(parsed_items, f, ensure_ascii=False, indent=2)

print(f"\nSuccessfully wrote {len(parsed_items)} parsed products to {out_path}")
