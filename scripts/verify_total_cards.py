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

print('Checking cards/error/list now...')
r_err = s.post('https://content-api.wildberries.ru/content/v2/cards/error/list', json={}, timeout=20)
print('Current error queue:', r_err.json())

# Check cards list
all_cards = []
cursor = {'limit': 100}
while True:
    r = s.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
        'settings': {'cursor': cursor, 'filter': {'withPhoto': -1}}
    }, timeout=25)
    if r.status_code != 200:
        break
    data = r.json()
    cards = data.get('cards', [])
    all_cards.extend(cards)
    if len(cards) < 100:
        break
    cur = data.get('cursor', {})
    cursor = {'limit': 100, 'updatedAt': cur.get('updatedAt', ''), 'nmID': cur.get('nmID', 0)}
    time.sleep(0.3)

print(f'Total online cards in store RR008: {len(all_cards)}')

archive_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\rr008_listed_products.json'
with open(archive_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

p_map = {p.get('vendorCode'): p for p in products}

for c in all_cards:
    vc = c.get('vendorCode')
    if vc in p_map:
        p_map[vc]['nmID'] = c.get('nmID')

with open(archive_path, 'w', encoding='utf-8') as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

matched = sum(1 for p in products if p.get('nmID'))
print(f'Matched products with nmIDs: {matched} / {len(products)}')

