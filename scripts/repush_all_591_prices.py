# -*- coding: utf-8 -*-
import os, sys, json, time, requests

SCRIPT_DIR = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts'
sys.path.insert(0, SCRIPT_DIR)
from session_manager import SessionManager

mgr = SessionManager()
creds = mgr.get_active_session_credentials('97ac70fb-afa7-4e2b-9dd5-c0853147f357')
token = creds.get('wb_api_token')

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

# Upload all in chunks of 500
payload = [{'nmID': p['nmID'], 'price': p['wb_strike_price'], 'discount': 50} for p in products if p.get('nmID')]
print(f'Submitting 50% discount and strike price for all {len(payload)} products...')

for i in range(0, len(payload), 500):
    chunk = payload[i:i+500]
    r = s.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': chunk}, timeout=25)
    print(f'Upload chunk {i//500 + 1} -> HTTP {r.status_code} | {r.text}')

print('Done!')
