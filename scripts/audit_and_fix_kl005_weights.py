# -*- coding: utf-8 -*-
import requests, json, sys, os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_manager import SessionManager

mgr = SessionManager()
token = mgr.get_active_session_credentials()['wb_api_token']
headers = {'Authorization': token, 'Content-Type': 'application/json'}

r_cards = requests.post(
    'https://content-api.wildberries.ru/content/v2/get/cards/list',
    headers=headers,
    json={'settings': {'cursor': {'limit': 100}, 'filter': {'withPhoto': -1}}}
)
cards = r_cards.json().get('cards', [])
print(f"Total live cards in KL005: {len(cards)}")

abnormal_cards = []
for c in cards:
    nm = c.get('nmID')
    vc = c.get('vendorCode')
    title = c.get('title', '')
    dims = c.get('dimensions', {})
    l = dims.get('length', 0)
    w = dims.get('width', 0)
    h = dims.get('height', 0)
    wt = dims.get('weightBrutto', 0)
    
    # Check if weight is abnormal (e.g. > 1.0 kg for cosmetics or glasses)
    is_cosmetic_or_ppe = any(k in title.lower() for k in ['патч', 'крем', 'сыворотк', 'маск', 'очки'])
    if is_cosmetic_or_ppe and wt > 1.0:
        abnormal_cards.append(c)
        print(f"  [!] Abnormal Card: nmID {nm} | {vc:<18} | Weight: {wt:.2f} kg | Dims: {l}x{w}x{h}cm | Title: {title[:40]}")

print(f"\nTotal abnormal cards found: {len(abnormal_cards)}")
