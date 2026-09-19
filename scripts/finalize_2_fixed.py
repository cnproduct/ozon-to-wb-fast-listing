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

archive_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\rr008_listed_products.json'
with open(archive_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

p_map = {p.get('vendorCode'): p for p in products}

print('Polling cards list for the 2 newly fixed cards...')
for attempt in range(1, 10):
    time.sleep(3)
    r = s.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
        'settings': {'cursor': {'limit': 100}, 'filter': {'withPhoto': -1}}
    }, timeout=20)
    cards = r.json().get('cards', [])
    matched = 0
    for target_vc in ['RR-951893362-v3', 'RR-2924298661-v3']:
        for c in cards:
            if c.get('vendorCode') == target_vc:
                p_map[target_vc]['nmID'] = c.get('nmID')
                matched += 1
                break
    print(f'Attempt {attempt}/10: matched {matched}/2')
    if matched == 2:
        break

# Attach media, stocks, prices
for target_vc in ['RR-951893362-v3', 'RR-2924298661-v3']:
    p = p_map.get(target_vc)
    if p and p.get('nmID'):
        nmid = p['nmID']
        if p.get('photos'):
            r_m = s.post('https://content-api.wildberries.ru/content/v3/media/save', json={'nmId': nmid, 'data': p['photos']}, timeout=25)
            print(f'Media upload for {target_vc} (nmID: {nmid}) -> HTTP {r_m.status_code}')
        if p.get('barcode'):
            r_stk = s.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}', json={'stocks': [{'sku': p['barcode'], 'amount': 5}]}, timeout=20)
            print(f'Stock update for {target_vc} -> HTTP {r_stk.status_code}')
        r_pr = s.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': [{'nmID': nmid, 'price': p['wb_strike_price'], 'discount': 50}]}, timeout=20)
        print(f'Price update for {target_vc} -> HTTP {r_pr.status_code}')

# Update archive
with open(archive_path, 'w', encoding='utf-8') as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print('Updated archive.')
