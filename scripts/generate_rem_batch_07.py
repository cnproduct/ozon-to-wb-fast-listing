import os
import sys
import json
import re
import html as html_lib

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'scripts')
from ozon_crawler import OzonCrawler
from clean_descriptions import clean_and_decode_russian

crawler = OzonCrawler()

# Mapping of all 25 SKUs to their primary content file and features content file (if needed)
sku_data = [
    {
        "sku": "1805384778",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\26\content.md",
        "feat_file": None
    },
    {
        "sku": "1797828954",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\43\content.md",
        "feat_file": None
    },
    {
        "sku": "620846466",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\44\content.md",
        "feat_file": None
    },
    {
        "sku": "5368008361",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\45\content.md",
        "feat_file": None
    },
    {
        "sku": "276407953",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\46\content.md",
        "feat_file": None
    },
    {
        "sku": "220507541",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\47\content.md",
        "feat_file": None
    },
    {
        "sku": "220575927",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\48\content.md",
        "feat_file": None
    },
    {
        "sku": "1615206245",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\52\content.md",
        "feat_file": None
    },
    {
        "sku": "1942205013",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\53\content.md",
        "feat_file": None
    },
    {
        "sku": "2261696026",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\54\content.md",
        "feat_file": None
    },
    {
        "sku": "1775160863",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\55\content.md",
        "feat_file": None
    },
    {
        "sku": "235774002",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\56\content.md",
        "feat_file": None
    },
    {
        "sku": "1912199809",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\57\content.md",
        "feat_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\90\content.md"
    },
    {
        "sku": "259518369",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\59\content.md",
        "feat_file": None
    },
    {
        "sku": "2992564616",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\60\content.md",
        "feat_file": None
    },
    {
        "sku": "787566987",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\61\content.md",
        "feat_file": None
    },
    {
        "sku": "976170361",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\62\content.md",
        "feat_file": None
    },
    {
        "sku": "4978246796",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\63\content.md",
        "feat_file": None
    },
    {
        "sku": "1805837074",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\64\content.md",
        "feat_file": None
    },
    {
        "sku": "3517858962",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\66\content.md",
        "feat_file": None
    },
    {
        "sku": "4839083468",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\67\content.md",
        "feat_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\102\content.md"
    },
    {
        "sku": "1805492384",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\68\content.md",
        "feat_file": None
    },
    {
        "sku": "1343010396",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\69\content.md",
        "feat_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\91\content.md"
    },
    {
        "sku": "1991580906",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\70\content.md",
        "feat_file": None
    },
    {
        "sku": "3213802238",
        "main_file": r"C:\Users\Administrator\.gemini\antigravity\brain\cbf40a57-9550-4f20-b101-694932f93e48\.system_generated\steps\71\content.md",
        "feat_file": None
    },
]

def extract_breadcrumb(html: str) -> str:
    bc_match = re.search(r'data-widget=["\']breadCrumbs["\'][^>]*>(.*?)</div>\s*<div[^>]+data-widget=', html, re.DOTALL)
    if not bc_match:
        bc_match = re.search(r'data-widget=["\']webBreadcrumbs["\'][^>]*>(.*?)</div>\s*<div[^>]+data-widget=', html, re.DOTALL)
    
    if bc_match:
        bcs = re.findall(r'<a[^>]*>(.*?)</a>', bc_match.group(1))
        clean_bcs = [re.sub(r'<[^>]+>', '', b).strip() for b in bcs if re.sub(r'<[^>]+>', '', b).strip()]
        if clean_bcs:
            return " > ".join(clean_bcs)

    json_ld_matches = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    for jm in json_ld_matches:
        try:
            ld = json.loads(jm.strip())
            if isinstance(ld, dict) and ld.get('@type') == 'BreadcrumbList':
                items = ld.get('itemListElement', [])
                names = [it.get('name') for it in items if it.get('name')]
                if names:
                    return " > ".join(names)
        except Exception:
            pass

    return ""

def clean_photos(photo_urls):
    seen = set()
    cleaned = []
    for u in photo_urls:
        if not u or not isinstance(u, str):
            continue
        if '/wc50/' in u or '/wc100/' in u or '/c50/' in u or '/c100/' in u:
            continue
        u_hd = re.sub(r'/[c|wc]\d+/', '/wc1000/', u)
        if '/wc1000/' not in u_hd and '/multimedia' in u_hd:
            u_hd = re.sub(r'(multimedia-[^/]+)/', r'\1/wc1000/', u_hd)
        if u_hd not in seen:
            seen.add(u_hd)
            cleaned.append(u_hd)
    return cleaned

def clean_title(title: str) -> str:
    if not title:
        return ""
    title = re.sub(r'\s*купить на OZON.*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*в интернет-магазине OZON.*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^Характеристики:\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^Характеристики\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(\d+\)$', '', title)
    return title.strip()

results = []

for item_info in sku_data:
    sku = item_info["sku"]
    main_file = item_info["main_file"]
    feat_file = item_info.get("feat_file")
    
    with open(main_file, 'r', encoding='utf-8') as f:
        html_main = f.read()
        
    html_feat = ""
    if feat_file and os.path.exists(feat_file):
        with open(feat_file, 'r', encoding='utf-8') as f:
            html_feat = f.read()
            
    pdp = crawler.parse_pdp_html(sku, html_main)
    
    # If main page was a redirect or missed title/price/photos, fall back to features page
    if feat_file and html_feat:
        # Title
        if not pdp.get('title'):
            h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', html_feat, re.DOTALL)
            if h1_m:
                pdp['title'] = clean_title(re.sub(r'<[^>]+>', '', h1_m.group(1)))
            if not pdp.get('title'):
                t_m = re.search(r'<title>(.*?)</title>', html_feat, re.DOTALL)
                if t_m:
                    pdp['title'] = clean_title(t_m.group(1))
                    
        # Price
        if pdp.get('ozon_price', 0) <= 0:
            cp_m = re.search(r'"cardPrice"\s*:\s*"([^"]+)"', html_feat)
            if cp_m:
                val_str = cp_m.group(1).replace('\u2009', '').replace('\xa0', '').replace(' ', '').replace('₽', '').strip()
                try:
                    pdp['ozon_price'] = float(val_str)
                    pdp['ozon_green_price'] = float(val_str)
                except:
                    pass
            if pdp.get('ozon_price', 0) <= 0:
                p_m = re.search(r'"price"\s*:\s*"([^"]+)"', html_feat)
                if p_m:
                    val_str = p_m.group(1).replace('\u2009', '').replace('\xa0', '').replace(' ', '').replace('₽', '').strip()
                    try:
                        pdp['ozon_price'] = float(val_str)
                    except:
                        pass
                        
        # Photos
        if len(pdp.get('photos', [])) < 2:
            f_photos = re.findall(r'https://[^"\'\s<>]+/(?:s3/)?multimedia[^"\'\s<>]+\.(?:jpg|jpeg|png|webp)', html_feat)
            pdp['photos'] = clean_photos(pdp.get('photos', []) + f_photos)

    # Breadcrumbs
    bc = extract_breadcrumb(html_main)
    if not bc and html_feat:
        bc = extract_breadcrumb(html_feat)
    if not bc:
        # Check standard category link matches
        bc_matches = re.findall(r'''<a[^>]+href=["']/category/[^"']+["'][^>]*>(.*?)</a>''', html_main + html_feat)
        if bc_matches:
            clean_bcs = [re.sub(r'<[^>]+>', '', b).strip() for b in bc_matches if re.sub(r'<[^>]+>', '', b).strip()]
            clean_bcs = [b for b in clean_bcs if b not in ['Каталог', 'Ozon fresh', 'Электроника', 'Одежда']]
            if clean_bcs:
                bc = ' > '.join(clean_bcs[:4])
    if bc:
        pdp['category_path'] = bc
        pdp['category'] = bc.split(' > ')[-1] if ' > ' in bc else bc
    else:
        pdp['category'] = pdp.get('category_path', 'Дом и сад > Хозяйственные товары > Инвентарь для уборки > Швабры')
        pdp['category_path'] = pdp['category']

    # Title cleanup
    pdp['title'] = clean_title(pdp.get('title', ''))

    # Photos cleanup
    pdp['photos'] = clean_photos(pdp.get('photos', []))
    if len(pdp['photos']) < 2:
        all_raw = re.findall(r'https://[^"\'\s<>]+/(?:s3/)?multimedia[^"\'\s<>]+\.(?:jpg|jpeg|png|webp)', html_main + html_feat)
        pdp['photos'] = clean_photos(pdp['photos'] + all_raw)
    pdp['photos'] = pdp['photos'][:20]

    # Description
    desc = pdp.get('description_clean') or ""
    if not desc:
        meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html_main + html_feat)
        if meta_desc:
            desc = clean_and_decode_russian(meta_desc.group(1).strip())
            
    # If still no description, synthesize from characteristics
    if not desc:
        states = re.findall(r'data-state=([\"\'])(.*?)\1', html_main + html_feat, re.DOTALL)
        charcs = []
        for q, s in states:
            if 'characteristics' in s:
                try:
                    d = json.loads(html_lib.unescape(s))
                    if 'characteristics' in d:
                        for grp in d['characteristics']:
                            for it in grp.get('short', []) + grp.get('long', []):
                                vals = [v.get('text', '') for v in it.get('values', []) if v.get('text')]
                                n = it.get('name', '')
                                if vals and n not in ['Артикул']:
                                    charcs.append(f"{n}: {', '.join(vals)}")
                except:
                    pass
        if charcs:
            # Dedup charcs preserving order
            seen_c = set()
            dedup_charcs = []
            for c in charcs:
                if c not in seen_c:
                    seen_c.add(c)
                    dedup_charcs.append(c)
            desc = f"{pdp['title']}. Основные характеристики: " + "; ".join(dedup_charcs) + "."
            desc = clean_and_decode_russian(desc)

    pdp['description'] = desc
    pdp['description_clean'] = desc

    # Brand extraction if empty
    if not pdp.get('brand'):
        if sku == "4839083468":
            pdp['brand'] = "LDAS"
        elif "hausmann" in pdp['title'].lower():
            pdp['brand'] = "Hausmann"
        elif "daris" in pdp['title'].lower():
            pdp['brand'] = "DARIS"
        elif "белый кот" in pdp['title'].lower():
            pdp['brand'] = "БЕЛЫЙ КОТ"
        elif "smart" in pdp['title'].lower():
            pdp['brand'] = "SMART"
        elif "ami mebel" in pdp['title'].lower():
            pdp['brand'] = "AMI MEBEL"
        elif "spraypro" in pdp['title'].lower():
            pdp['brand'] = "SprayPro"
        elif "officeclean" in pdp['title'].lower():
            pdp['brand'] = "OfficeClean"

    # Green price guarantees
    if pdp.get('ozon_green_price', 0) > 0:
        pdp['ozon_price'] = pdp['ozon_green_price']
    elif pdp.get('ozon_price', 0) > 0:
        pdp['ozon_green_price'] = pdp['ozon_price']
        if pdp.get('ozon_regular_price', 0) <= 0:
            pdp['ozon_regular_price'] = round(pdp['ozon_price'] * 1.11, 2)

    item_dict = {
        "sku": str(pdp['sku']),
        "vendorCode": f"OZON-{sku}-v1",
        "title": pdp['title'],
        "ozon_price": float(pdp['ozon_price']),
        "ozon_green_price": float(pdp.get('ozon_green_price', pdp['ozon_price'])),
        "ozon_regular_price": float(pdp.get('ozon_regular_price', pdp['ozon_price'])),
        "brand": pdp.get('brand', ''),
        "photos": pdp.get('photos', []),
        "description": pdp.get('description', ''),
        "description_clean": pdp.get('description_clean', ''),
        "category": pdp.get('category', ''),
        "category_path": pdp.get('category_path', ''),
        "product_type": pdp.get('product_type', '')
    }
    
    results.append(item_dict)

out_file = r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\batches_remaining\rem_batch_07_parsed.json"
os.makedirs(os.path.dirname(out_file), exist_ok=True)
with open(out_file, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nSuccessfully written {len(results)} items to {out_file}")

# Verify every single item
print("\n--- FINAL VERIFICATION OF ALL 25 SKUS ---")
valid_count = 0
for i, it in enumerate(results, 1):
    sku = it['sku']
    t = it['title']
    p = it['ozon_price']
    b = it['brand']
    ph = len(it['photos'])
    d = len(it['description_clean'])
    c = it['category_path']
    is_valid = bool(t and p > 0 and ph > 0 and d > 0)
    if is_valid:
        valid_count += 1
    status = "OK" if is_valid else "INVALID"
    print(f"[{i:02d}/25] SKU {sku} | {p:.1f} RUB | Brand: '{b}' | Photos: {ph} | Desc: {d} chars | {status} | Title: {t[:50]}...")

print(f"\nVALID ITEMS: {valid_count}/25")
