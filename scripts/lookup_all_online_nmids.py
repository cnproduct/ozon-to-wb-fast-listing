# -*- coding: utf-8 -*-
import os, sys, json, time, requests

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from session_manager import SessionManager

CONVERSATION_ID = "97ac70fb-afa7-4e2b-9dd5-c0853147f357"
mgr = SessionManager()
creds = mgr.get_active_session_credentials(CONVERSATION_ID)
token = creds.get('wb_api_token')
wh_id = int(creds.get('wb_warehouse_id', 2200719))

s = requests.Session()
s.trust_env = False
s.headers.update({
    'Authorization': token,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
})

print("Fetching ALL cards online from Content API...")
all_cards = []
cursor = {"limit": 100}
page = 1
while True:
    r = s.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
        "settings": {"cursor": cursor, "filter": {"withPhoto": -1}}
    }, timeout=25)
    if r.status_code != 200:
        print(f"Error on page {page}: {r.status_code}")
        break
    data = r.json()
    cards = data.get('cards', [])
    all_cards.extend(cards)
    print(f"Page {page}: fetched {len(cards)} cards (total: {len(all_cards)})")
    if len(cards) < 100:
        break
    cur = data.get('cursor', {})
    cursor = {
        "limit": 100,
        "updatedAt": cur.get('updatedAt', ''),
        "nmID": cur.get('nmID', 0)
    }
    page += 1
    time.sleep(0.3)

print(f"\nTotal online cards found: {len(all_cards)}")

online_vc_map = {}
for c in all_cards:
    vc = c.get('vendorCode')
    if vc:
        online_vc_map[vc] = c

archive_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'rr008_listed_products.json')
with open(archive_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

matched_v2 = 0
matched_v1 = 0
unmatched = []

for p in products:
    sku = p.get('sku')
    v2 = f"RR-{sku}-v2"
    v1 = f"RR-{sku}-v1"
    
    if v2 in online_vc_map:
        matched_v2 += 1
        c = online_vc_map[v2]
        p['vendorCode'] = v2
        p['nmID'] = c.get('nmID')
        # match barcode from sizes
        sizes = c.get('sizes', [])
        if sizes and sizes[0].get('skus'):
            p['barcode'] = sizes[0]['skus'][0]
    elif v1 in online_vc_map:
        matched_v1 += 1
        c = online_vc_map[v1]
        p['vendorCode'] = v1
        p['nmID'] = c.get('nmID')
        sizes = c.get('sizes', [])
        if sizes and sizes[0].get('skus'):
            p['barcode'] = sizes[0]['skus'][0]
    else:
        unmatched.append(p)

print(f"\nResults:")
print(f"  Matched v2: {matched_v2}")
print(f"  Matched v1: {matched_v1}")
print(f"  Unmatched: {len(unmatched)}")

with open(archive_path, 'w', encoding='utf-8') as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print("\nArchive updated with online nmIDs and barcodes!")
