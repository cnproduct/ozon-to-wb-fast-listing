# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import math
import requests
import re

sys.path.insert(0, r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts")
from clean_descriptions import clean_and_decode_russian

sys.stdout.reconfigure(encoding='utf-8')

print("==================================================================")
print("🚀 重新上架 9 款五金电钻工具商品 (版本升级防重名冲突)")
print("==================================================================")

cfg_path = r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\config.json"
with open(cfg_path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

token = cfg['wb_api_token']
warehouse_id = int(cfg.get('wb_warehouse_id', 2200658))
store_currency = cfg.get('store_currency', 'CNY')
wb_rub_rate = float(cfg.get('wb_rub_rate', 11.672619))
multiplier = 6.0
discount = 50
stock = 5

session = requests.Session()
session.trust_env = False
session.headers.update({
    'Authorization': token,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
})

batch_path = r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\batch_9_ready.json"
with open(batch_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

# 升级货号版本号避免与已删除/回收站卡片冲突
for p in products:
    sku = p['sku']
    if sku == '2321480386':
        p['vendorCode'] = f"OZON-{sku}-v3"
    else:
        p['vendorCode'] = f"OZON-{sku}-v2"
        
    # 清洗违禁符号
    desc = p['description']
    desc = re.sub(r'[✔✓✅🌟⭐💡🔥✨💪⚙️🏋️🎉📦📐👉🚀🏁⚠️ℹ️❌🛡️]+', '', desc)
    desc = re.sub(r'[\U00010000-\U0010ffff]', '', desc)
    desc = re.sub(r'[\u2700-\u27bf]', '', desc)
    desc = re.sub(r'[\r\n]+.*?(?:ozon|код товара|артикул).*', '', desc, flags=re.IGNORECASE)
    p['description'] = desc
    
    # 价格计算
    ozon_rub = float(p['ozon_price'])
    target_buyer_rub = round(ozon_rub * multiplier)
    target_sell_cny = max(1, round(target_buyer_rub / wb_rub_rate))
    strike_price_cny = max(2, math.ceil(target_sell_cny / (1.0 - (discount / 100.0))))
    p['strike_price'] = strike_price_cny
    p['sell_price'] = target_sell_cny
    p['discount'] = discount
    p['stock'] = stock

# 1. 批量申请新条码
print("\n>>> [步骤 1/5] 申请 9 个全新官方 EAN-13 条形码...")
r_bc = session.post('https://content-api.wildberries.ru/content/v2/barcodes', json={'count': len(products)}, timeout=20)
if r_bc.status_code != 200:
    raise RuntimeError(f"申请条码失败: {r_bc.text}")
barcodes = r_bc.json().get('data', [])
print(f"  [+] 成功获取条码: {barcodes}")
for i, p in enumerate(products):
    p['barcode'] = barcodes[i]

# 2. 组装建卡 Payload
print("\n>>> [步骤 2/5] 提交批量建卡 Payload...")
cards_payload = []
for p in products:
    l = max(1, math.floor(float(p['length_cm'])))
    w = max(1, math.floor(float(p['width_cm'])))
    h = max(1, math.floor(float(p['height_cm'])))
    wt_kg = round(float(p['weight_g']) / 1000.0, 2)
    
    chars = [
        {'Предмет': 2197},
        {'ТНВЭД': '8467210000'}
    ]
    
    card_obj = {
        'subjectID': 2197,
        'variants': [{
            'vendorCode': p['vendorCode'],
            'title': p['title'],
            'description': p['description'],
            'dimensions': {
                'length': l,
                'width': w,
                'height': h,
                'weightBrutto': wt_kg
            },
            'characteristics': chars,
            'sizes': [{
                'techSize': '0',
                'wbSize': '',
                'price': int(p['strike_price']),
                'skus': [str(p['barcode'])]
            }]
        }]
    }
    cards_payload.append(card_obj)

r_up = session.post('https://content-api.wildberries.ru/content/v2/cards/upload', json=cards_payload, timeout=25)
print(f"  [+] 建卡接口返回: HTTP {r_up.status_code} | {r_up.text}")

# 3. 轮询获取 nmID
print("\n>>> [步骤 3/5] 轮询获取全新 nmID...")
vendor_codes = [p['vendorCode'] for p in products]
live_map = {}

for attempt in range(14):
    time.sleep(6)
    try:
        r_list = session.post(
            'https://content-api.wildberries.ru/content/v2/get/cards/list',
            json={'settings': {'filter': {'withPhoto': -1}, 'cursor': {'limit': 100}}},
            timeout=15
        )
        if r_list.status_code == 200:
            for c in r_list.json().get('cards', []):
                vc = c.get('vendorCode')
                if vc in vendor_codes:
                    live_map[vc] = c.get('nmID')
            print(f"  -> 轮询进度 ({attempt+1}/14): 已分配 {len(live_map)} / {len(vendor_codes)} 款商品")
            if len(live_map) == len(vendor_codes):
                print(f"  [+] 全部 {len(vendor_codes)} 款商品 nmID 分配就绪！")
                break
    except Exception as e:
        print(f"  -> 轮询异常: {e}")

for p in products:
    p['nmID'] = live_map.get(p['vendorCode'])
    print(f"  • SKU {p['sku']} ({p['vendorCode']}) ➔ nmID: {p['nmID']}")

# 4. 挂载高清图片
print("\n>>> [步骤 4/5] 云端直拉原厂高清相册...")
for p in products:
    nm_id = p.get('nmID')
    photos = p.get('photos', [])
    if not nm_id or not photos:
        continue
    try:
        r_m = session.post(
            'https://content-api.wildberries.ru/content/v3/media/save',
            json={'nmId': nm_id, 'data': photos[:30]},
            timeout=15
        )
        print(f"  • nmID {nm_id}: 挂载 {len(photos)} 张原图 {'[成功]' if r_m.status_code == 200 else '[降级/重试]'}")
    except Exception as e:
        print(f"  • nmID {nm_id} 挂图异常: {e}")
    time.sleep(1)

# 5. 下发价格与库存
print("\n>>> [步骤 5/5] 下发 CNY 折扣价格与莫斯科1仓库存...")
price_tasks = []
stock_items = []

for p in products:
    nm_id = p.get('nmID')
    bc = p.get('barcode')
    if nm_id:
        price_tasks.append({
            'nmID': nm_id,
            'price': int(p['strike_price']),
            'discount': int(p['discount'])
        })
    if bc:
        stock_items.append({
            'sku': str(bc),
            'amount': int(p['stock'])
        })

if price_tasks:
    for _ in range(3):
        r_p = session.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': price_tasks}, timeout=15)
        print(f"  [+] 价格下发: HTTP {r_p.status_code} | {r_p.text}")
        if r_p.status_code == 200:
            break
        time.sleep(2)

if stock_items:
    r_s = session.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouse_id}', json={'stocks': stock_items}, timeout=15)
    print(f"  [+] 莫斯科1仓库存注入: HTTP {r_s.status_code} | {r_s.text}")

# 6. 更新持久化档案
results_file = r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\upload_results.json"
try:
    with open(results_file, 'r', encoding='utf-8') as f:
        all_results = json.load(f)
except Exception:
    all_results = []

for p in products:
    rec = {
        'sku': p['sku'],
        'title': p['title'],
        'nmID': p.get('nmID'),
        'vendorCode': p['vendorCode'],
        'barcode': p['barcode'],
        'strike_price': p['strike_price'],
        'discount': p['discount'],
        'sell_price': p['sell_price'],
        'currency': 'CNY',
        'stock': p['stock'],
        'status': 'SUCCESS' if p.get('nmID') else 'PENDING',
        'url': f"https://www.wildberries.ru/catalog/{p.get('nmID')}/detail.aspx" if p.get('nmID') else ""
    }
    # 更新或追加
    found = False
    for idx, item in enumerate(all_results):
        if str(item.get('sku')) == str(p['sku']):
            all_results[idx] = rec
            found = True
            break
    if not found:
        all_results.append(rec)

with open(results_file, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print("\n==================================================================")
print(f"🎉 9 款商品重新上架全流程完成！")
print("==================================================================")
for p in products:
    print(f"  ✅ SKU {p['sku']} ({p['vendorCode']}) ➔ nmID: {p['nmID']}")
    print(f"     划线价: {p['strike_price']}元 ➔ 到手价: {p['sell_price']}元 | 库存: {p['stock']}件")
    print(f"     前台直达: https://www.wildberries.ru/catalog/{p['nmID']}/detail.aspx")
print("==================================================================")
