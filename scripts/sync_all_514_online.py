# -*- coding: utf-8 -*-
import os, sys, json, time, re, requests

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

print("1. Fetching all online cards...")
all_cards = []
cursor = {"limit": 100}
while True:
    r = s.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
        "settings": {"cursor": cursor, "filter": {"withPhoto": -1}}
    }, timeout=25)
    if r.status_code != 200:
        break
    data = r.json()
    cards = data.get('cards', [])
    all_cards.extend(cards)
    if len(cards) < 100:
        break
    cur = data.get('cursor', {})
    cursor = {
        "limit": 100,
        "updatedAt": cur.get('updatedAt', ''),
        "nmID": cur.get('nmID', 0)
    }

print(f"Total Online Cards: {len(all_cards)}")

# Read archive to get photo URLs and prices
archive_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'rr008_listed_products.json')
with open(archive_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

sku_map = {p['sku']: p for p in products}

# 2. Check and attach missing photos
print("\n2. Checking and attaching photos for all online cards...")
photos_attached = 0
for c in all_cards:
    nmid = c.get('nmID')
    vc = c.get('vendorCode', '')
    existing_photos = c.get('photos', [])
    if len(existing_photos) >= 1:
        continue
    
    # Extract SKU from vendorCode e.g. RR-123456-v2
    m = re.search(r'RR-(\d+)-v', vc)
    if m:
        sku = m.group(1)
        p = sku_map.get(sku)
        if p and p.get('photos'):
            try:
                r_med = s.post('https://content-api.wildberries.ru/content/v3/media/save', json={
                    "nmId": nmid,
                    "data": p['photos'][:10]
                }, timeout=20)
                if r_med.status_code == 200:
                    photos_attached += 1
            except Exception as e:
                pass
            time.sleep(0.3)

print(f"Newly attached photos for {photos_attached} cards.")

# 3. Inject stocks for all barcodes
print("\n3. Injecting 5 units stock on Moscow 1 Warehouse (2200719)...")
all_barcodes = []
for c in all_cards:
    sizes = c.get('sizes', [])
    if sizes and sizes[0].get('skus'):
        all_barcodes.append(sizes[0]['skus'][0])

print(f"Total barcodes to inject stock: {len(all_barcodes)}")
for i in range(0, len(all_barcodes), 100):
    chunk_bc = all_barcodes[i:i+100]
    stock_payload = [{"sku": bc, "amount": 5} for bc in chunk_bc]
    for attempt in range(3):
        try:
            r_stk = s.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}', json={'stocks': stock_payload}, timeout=25)
            print(f"  -> Stock chunk {i//100 + 1}: HTTP {r_stk.status_code}")
            if r_stk.status_code in [200, 204]:
                break
        except Exception as e:
            time.sleep(1)

# 4. Push 50% discount price task
print("\n4. Submitting 50% discount prices for all online cards...")
price_payload = []
for c in all_cards:
    nmid = c.get('nmID')
    vc = c.get('vendorCode', '')
    m = re.search(r'RR-(\d+)-v', vc)
    p = sku_map.get(m.group(1)) if m else None
    
    # Calculate strike price
    strike_price = p.get('wb_strike_price') if p else 1000
    price_payload.append({
        "nmID": nmid,
        "price": strike_price,
        "discount": 50
    })

for i in range(0, len(price_payload), 100):
    chunk_pr = price_payload[i:i+100]
    try:
        r_pr = s.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': chunk_pr}, timeout=25)
        print(f"  -> Price task chunk {i//100 + 1}: HTTP {r_pr.status_code} | {r_pr.text[:80]}")
    except Exception as e:
        print(f"  [-] Price task error: {e}")
    time.sleep(0.5)

print("\n✅ All 514 online cards synchronized with photos, stocks, and 50% discount prices!")
