# -*- coding: utf-8 -*-
import sys, os, json, re

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

ref_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\references\wb_all_subjects.json'
with open(ref_path, 'r', encoding='utf-8') as f:
    all_subjects = json.load(f)

print(f"Total official subjects loaded: {len(all_subjects)}")

def search_subjects(keywords):
    results = []
    for s in all_subjects:
        name = s.get('subjectName', '').lower()
        parent = s.get('parentName', '').lower()
        for kw in keywords:
            if kw.lower() in name or kw.lower() in parent:
                results.append(s)
                break
    return results

keywords_to_check = [
    'швабр', 'ведро', 'уборк', 'насадк',
    'эспандер', 'жгут', 'фитнес', 'тренажер', 'динамометр', 'рукоятк', 'тяг',
    'фильтр', 'кассет', 'картридж', 'мембран', 'смола', 'шунгит', 'минерализатор',
    'бутылк', 'термос', 'термокружк', 'кружк',
    'массаж', 'маск', 'парфюм', 'аромат'
]

print("\n--- Key WB Categories Found ---")
for kw in ['швабр', 'насадк для швабр', 'ведра', 'наборы для уборки', 'эспандеры', 'ленты для фитнеса', 'жгуты спортивные', 'динамометры', 'фильтры для воды', 'кассеты для фильтров', 'картриджи для фильтров', 'мембраны', 'смолы', 'шунгит', 'бутылки для воды', 'термосы', 'термокружки']:
    matches = [s for s in all_subjects if kw in s.get('subjectName', '').lower()]
    print(f"\nKeyword '{kw}': {len(matches)} matches")
    for m in matches[:5]:
        print(f"  ID: {m.get('subjectID')} | Name: {m.get('subjectName')} | Parent: {m.get('parentName')}")
