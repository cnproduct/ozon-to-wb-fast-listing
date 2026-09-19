# -*- coding: utf-8 -*-
"""
==============================================================================
Wildberries 极速搬家上架引擎 - RR008 店铺全链路闭环脚本
==============================================================================
执行策略：
- 店铺: RR008
- 仓库: 莫斯科1仓 (ID: 2200719)
- 货币: CNY (人民币统一结算)
- 售价: Ozon 绿标价 * 6.0 倍实售 (划线标价 12 倍, 50% 官方大促折扣)
- 库存: 5 件 / 款
- 闭环指标: 现货在线 > 0 | 50%折扣生效 | weightBrutto > 0 & isValid:True | 白牌脱敏
==============================================================================
"""

import os
import sys
import re
import json
import time
import math
import glob
import requests
from typing import List, Dict, Any, Optional

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
BATCHES_DIR = os.path.join(WORKSPACE_DIR, 'batches_rr008')
OUTPUT_ARCHIVE = os.path.join(WORKSPACE_DIR, 'rr008_listed_products.json')

CONVERSATION_ID = "97ac70fb-afa7-4e2b-9dd5-c0853147f357"
OZON_CNY_RATE = 12.535  # Ozon 卢布转人民币基准汇率

try:
    from session_manager import SessionManager
except ImportError:
    from scripts.session_manager import SessionManager

def get_wb_session():
    mgr = SessionManager()
    creds = mgr.get_active_session_credentials(CONVERSATION_ID)
    token = creds.get('wb_api_token')
    wh_id = int(creds.get('wb_warehouse_id', 2200719))
    store_name = creds.get('store_name', 'RR008')
    
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        'Authorization': token,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    })
    return s, wh_id, store_name

def clean_text(text: str, sku: str = "") -> str:
    if not text:
        return ""
    if sku:
        text = re.sub(rf'\b{re.escape(str(sku))}\b', '', text)
    text = re.sub(r'(?i)[-\s*•]*(?:артикул|код товара|код|sku|ozon|озон)[^\n\.,;]*[:：]?\s*\b\d{6,14}\b[^\n\.,;]*', '', text)
    text = re.sub(r'(?i)\bozon\b', '', text)
    text = re.sub(r'(?i)\bозон\b', '', text)
    text = re.sub(r'OZON-\d+(-v\d+)?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[™®©\u2122\u00AE\u00A9]', '', text)
    text = re.sub(r'[\u25A0-\u25FF\u2B00-\u2BFF\u2700-\u27BF\u2600-\u26FF\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    if len(text) > 1950:
        text = text[:1900].rsplit('.', 1)[0] + "."
    return text.strip()

from category_matcher import match_subject_and_specs, clean_title_and_text

def format_product_payload(raw: Dict[str, Any], multiplier: float = 6.0) -> Dict[str, Any]:
    sku = str(raw.get('sku', '')).strip()
    title = raw.get('title', '').split('купить на OZON')[0].strip()
    title = re.sub(r'(?i)[-\s]*(?:ozon|озон).*', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    if len(title) > 60:
        title = title[:58].rsplit(' ', 1)[0]
    
    # 价格计算 (CNY 法则)
    ozon_rub = float(raw.get('ozon_price') or raw.get('ozon_green_price') or raw.get('ozon_rub') or 600)
    ozon_cny = round(ozon_rub / OZON_CNY_RATE, 2)
    wb_strike_price = int(round(ozon_cny * multiplier * 2.0))
    wb_sell_price = int(round(wb_strike_price * 0.5))

    # 类目与规格推导
    specs = match_subject_and_specs(title, raw.get('category_path', ''))
    
    # 描述清洗
    raw_desc = raw.get('description') or raw.get('description_clean') or f"{title}. Качественный товар для дома и спорта."
    desc = clean_text(raw_desc, sku)

    # 相册提取 (转换到 /wc1000/)
    photos = []
    seen_imgs = set()
    raw_photos = raw.get('photos', [])
    for u in raw_photos:
        u_hd = re.sub(r'/[c|wc]\d+/', '/wc1000/', str(u))
        img_id = u_hd.split('/')[-1]
        if img_id not in seen_imgs:
            seen_imgs.add(img_id)
            photos.append(u_hd)

    weight_g = specs['weight_g']
    weight_kg = round(weight_g / 1000.0, 2)
    if weight_kg <= 0:
        weight_kg = 0.2

    return {
        "sku": sku,
        "vendorCode": f"RR-{sku}-v1",
        "title": title,
        "description": desc,
        "subjectID": specs['subjectID'],
        "ozon_rub": ozon_rub,
        "ozon_cny": ozon_cny,
        "wb_strike_price": wb_strike_price,
        "wb_sell_price": wb_sell_price,
        "discount": 50,
        "stock": 5,
        "length_cm": specs['length'],
        "width_cm": specs['width'],
        "height_cm": specs['height'],
        "weight_g": weight_g,
        "weightBrutto": weight_kg,
        "photos": photos[:10],
        "characteristics": specs['characteristics']
    }

def get_already_listed_cards(session: requests.Session) -> Dict[str, int]:
    all_cards = {}
    cursor = {"limit": 100}
    while True:
        r = session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
            "settings": {"cursor": cursor, "filter": {"withPhoto": -1}}
        }, timeout=20)
        if r.status_code != 200:
            break
        data = r.json()
        cards = data.get('cards', [])
        if not cards:
            break
        for c in cards:
            vc = c.get('vendorCode')
            if vc:
                all_cards[vc] = c.get('nmID', 0)
        if len(cards) < 100:
            break
        cur = data.get('cursor', {})
        cursor = {
            "limit": 100,
            "updatedAt": cur.get('updatedAt', ''),
            "nmID": cur.get('nmID', 0)
        }
        time.sleep(0.3)
    return all_cards

def upload_products_batch(products: List[Dict[str, Any]], session: requests.Session, warehouse_id: int):
    if not products:
        return []
    
    total = len(products)
    print(f"\n{'='*70}\n🚀 开始执行本批次 {total} 款商品上架闭环 (目标仓库: {warehouse_id})\n{'='*70}")

    # 1. 批量申请 EAN-13 条形码
    print(f"[1/7] 申请 {total} 个官方 EAN-13 条码...")
    r_bc = session.post('https://content-api.wildberries.ru/content/v2/barcodes', json={'count': total}, timeout=20)
    if r_bc.status_code != 200:
        raise RuntimeError(f"申请条码失败: {r_bc.status_code} {r_bc.text}")
    barcodes = r_bc.json().get('data', [])
    for idx, p in enumerate(products):
        p['barcode'] = barcodes[idx]

    # 2. 构造建卡 Payload
    print(f"[2/7] 提交建卡至 Content API (预填 weightBrutto & sizes.price)...")
    cards_payload = []
    for p in products:
        cards_payload.append({
            "subjectID": p['subjectID'],
            "variants": [
                {
                    "vendorCode": p['vendorCode'],
                    "title": p['title'],
                    "description": p['description'],
                    "brand": "",  # 白牌脱敏
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

    r_up = session.post('https://content-api.wildberries.ru/content/v2/cards/upload', json=cards_payload, timeout=30)
    print(f"  -> 建卡返回: HTTP {r_up.status_code} | {r_up.text[:120]}")

    # 3. 轮询匹配 nmID
    print(f"[3/7] 轮询匹配官方 nmID...")
    target_vcs = {p['vendorCode']: p for p in products}
    nmid_map = {}
    for attempt in range(1, 15):
        time.sleep(3)
        r_list = session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
            "settings": {"cursor": {"limit": 100}, "filter": {"withPhoto": -1}}
        }, timeout=20)
        cards = r_list.json().get('cards', [])
        for c in cards:
            vc = c.get('vendorCode', '')
            if vc in target_vcs:
                nmid_map[vc] = c.get('nmID')
        print(f"  -> [轮询 {attempt}/15] 已匹配 nmID: {len(nmid_map)} / {len(target_vcs)}")
        if len(nmid_map) == len(target_vcs):
            break

    for p in products:
        p['nmID'] = nmid_map.get(p['vendorCode'])

    # 4. 异步上传高清相册 (media/save)
    print(f"[4/7] 云端异步挂载高清相册 (media/save)...")
    for p in products:
        nmid = p.get('nmID')
        if not nmid or not p['photos']:
            continue
        try:
            r_med = session.post('https://content-api.wildberries.ru/content/v3/media/save', json={
                "nmId": nmid,
                "data": p['photos']
            }, timeout=25)
            print(f"  • SKU {p['sku']} (nmID: {nmid}) 挂载 {len(p['photos'])} 张相册 -> HTTP {r_med.status_code}")
        except Exception as e:
            print(f"  • SKU {p['sku']} 相册挂载重试异常: {e}")
        time.sleep(0.3)

    # 5. 注入莫斯科1仓现货库存
    print(f"[5/7] 注入莫斯科1仓 (ID: {warehouse_id}) 现货库存 5 件...")
    stocks = [{"sku": p['barcode'], "amount": 5} for p in products if p.get('barcode')]
    for attempt in range(3):
        try:
            r_stk = session.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouse_id}', json={'stocks': stocks}, timeout=25)
            print(f"  -> 现货库存下发状态: HTTP {r_stk.status_code} (204 成功)")
            break
        except Exception as e:
            print(f"  -> 库存下发异常重试: {e}")
            time.sleep(1.5)

    # 6. 下发 50% 官方大促折扣至 Discounts-Prices API
    print(f"[6/7] 下发 50% 官方大促折扣至 Discounts-Prices API...")
    price_payload = [{'nmID': p['nmID'], 'price': p['wb_strike_price'], 'discount': 50} for p in products if p.get('nmID')]
    if price_payload:
        for attempt in range(3):
            try:
                r_pr = session.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': price_payload}, timeout=25)
                print(f"  -> 价格折扣提交状态: HTTP {r_pr.status_code} | {r_pr.text[:120]}")
                break
            except Exception as e:
                print(f"  -> 价格折扣提交异常重试: {e}")
                time.sleep(1.5)

    # 7. 归档保存
    print(f"[7/7] 归档保存至本地 rr008_listed_products.json...")
    archived = []
    if os.path.exists(OUTPUT_ARCHIVE):
        try:
            with open(OUTPUT_ARCHIVE, 'r', encoding='utf-8') as f:
                archived = json.load(f)
        except Exception:
            archived = []
    
    existing_skus = {it['sku'] for it in archived}
    for p in products:
        if p['sku'] not in existing_skus:
            archived.append(p)
            existing_skus.add(p['sku'])

    with open(OUTPUT_ARCHIVE, 'w', encoding='utf-8') as f:
        json.dump(archived, f, ensure_ascii=False, indent=2)

    print(f"✅ 本批次 {total} 款商品上架闭环完成！")
    return products

def scan_and_run_all():
    session, warehouse_id, store_name = get_wb_session()
    print(f"🔒 店铺 session 已验证: {store_name} | 仓库 ID: {warehouse_id}")

    # 获取已在售列表
    already_listed = get_already_listed_cards(session)
    print(f"📊 RR008 店铺当前已建卡: {len(already_listed)} 款")

    # 扫描 batches_rr008 目录下所有 parsed json
    parsed_files = sorted(glob.glob(os.path.join(BATCHES_DIR, 'batch_*_parsed.json')))
    print(f"📁 发现 {len(parsed_files)} 个已解析批次文件: {[os.path.basename(f) for f in parsed_files]}")

    all_parsed = []
    seen_skus = set()
    for pf in parsed_files:
        try:
            with open(pf, 'r', encoding='utf-8') as f:
                items = json.load(f)
                for it in items:
                    sku = str(it.get('sku', '')).strip()
                    if sku and sku not in seen_skus:
                        seen_skus.add(sku)
                        all_parsed.append(it)
        except Exception as e:
            print(f"[-] 读取 {pf} 异常: {e}")

    print(f"📦 累积解析就绪商品: {len(all_parsed)} 款")

    # 过滤待建卡商品
    to_upload = []
    for raw in all_parsed:
        p = format_product_payload(raw, multiplier=6.0)
        if p['vendorCode'] not in already_listed:
            to_upload.append(p)

    print(f"⚡ 待上架新商品: {len(to_upload)} 款")

    # 按每批 25 款执行上架
    batch_size = 25
    for i in range(0, len(to_upload), batch_size):
        chunk = to_upload[i:i+batch_size]
        upload_products_batch(chunk, session, warehouse_id)
        time.sleep(2)

if __name__ == '__main__':
    scan_and_run_all()
