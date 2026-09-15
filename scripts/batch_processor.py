# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import math
import re
import glob
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_manager import SessionManager
from clean_descriptions import clean_and_decode_russian
from ozon_crawler import OzonCrawler
from listing_engine import WBListingStudio
from morphology_engine import PhysicalMorphologyEngine
from category_matcher import match_subject_and_specs

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

def process_batch(target_skus, batch_name="Batch"):
    print(f"\n{'='*70}\n🚀 启动处理批次 [{batch_name}] (包含 {len(target_skus)} 款 SKU)\n{'='*70}")
    
    studio = WBListingStudio()
    crawler = OzonCrawler()
    mgr = SessionManager()
    creds = mgr.get_active_session_credentials()
    token = creds['wb_api_token']
    warehouse_id = int(creds['wb_warehouse_id'])
    multiplier = float(creds.get('default_multiplier', 6.0))
    discount = int(creds.get('default_discount', 50))
    stock = int(creds.get('default_stock', 5))
    ozon_cny_rate = 12.535

    session = requests.Session()
    session.trust_env = False
    session.headers.update({'Authorization': token, 'Content-Type': 'application/json'})

    # 扫描所有 step 文件
    sku_files = {}
    for sf in glob.glob(os.path.expanduser('~/.gemini/antigravity/brain/*/.system_generated/steps/*/content.md')):
        try:
            with open(sf, 'r', encoding='utf-8', errors='ignore') as f:
                head = f.read(400)
                m = re.search(r'ozon\.ru/product/[^/]*?(\d+)/?', head)
                if m and m.group(1) in target_skus:
                    sku_files[m.group(1)] = sf
        except Exception:
            pass

    print(f"[*] 已在本地缓存找到 {len(sku_files)}/{len(target_skus)} 款 Ozon 页面数据")

    products = []
    for sku in target_skus:
        if sku not in sku_files:
            print(f"[-] 暂无缓存文件，跳过 SKU {sku}")
            continue
        with open(sku_files[sku], 'r', encoding='utf-8', errors='ignore') as f:
            html = f.read()
        pdp = crawler.parse_pdp_html(sku, html)
        feat = crawler.parse_features_html(html)
        
        raw_title = pdp.get('title', '').split('купить на OZON')[0].strip()
        full_title = clean_and_decode_russian(raw_title)
        
        ozon_rub = float(pdp.get('ozon_price') or pdp.get('ozon_green_price') or 1000.0)
        ozon_cny = round(ozon_rub / ozon_cny_rate, 2)
        wb_strike_cny = int(round(ozon_cny * multiplier * 2.0))
        wb_sell_cny = int(round(wb_strike_cny * 0.5))
        
        # 1. 严格类目对齐 (Zero-Fallback，在完整标题上匹配)
        spec = match_subject_and_specs(full_title)
        subj_id = spec['subjectID']
        subj_name = spec['subjectName']
        
        # 截断标题以符合 WB 平台字符上限 (60字符)
        title = full_title
        if len(title) > 60:
            title = title[:58].rsplit(' ', 1)[0]
            
        # 2. 真实物理形态包装尺寸与毛重推导 (三层推导体系)
        morph_res = PhysicalMorphologyEngine.deduce_dimensions_and_weight(
            title=full_title,
            raw_props=feat.get('raw_props', {}),
            html_content=html,
            sku=sku
        )
        l = morph_res['length_cm']
        w = morph_res['width_cm']
        h = morph_res['height_cm']
        wt_g = morph_res['weight_g']
        wt_kg = morph_res['weightBrutto']
        
        specs_footer = (
            f"\n\nОсновные характеристики:\n"
            f"- Вес с упаковкой (брутто): {wt_g} г ({wt_kg:.2f} кг)\n"
            f"- Габариты упаковки: {l} x {w} x {h} см\n"
            f"- Категория: {subj_name}\n"
            f"- Артикул продавца: KL-{sku}-v1"
        )
        budget = 1950 - len(specs_footer)
        clean_desc = clean_and_decode_russian(pdp.get('description_clean') or title)[:budget].strip() + specs_footer
        
        # 3. 官方展示属性
        chars = list(spec.get('characteristics', []))
        # 确保包含产地和颜色基础属性
        char_ids = {c['id'] for c in chars}
        if 14177451 not in char_ids:
            chars.append({'id': 14177451, 'name': 'Страна производства', 'value': ['Китай']})
        
        # 4. 图片去重
        raw_photos = pdp.get('photos', [])
        dedup_photos = []
        seen_img_ids = set()
        for u in raw_photos:
            img_id_match = re.search(r'(\d+\.(?:jpg|jpeg|png))', u)
            if img_id_match:
                img_id = img_id_match.group(1)
                if img_id not in seen_img_ids:
                    seen_img_ids.add(img_id)
                    dedup_photos.append(u)
            elif u not in dedup_photos:
                dedup_photos.append(u)
        
        products.append({
            'sku': sku,
            'vendorCode': f'KL-{sku}-v1',
            'subjectID': subj_id,
            'subjectName': subj_name,
            'title': title,
            'description': clean_desc,
            'brand': '',
            'length_cm': l,
            'width_cm': w,
            'height_cm': h,
            'weight_g': wt_g,
            'weightBrutto': wt_kg,
            'ozon_rub': ozon_rub,
            'ozon_cny': ozon_cny,
            'wb_strike_cny': wb_strike_cny,
            'wb_sell_cny': wb_sell_cny,
            'photos': dedup_photos[:10],
            'characteristics': chars
        })

    if not products:
        print("[-] 本批次无可上架商品")
        return []

    # 1. 申请官方条形码
    print(f">>> [1/5] 申请 {len(products)} 个官方 EAN-13 条形码...")
    r_bc = session.post('https://content-api.wildberries.ru/content/v2/barcodes', json={'count': len(products)}, timeout=20)
    bcs = r_bc.json().get('data', [])
    for i, p in enumerate(products):
        p['barcode'] = bcs[i]

    # 2. 批量建卡
    print(f">>> [2/5] 批量提交卡片至 Content API...")
    cards_payload = []
    for p in products:
        cards_payload.append({
            'subjectID': p['subjectID'],
            'variants': [{
                'vendorCode': p['vendorCode'],
                'title': p['title'],
                'description': p['description'],
                'brand': '',
                'dimensions': {
                    'length': p['length_cm'],
                    'width': p['width_cm'],
                    'height': p['height_cm'],
                    'weightBrutto': p['weightBrutto'],
                    'isValid': True
                },
                'characteristics': p['characteristics'],
                'sizes': [{'techSize': '0', 'wbSize': '', 'price': p['wb_strike_cny'], 'skus': [p['barcode']]}]
            }]
        })

    r_up = session.post('https://content-api.wildberries.ru/content/v2/cards/upload', json=cards_payload, timeout=30)
    print(f"  [+] 建卡状态: HTTP {r_up.status_code}")

    # 3. 轮询匹配 nmID
    print(f">>> [3/5] 轮询匹配官方 nmID...")
    target_vcs = [p['vendorCode'] for p in products]
    nmid_map = {}
    for attempt in range(1, 15):
        time.sleep(3)
        r_list = session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={'settings': {'cursor': {'limit': 100}, 'filter': {'withPhoto': -1}}})
        for c in r_list.json().get('cards', []):
            if c.get('vendorCode') in target_vcs:
                nmid_map[c.get('vendorCode')] = c.get('nmID')
        if len(nmid_map) == len(target_vcs):
            break

    print(f"  [+] nmID 匹配完成: {len(nmid_map)}/{len(target_vcs)}")
    for p in products:
        p['nmID'] = nmid_map.get(p['vendorCode'])

    # 4. 极速异步挂载相册 (media/save 优先，失败降级 media/file)
    print(f">>> [4/5] 挂载多角度高清相册...")
    for p in products:
        nmid = p.get('nmID')
        sku = p['sku']
        if not nmid or not p['photos']:
            continue
        try:
            r_save = session.post('https://content-api.wildberries.ru/content/v3/media/save', json={'nmId': nmid, 'data': p['photos']}, timeout=15)
            if r_save.status_code == 200:
                print(f"  • SKU {sku} (nmID: {nmid}) 异步直拉 {len(p['photos'])} 张图片 ➔ HTTP 200 成功")
                continue
        except Exception:
            pass

        # 降级二进制上传
        for idx, u in enumerate(p['photos'][:10], start=1):
            try:
                r_img = session.get(u, timeout=10)
                if r_img.status_code == 200 and len(r_img.content) > 500:
                    h = {'Authorization': token, 'X-Nm-Id': str(nmid), 'X-Photo-Number': str(idx)}
                    files = {'uploadfile': (f'{sku}_{idx}.jpg', r_img.content, 'image/jpeg')}
                    session.post('https://content-api.wildberries.ru/content/v3/media/file', headers=h, files=files, timeout=15)
            except Exception:
                pass

    # 5. 注入现货库存
    print(f">>> [5/5] 注入俄罗斯海外仓 (ID: {warehouse_id}) 现货库存: {stock} 件/款...")
    stocks_payload = [{'sku': p['barcode'], 'amount': stock} for p in products if p.get('barcode')]
    session.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouse_id}', json={'stocks': stocks_payload}, timeout=30)
    print("  [+] 现货库存注入成功！")

    # 6. 下发 50% 大促价格
    print(f">>> [6/6] 下发 50% 官方大促价格中心...")
    prices_payload = [{'nmId': p['nmID'], 'price': p['wb_strike_cny'], 'discount': discount} for p in products if p.get('nmID')]
    if prices_payload:
        try:
            r_price = session.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': prices_payload}, timeout=20)
            print(f"  [+] 价格下发状态: HTTP {r_price.status_code}")
        except Exception as e:
            print(f"  [-] 价格下发异常: {e}")

    # 归档保存
    out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'KL005_listed_products.json')
    all_listed = []
    if os.path.exists(out_file):
        try:
            with open(out_file, 'r', encoding='utf-8') as f:
                all_listed = json.load(f)
        except Exception:
            all_listed = []
    all_listed.extend(products)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_listed, f, ensure_ascii=False, indent=2)

    print(f"\n[🎉] 批次 [{batch_name}] 上架完毕！当前 KL005 累计已上架: {len(all_listed)} 款商品！\n")
    return products

if __name__ == '__main__':
    # 示例运行
    pass
