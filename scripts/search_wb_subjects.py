# -*- coding: utf-8 -*-
import sys, os, json, requests

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

sys.path.insert(0, r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts')
from wb_uploader import WildberriesAPIClient

client = WildberriesAPIClient()

queries = [
    'швабра', 'насадка для швабры', 'ведро', 'набор для уборки',
    'эспандер', 'лента для фитнеса', 'жгут спортивный', 'динамометр', 'рукоятка для тяги',
    'фильтр для воды', 'кассета для фильтра', 'картридж для фильтра', 'мембрана', 'засыпка',
    'смола', 'шунгит', 'массажер', 'маска', 'парфюмерная вода'
]

for q in queries:
    r = client.session.get('https://content-api.wildberries.ru/content/v2/object/all', params={'name': q})
    if r.status_code == 200:
        data = r.json().get('data', [])
        print(f"=== Query: {q} (Found {len(data)}) ===")
        for item in data[:5]:
            print(f"  ID: {item.get('subjectID')} | Name: {item.get('subjectName')} | Parent: {item.get('parentName')}")
