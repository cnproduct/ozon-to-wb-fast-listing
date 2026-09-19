# -*- coding: utf-8 -*-
import os, sys, glob, re, json
sys.path.insert(0, r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts')
from ozon_crawler import OzonCrawler
from smart_category_matcher import SmartCategoryMatcher

sys.stdout.reconfigure(encoding='utf-8')

crawler = OzonCrawler()
brain_dir = r'C:\Users\Administrator\.gemini\antigravity\brain'
txt_path = r'c:\Users\Administrator\Documents\google drive\RR009-09-10-1.txt'

with open(txt_path, 'r', encoding='utf-8') as f:
    all_skus = [l.strip() for l in f if l.strip().isdigit()]
unique_skus = list(dict.fromkeys(all_skus))

# Map sku to file
sku_map = {}
for root, dirs, files in os.walk(brain_dir):
    if 'content.md' in files:
        p = os.path.join(root, 'content.md')
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                c = f.read(2000)
            m = re.search(r'ozon\.ru/product/.*?(\d{6,14})', c)
            if m:
                sku_map[m.group(1)] = p
        except:
            pass

for sku in unique_skus:
    if sku not in sku_map:
        for root, dirs, files in os.walk(brain_dir):
            if 'content.md' in files:
                p = os.path.join(root, 'content.md')
                try:
                    with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                        c = f.read()
                    if f'ozon.ru/product/{sku}' in c or sku in c:
                        sku_map[sku] = p
                        break
                except:
                    pass

print(f"Total Unique SKUs: {len(unique_skus)}, Mapped files: {len(sku_map)}")

# Extract data
records = []
for sku in unique_skus:
    fpath = sku_map.get(sku)
    title, cat, price_rub, photos = "", "", 1500.0, []
    if fpath:
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            html = f.read()
        pdp = crawler.parse_pdp_html(sku, html)
        title = pdp.get('title', '')
        cat = pdp.get('category_path', '')
        price_rub = float(pdp.get('ozon_green_price') or pdp.get('ozon_price') or 1500.0)
        photos = pdp.get('photos', [])
        
        # If title is empty, extract directly via regex
        if not title:
            m_t = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
            if m_t:
                title = re.sub(r'<[^>]+>', '', m_t.group(1)).strip()
            else:
                m_t2 = re.search(r'title[\"\'\:\s]+([^\"\'\}]+)', html)
                if m_t2: title = m_t2.group(1).strip()
                
    records.append({
        'sku': sku,
        'title': title,
        'category_path': cat,
        'price_rub': price_rub,
        'photos': photos,
        'fpath': fpath
    })

empty_titles = [r for r in records if not r['title']]
print(f"Empty titles count: {len(empty_titles)}")
for et in empty_titles:
    print(f"  Empty SKU: {et['sku']}, fpath: {et['fpath']}")
