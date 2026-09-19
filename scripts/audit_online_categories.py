# -*- coding: utf-8 -*-
import os, sys, json, requests

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

print(f"\nTotal Online Cards: {len(all_cards)}")

by_subj = {}
for c in all_cards:
    sid = c.get('subjectID')
    sname = c.get('subjectName', 'Unknown')
    key = f"{sid}: {sname}"
    by_subj[key] = by_subj.get(key, 0) + 1

print("\n--- Online Subject Breakdown ---")
for k, cnt in sorted(by_subj.items(), key=lambda x: x[1], reverse=True):
    print(f"  • {k}: {cnt} cards")
