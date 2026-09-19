# -*- coding: utf-8 -*-
import json
import os

fpath = r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\batches_remaining\rem_batch_13_parsed.json"

with open(fpath, "r", encoding="utf-8") as f:
    items = json.load(f)

print(f"Total parsed items: {len(items)}")

anomalies = []
for i, item in enumerate(items, 1):
    sku = item.get("sku")
    title = item.get("title")
    price = item.get("ozon_price")
    brand = item.get("brand")
    photos = item.get("photos", [])
    desc = item.get("description")
    cat = item.get("category_path")
    
    issues = []
    if not title:
        issues.append("MISSING_TITLE")
    if not price or price <= 0:
        issues.append(f"INVALID_PRICE({price})")
    if not photos or len(photos) == 0:
        issues.append("NO_PHOTOS")
    if not desc:
        issues.append("EMPTY_DESC")
    if not cat:
        issues.append("EMPTY_CATEGORY")
        
    print(f"[{i:02d}] SKU: {sku} | Price: {price} | Photos: {len(photos)} | Brand: '{brand}' | Issues: {issues or 'OK'}")
    if issues:
        anomalies.append((sku, issues))

print("\nSummary of anomalies:", anomalies)
