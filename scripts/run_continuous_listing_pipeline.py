# -*- coding: utf-8 -*-
import os
import sys
import re
import json
import time
import glob
from typing import List, Dict, Any, Set

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from parse_batch_utils import parse_pdp_or_features
from execute_rr008_listing import get_wb_session, get_already_listed_cards, format_product_payload, upload_products_batch

TARGET_FILE = os.path.join(r'c:\Users\Administrator\Documents\google drive', 'RR008-09-04-1.txt')
OUTPUT_ARCHIVE = os.path.join(WORKSPACE_DIR, 'rr008_listed_products.json')
BRAIN_ROOT = r'C:\Users\Administrator\.gemini\antigravity\brain'

def load_target_skus() -> List[str]:
    with open(TARGET_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and line.strip().isdigit()]

def load_listed_skus() -> Set[str]:
    if not os.path.exists(OUTPUT_ARCHIVE):
        return set()
    try:
        with open(OUTPUT_ARCHIVE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {str(it.get('sku', '')).strip() for it in data if it.get('sku')}
    except Exception:
        return set()

def scan_and_parse_cached_skus(target_skus: List[str], listed_skus: Set[str]) -> List[Dict[str, Any]]:
    unlisted_set = set(target_skus) - listed_skus
    print(f'Target unlisted SKUs remaining: {len(unlisted_set)}')
    if not unlisted_set:
        return []

    parsed_items = []
    found_skus = set()

    # 1. Also check any parsed json files in batches_remaining or batches_rr008
    json_files = glob.glob(os.path.join(WORKSPACE_DIR, 'batches_remaining', '*parsed.json')) +                  glob.glob(os.path.join(WORKSPACE_DIR, 'batches_rr008', '*parsed.json'))
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                items = json.load(f)
                for it in items:
                    sku = str(it.get('sku', '')).strip()
                    if sku in unlisted_set and sku not in found_skus:
                        if it.get('title') and (it.get('photos') or it.get('ozon_price')):
                            parsed_items.append(it)
                            found_skus.add(sku)
        except Exception:
            pass

    print(f'Parsed from json batch files: {len(parsed_items)} items')

    # 2. Scan all content.md in brain
    content_files = []
    for root, dirs, files in os.walk(BRAIN_ROOT):
        if 'content.md' in files:
            p = os.path.join(root, 'content.md')
            try:
                sz = os.path.getsize(p)
                if sz > 1500:
                    content_files.append((p, sz))
            except Exception:
                pass

    print(f'Total content.md files in brain: {len(content_files)}')

    for p, sz in content_files:
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            m = re.findall(r'ozon\.ru/product/.*?(\d{6,14})', text[:3000])
            if not m:
                m = re.findall(r'/product/(\d{6,14})', text[:3000])
            if not m:
                m = re.findall(r'(\d{6,14})', text[:1000])
            for sku in m:
                if sku in unlisted_set and sku not in found_skus:
                    item = parse_pdp_or_features(sku, text)
                    if item.get('title') and len(item.get('title')) > 3:
                        if not item.get('ozon_price') or item.get('ozon_price') <= 0:
                            item['ozon_price'] = 600.0
                        parsed_items.append(item)
                        found_skus.add(sku)
        except Exception:
            pass

    print(f'Total newly parsed unlisted items ready to upload: {len(parsed_items)}')
    return parsed_items

def run_pipeline_round():
    session, warehouse_id, store_name = get_wb_session()
    print(f'Authenticated session for store: {store_name} (WH: {warehouse_id})')

    target_skus = load_target_skus()
    listed_skus = load_listed_skus()
    print(f'Target total: {len(target_skus)} | Already archived: {len(listed_skus)}')

    parsed_items = scan_and_parse_cached_skus(target_skus, listed_skus)
    if not parsed_items:
        print('No new parsed items available in this round.')
        return 0

    to_upload = []
    already_live = get_already_listed_cards(session)
    for raw in parsed_items:
        p = format_product_payload(raw, multiplier=6.0)
        if p['vendorCode'] not in already_live:
            to_upload.append(p)

    print(f'Ready to upload to WB: {len(to_upload)} items')
    if not to_upload:
        print('Items already live on WB, updating archive...')
        archived = []
        if os.path.exists(OUTPUT_ARCHIVE):
            with open(OUTPUT_ARCHIVE, 'r', encoding='utf-8') as f:
                archived = json.load(f)
        existing = {it['sku'] for it in archived}
        for raw in parsed_items:
            p = format_product_payload(raw, multiplier=6.0)
            p['barcode'] = 'N/A'
            p['nmID'] = already_live.get(p['vendorCode'])
            if p['sku'] not in existing:
                archived.append(p)
                existing.add(p['sku'])
        with open(OUTPUT_ARCHIVE, 'w', encoding='utf-8') as f:
            json.dump(archived, f, ensure_ascii=False, indent=2)
        return 0

    batch_size = 25
    total_uploaded = 0
    for i in range(0, len(to_upload), batch_size):
        chunk = to_upload[i:i+batch_size]
        res = upload_products_batch(chunk, session, warehouse_id)
        total_uploaded += len(res)
        time.sleep(2)

    return total_uploaded

if __name__ == '__main__':
    run_pipeline_round()
