# -*- coding: utf-8 -*-
import os, sys, json, re, requests

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

SCRIPT_DIR = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts'
sys.path.insert(0, SCRIPT_DIR)
from session_manager import SessionManager

archive_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\rr008_listed_products.json'
with open(archive_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

print(f"Total products in archive: {len(products)}")

# Group by current subjectID
by_subj = {}
for p in products:
    sid = p.get('subjectID')
    by_subj.setdefault(sid, []).append(p)

print("\nCurrent Subject ID breakdown:")
for sid, items in sorted(by_subj.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"  SubjectID {sid}: {len(items)} items")

# Inspect items under SubjectID 384
items_384 = by_subj.get(384, [])
print(f"\nAnalyzing all {len(items_384)} items currently under SubjectID 384 (Бутылки для воды):")

categories_found = {}
for p in items_384:
    title = p.get('title', '').lower()
    cat_guess = "Unknown"
    
    if any(k in title for k in ['швабр', 'ведро', 'насадк для швабр', 'отжим', 'моп']):
        cat_guess = "Швабры / Товары для уборки (Mops / Cleaning)"
    elif any(k in title for k in ['эспандер', 'тренажер', 'резинк для фитнес', 'турник', 'утяжелител', 'гир', 'гантел', 'петл']):
        cat_guess = "Эспандеры / Спорт (Expanders / Sports Fitness)"
    elif any(k in title for k in ['бутылк', 'фляг', 'шейкер', 'bottle']):
        cat_guess = "Бутылки для воды (Water Bottles - Correct)"
    elif any(k in title for k in ['термос', 'термокружк', 'термостакан']):
        cat_guess = "Термосы / Термокружки (Thermoses)"
    elif any(k in title for k in ['фильтр', 'картридж', 'кассет']):
        cat_guess = "Фильтры для воды (Water Filters)"
    elif any(k in title for k in ['массажер', 'перкуссионн', 'миостимулятор']):
        cat_guess = "Массажеры (Massagers)"
    elif any(k in title for k in ['стельк', 'супинатор']):
        cat_guess = "Стельки (Insoles)"
    elif any(k in title for k in ['лазерн', 'уровень', 'инструмент', 'дальномер', 'рулетк']):
        cat_guess = "Инструменты / Измерительные приборы (Tools)"
    elif any(k in title for k in ['очк', 'маск', 'шлем']):
        cat_guess = "Очки / Маски (Glasses / Masks)"
    elif any(k in title for k in ['перчатк']):
        cat_guess = "Перчатки (Gloves)"
    else:
        cat_guess = f"Other ({title[:35]})"
        
    categories_found.setdefault(cat_guess, []).append(p)

print("\nActual product types misclassified under 384:")
for cat, items in sorted(categories_found.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"  • {cat}: {len(items)} items")
    for sample in items[:2]:
        print(f"      - SKU {sample.get('sku')}: {sample.get('title')[:60]}")

