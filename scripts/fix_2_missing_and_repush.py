# -*- coding: utf-8 -*-
import os, sys, json, time, requests, re

SCRIPT_DIR = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts'
sys.path.insert(0, SCRIPT_DIR)
from session_manager import SessionManager
from execute_rr008_listing import clean_text

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

# Fix 951893362 and 2924298661
p_map = {p['sku']: p for p in products}

# 1. Fix 951893362
p1 = p_map.get('951893362')
if p1:
    p1['vendorCode'] = 'RR-951893362-v2'
    p1['description'] = 'Комплект сменных кассет для фильтров-кувшинов. Эффективная очистка воды от примесей и хлора. Подходит для ежедневного использования.'
    p1['subjectID'] = 3741
    p1['characteristics'] = [
        {"id": 746, "name": "Совместимость", "value": ["универсальная", "для фильтров"]},
        {"id": 14177451, "name": "Комплектация", "value": ["сменные картриджи 3 шт"]},
        {"id": 17596, "name": "Материал изделия", "value": ["пищевой пластик"]}
    ]

# 2. Fix 2924298661
p2 = p_map.get('2924298661')
if p2:
    p2['vendorCode'] = 'RR-2924298661-v2'
    p2['description'] = 'Эспандер для груди и плечевого пояса. Надежный пружинный тренажер для домашних тренировок и фитнеса. Регулируемая нагрузка, качественные материалы.'
    p2['subjectID'] = 618  # Эспандеры
    p2['characteristics'] = [
        {"id": 640, "name": "Спортивное назначение", "value": ["фитнес", "воркаут", "тяжелая атлетика"]},
        {"id": 17596, "name": "Материал изделия", "value": ["сталь", "термопластичный эластомер", "abs пластик"]},
        {"id": 14177451, "name": "Комплектация", "value": ["эспандер"]}
    ]

to_fix = [p for p in [p1, p2] if p]

# Get new barcodes
r_bc = s.post('https://content-api.wildberries.ru/content/v2/barcodes', json={'count': len(to_fix)}, timeout=20)
barcodes = r_bc.json().get('data', [])
for idx, p in enumerate(to_fix):
    p['barcode'] = barcodes[idx]

cards_payload = []
for p in to_fix:
    cards_payload.append({
        "subjectID": p['subjectID'],
        "variants": [
            {
                "vendorCode": p['vendorCode'],
                "title": p['title'],
                "description": p['description'],
                "brand": "",
                "dimensions": {
                    "length": p['length_cm'],
                    "width": p['width_cm'],
                    "height": p['height_cm'],
                    "weightBrutto": p['weightBrutto'],
                    "isValid": True
                },
                "characteristics": p['characteristics'],
                "sizes": [
                    {
                        "techSize": "0",
                        "wbSize": "",
                        "price": p['wb_strike_price'],
                        "skus": [p['barcode']]
                    }
                ]
            }
        ]
    })

print('Uploading fixed cards...')
r_up = s.post('https://content-api.wildberries.ru/content/v2/cards/upload', json=cards_payload, timeout=25)
print('Upload response:', r_up.status_code, r_up.text)

# Poll nmIDs
nmid_map = {}
for attempt in range(1, 15):
    time.sleep(3)
    r_list = s.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
        "settings": {"cursor": {"limit": 100}, "filter": {"withPhoto": -1}}
    }, timeout=20)
    cards = r_list.json().get('cards', [])
    for c in cards:
        vc = c.get('vendorCode', '')
        for p in to_fix:
            if vc == p['vendorCode']:
                nmid_map[vc] = c.get('nmID')
                p['nmID'] = c.get('nmID')
    print(f'Poll {attempt}/15 matched nmIDs: {len(nmid_map)}/{len(to_fix)}')
    if len(nmid_map) == len(to_fix):
        break

# Upload media for fixed cards and all 591
print('Uploading media for fixed cards...')
for p in to_fix:
    if p.get('nmID') and p.get('photos'):
        r_m = s.post('https://content-api.wildberries.ru/content/v3/media/save', json={'nmId': p['nmID'], 'data': p['photos']}, timeout=25)
        print(f"Media for {p['sku']} -> HTTP {r_m.status_code}")

# Inject stocks
stocks = [{'sku': p['barcode'], 'amount': 5} for p in to_fix if p.get('barcode')]
if stocks:
    r_stk = s.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}', json={'stocks': stocks}, timeout=20)
    print('Stock update HTTP:', r_stk.status_code)

# Prices
pr_payload = [{'nmID': p['nmID'], 'price': p['wb_strike_price'], 'discount': 50} for p in to_fix if p.get('nmID')]
if pr_payload:
    r_pr = s.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': pr_payload}, timeout=20)
    print('Prices update HTTP:', r_pr.status_code)

# Update archive
with open(archive_path, 'w', encoding='utf-8') as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print('Archive updated successfully!')
