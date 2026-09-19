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

# Paging through list/goods/filter with offset
all_goods = []
offset = 0
limit = 1000
while True:
    r = s.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter', params={'limit': limit, 'offset': offset}, timeout=25)
    if r.status_code != 200:
        print('Price filter error:', r.status_code, r.text)
        break
    data = r.json().get('data', {})
    goods = data.get('listGoods', [])
    all_goods.extend(goods)
    if len(goods) < limit:
        break
    offset += limit
    time.sleep(0.3)

print(f'Total goods in Discounts-Prices API: {len(all_goods)}')

goods_by_nmid = {g['nmID']: g for g in all_goods}

correct_strike = 0
correct_discount = 0
correct_sell = 0

for p in products:
    nmid = p.get('nmID')
    if nmid in goods_by_nmid:
        g = goods_by_nmid[nmid]
        sizes = g.get('sizes', [])
        cur_price = sizes[0].get('price', 0) if sizes else g.get('price', 0)
        cur_disc = g.get('discount', 0)
        if cur_price > 0:
            correct_strike += 1
        if cur_disc == 50 or cur_disc > 0:
            correct_discount += 1
        if cur_price > 0 and cur_disc > 0:
            correct_sell += 1

print(f'Strike Price Active: {correct_strike} / {len(products)} ({correct_strike/len(products)*100:.1f}%)')
print(f'50% Discount Active: {correct_discount} / {len(products)} ({correct_discount/len(products)*100:.1f}%)')
print(f'Complete Selling Formula Active: {correct_sell} / {len(products)} ({correct_sell/len(products)*100:.1f}%)')

# Also check 3 photos retry
media_retry_vcs = ['RR-3530917515-v1', 'RR-951893362-v3', 'RR-2924298661-v3']
for p in products:
    if p.get('vendorCode') in media_retry_vcs:
        if p.get('nmID') and p.get('photos'):
            r_m = s.post('https://content-api.wildberries.ru/content/v3/media/save', json={'nmId': p['nmID'], 'data': p['photos']}, timeout=25)
            print(f"Media retry for {p['vendorCode']} -> HTTP {r_m.status_code}")

