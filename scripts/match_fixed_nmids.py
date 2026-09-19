# -*- coding: utf-8 -*-
import os, sys, json, time, requests

SCRIPT_DIR = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts'
sys.path.insert(0, SCRIPT_DIR)
from session_manager import SessionManager

mgr = SessionManager()
creds = mgr.get_active_session_credentials('97ac70fb-afa7-4e2b-9dd5-c0853147f357')
token = creds.get('wb_api_token')
wh_id = int(creds.get('wb_warehouse_id', 2200719))

s = requests.Session()
s.trust_env = False
s.headers.update({
    'Authorization': token,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
})

r_list = s.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
    "settings": {"cursor": {"limit": 100}, "filter": {"withPhoto": -1}}
}, timeout=20)
cards = r_list.json().get('cards', [])

archive_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\rr008_listed_products.json'
with open(archive_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

p_map = {p.get('vendorCode'): p for p in products}

for c in cards:
    vc = c.get('vendorCode')
    if vc in p_map:
        p_map[vc]['nmID'] = c.get('nmID')
        print(f'Matched {vc} -> nmID {c.get("nmID")}')

# Update archive
with open(archive_path, 'w', encoding='utf-8') as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

# Upload media for the 2 fixed cards
for target_vc in ['RR-951893362-v2', 'RR-2924298661-v2']:
    p = p_map.get(target_vc)
    if p and p.get('nmID') and p.get('photos'):
        r_m = s.post('https://content-api.wildberries.ru/content/v3/media/save', json={'nmId': p['nmID'], 'data': p['photos']}, timeout=25)
        print(f"Media upload for {target_vc} (nmID: {p['nmID']}) -> HTTP {r_m.status_code}")
    if p and p.get('barcode'):
        r_stk = s.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}', json={'stocks': [{'sku': p['barcode'], 'amount': 5}]}, timeout=20)
        print(f"Stock for {target_vc} -> HTTP {r_stk.status_code}")
    if p and p.get('nmID'):
        r_pr = s.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': [{'nmID': p['nmID'], 'price': p['wb_strike_price'], 'discount': 50}]}, timeout=20)
        print(f"Prices for {target_vc} -> HTTP {r_pr.status_code}")

