# -*- coding: utf-8 -*-
import requests, json, sys, os, time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_manager import SessionManager
from morphology_engine import PhysicalMorphologyEngine

mgr = SessionManager()
token = mgr.get_active_session_credentials()['wb_api_token']
headers = {'Authorization': token, 'Content-Type': 'application/json'}

r_cards = requests.post(
    'https://content-api.wildberries.ru/content/v2/get/cards/list',
    headers=headers,
    json={'settings': {'cursor': {'limit': 100}, 'filter': {'withPhoto': -1}}}
)
cards = r_cards.json().get('cards', [])
print(f"Total live cards: {len(cards)}")

success_count = 0
failed_count = 0

for c in cards:
    nm = c.get('nmID')
    vc = c.get('vendorCode')
    title = c.get('title', '')
    dims = c.get('dimensions', {})
    wt = dims.get('weightBrutto', 0)
    
    if wt > 1.0 and any(k in title.lower() for k in ['патч', 'крем', 'сыворотк', 'маск', 'очки']):
        morph = PhysicalMorphologyEngine.deduce_dimensions_and_weight(title=title, sku=vc)
        
        sizes = c.get('sizes', [])
        clean_sizes = []
        for s in sizes:
            clean_sizes.append({
                'techSize': s.get('techSize', '0'),
                'wbSize': s.get('wbSize', ''),
                'price': s.get('price', 800),
                'skus': s.get('skus', [])
            })
            
        update_card = {
            'nmID': nm,
            'vendorCode': vc,
            'brand': c.get('brand', ''),
            'title': title,
            'description': c.get('description', ''),
            'dimensions': {
                'length': morph['length_cm'],
                'width': morph['width_cm'],
                'height': morph['height_cm'],
                'weightBrutto': morph['weightBrutto'],
                'isValid': True
            },
            'characteristics': c.get('characteristics', []),
            'sizes': clean_sizes
        }
        
        # 单件安全更新与隔离容错
        r_single = requests.post(
            'https://content-api.wildberries.ru/content/v2/cards/update',
            headers=headers,
            json=[update_card]
        )
        if r_single.status_code == 200:
            print(f"  [✓] 成功更新: nmID {nm} | {vc:<18} | {dims.get('weightBrutto')} kg ➔ {morph['weightBrutto']} kg ({morph['length_cm']}x{morph['width_cm']}x{morph['height_cm']}cm)")
            success_count += 1
        else:
            print(f"  [!] 更新拦截: nmID {nm} | {vc:<18} | HTTP {r_single.status_code} | {r_single.text}")
            failed_count += 1
        time.sleep(0.5)

print(f"\nUpdate Summary: {success_count} succeeded, {failed_count} skipped/intercepted.")

print("\nWaiting 5 seconds to verify live WB card updates...")
time.sleep(5)

r_verify = requests.post(
    'https://content-api.wildberries.ru/content/v2/get/cards/list',
    headers=headers,
    json={'settings': {'cursor': {'limit': 100}, 'filter': {'withPhoto': -1}}}
)
for c in r_verify.json().get('cards', []):
    vc = c.get('vendorCode')
    title = c.get('title', '')
    if any(k in title.lower() for k in ['патч', 'крем']):
        d = c.get('dimensions', {})
        print(f"  Live State: nmID {c.get('nmID')} | {vc:<18} | Weight: {d.get('weightBrutto')} kg | Dims: {d.get('length')}x{d.get('width')}x{d.get('height')}cm | Title: {title[:35]}")
