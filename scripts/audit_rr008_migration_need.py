# -*- coding: utf-8 -*-
import json, os, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

archive_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\rr008_listed_products.json'
with open(archive_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

from categorize_all_rr008 import determine_correct_subject

correct_count = 0
migration_needed = []

for p in products:
    current_sid = p.get('subjectID')
    correct_info = determine_correct_subject(p.get('title', ''))
    target_sid = correct_info.get('subjectID')
    
    if current_sid == target_sid:
        correct_count += 1
    else:
        p_copy = dict(p)
        p_copy['target_subjectID'] = target_sid
        p_copy['target_subjectName'] = correct_info.get('subjectName')
        migration_needed.append(p_copy)

print(f"Total Products: {len(products)}")
print(f"Already in Correct Subject: {correct_count}")
print(f"Need Migration: {len(migration_needed)}")

by_target = {}
for m in migration_needed:
    t_name = f"{m['target_subjectID']}: {m['target_subjectName']}"
    by_target.setdefault(t_name, []).append(m)

print("\n--- Migration Needed Breakdown by Target Category ---")
for t_name, items in sorted(by_target.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"  • {t_name}: {len(items)} items (Currently in {items[0].get('subjectID')})")
