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

p_map = {p['sku']: p for p in products}

# 1. 951893362
p1 = p_map.get('951893362')
p1['vendorCode'] = 'RR-951893362-v3'
p1['subjectID'] = 3741
p1['description'] = 'Комплект сменных кассет для фильтров-кувшинов. Качественная очистка питьевой воды от примесей и запахов.'
p1['characteristics'] = [
    {"id": 746, "name": "Совместимость", "value": ["универсальная", "для фильтров"]},
    {"id": 14177451, "name": "Страна производства", "value": ["Китай"]},
    {"id": 17596, "name": "Материал изделия", "value": ["пищевой пластик"]}
]

# 2. 2924298661
p2 = p_map.get('2924298661')
p2['vendorCode'] = 'RR-2924298661-v3'
p2['subjectID'] = 249
p2['description'] = 'Эспандер плечевой и грудной пружинный. Эффективный тренажер для развития мышц груди, рук и спины.'
p2['characteristics'] = [
    {"id": 640, "name": "Спортивное назначение", "value": ["фитнес", "бег", "воркаут"]},
    {"id": 14177451, "name": "Страна производства", "value": ["Китай"]},
    {"id": 17596, "name": "Материал изделия", "value": ["сталь", "термопластичный эластомер"]}
]

to_fix = [p1, p2]

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

# Update archive
with open(archive_path, 'w', encoding='utf-8') as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print('Updated local archive.')
