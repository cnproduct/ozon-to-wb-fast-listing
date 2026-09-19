# -*- coding: utf-8 -*-
import json, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

with open(r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\rr008_listed_products.json', 'r', encoding='utf-8') as f:
    products = json.load(f)

sys.path.insert(0, r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts')
from migrate_rr008_categories import format_migration_payload

passed = 0
failed = 0
by_subj = {}
for p in products:
    try:
        mp = format_migration_payload(p)
        passed += 1
        s_name = f"{mp['subjectID']}: {mp['subjectName']}"
        by_subj.setdefault(s_name, []).append(mp)
    except Exception as e:
        failed += 1
        print(f"Error on SKU {p.get('sku')}: {e}")

print(f"\nVerification Results: Passed: {passed} / {len(products)}, Failed: {failed}")
print("\nNew Subject Distribution:")
for s, items in sorted(by_subj.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"  • {s}: {len(items)} items")
