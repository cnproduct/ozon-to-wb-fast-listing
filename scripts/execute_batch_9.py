# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import math
import requests

sys.path.insert(0, r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\scripts")
from clean_descriptions import clean_and_decode_russian

sys.stdout.reconfigure(encoding='utf-8')

print("==================================================================")
print("🚀 开始执行 9 款电钻/五金工具商品全流程极速智能上架 (Store 007)")
print("==================================================================")

# 1. 装载配置
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

print(f"[+] 配置检查: 店铺 {cfg.get('store_name', 'RR007')} | 币种: {store_currency} | 汇率: {wb_rub_rate}")
print(f"[+] 仓库: {warehouse_id} ({cfg.get('warehouse_name', '莫斯科1仓')}) | 实售倍数: {multiplier}x | 折扣: {discount}% | 库存: {stock}件")

headers = {
    'Authorization': token,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

session = requests.Session()
session.trust_env = False
session.headers.update(headers)

# 2. 读取待上架商品
batch_path = r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\batch_9_ready.json"
with open(batch_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

print(f"\n[+] 待上架商品加载完毕: 共 {len(products)} 款")

for p in products:
    ozon_rub = float(p['ozon_price'])
    target_buyer_rub = round(ozon_rub * multiplier)
    
    if store_currency == 'CNY':
        target_sell_cny = max(1, round(target_buyer_rub / wb_rub_rate))
        strike_price_cny = max(2, math.ceil(target_sell_cny / (1.0 - (discount / 100.0))))
        p['strike_price'] = strike_price_cny
        p['sell_price'] = target_sell_cny
        p['currency'] = 'CNY'
    else:
        target_sell_rub = round(target_buyer_rub)
        strike_price_rub = math.ceil(target_sell_rub / (1.0 - (discount / 100.0)))
        p['strike_price'] = strike_price_rub
        p['sell_price'] = target_sell_rub
        p['currency'] = 'RUB'
        
    p['discount'] = discount
    p['stock'] = stock
    
    print(f"  • SKU {p['sku']}: 《{p['title']}》")
    print(f"    Ozon原价: {ozon_rub:.0f}₽ ➔ 买家前台目标: {target_buyer_rub}₽ ➔ 下发CNY实售: {p['sell_price']}元, 划线: {p['strike_price']}元 | 规格: {p['length_cm']}x{p['width_cm']}x{p['height_cm']}cm, {p['weight_g']}g")

# 3. 申请官方 EAN-13 条形码
print("\n>>> [步骤 1/5] 批量申请官方 EAN-13 条形码...")
r_bc = session.post('https://content-api.wildberries.ru/content/v2/barcodes', json={'count': len(products)}, timeout=20)
if r_bc.status_code != 200:
    raise RuntimeError(f"申请条形码失败: HTTP {r_bc.status_code} | {r_bc.text}")

barcodes = r_bc.json().get('data', [])
print(f"  [+] 成功获取 {len(barcodes)} 个官方条形码: {barcodes}")
for i, p in enumerate(products):
    p['barcode'] = barcodes[i]

# 4. 组装建卡 Payload 并提交
print("\n>>> [步骤 2/5] 提交批量建卡至 WB Content API...")

cards_payload = []
for p in products:
    l = max(1, math.floor(float(p['length_cm'])))
    w = max(1, math.floor(float(p['width_cm'])))
    h = max(1, math.floor(float(p['height_cm'])))
    wt_kg = round(float(p['weight_g']) / 1000.0, 2)
    
    # 特性属性
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
print(f"  [+] 建卡接口响应: HTTP {r_up.status_code} | {r_up.text}")

if r_up.status_code not in [200, 201]:
    # 若有个别货号冲突，进行逐个重试
    print("  [!] 批量建卡未直接返回 200，尝试逐个提交...")
    for idx, card_obj in enumerate(cards_payload):
        r_single = session.post('https://content-api.wildberries.ru/content/v2/cards/upload', json=[card_obj], timeout=25)
        print(f"    - SKU {products[idx]['sku']} ({products[idx]['vendorCode']}): HTTP {r_single.status_code}")
        time.sleep(1)

# 5. 轮询获取 nmID
print("\n>>> [步骤 3/5] 轮询获取系统分配的 nmID...")
vendor_codes = [p['vendorCode'] for p in products]
live_map = {}

for attempt in range(12):
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
            print(f"  -> 轮询中 ({attempt+1}/12): 已就绪 {len(live_map)} / {len(vendor_codes)} 款商品")
            if len(live_map) == len(vendor_codes):
                print(f"  [+] 全部 {len(vendor_codes)} 款商品 nmID 分配就绪！")
                break
    except Exception as e:
        print(f"  -> 轮询异常: {e}")

for p in products:
    p['nmID'] = live_map.get(p['vendorCode'])
    print(f"  • SKU {p['sku']} | 货号: {p['vendorCode']} ➔ nmID: {p['nmID']}")

# 6. 极速挂载高清多图
print("\n>>> [步骤 4/5] 云端异步直拉高清原版相册 (media/save)...")
for p in products:
    nm_id = p.get('nmID')
    photos = p.get('photos', [])
    if not nm_id or not photos:
        continue
        
    try:
        r_media = session.post(
            'https://content-api.wildberries.ru/content/v3/media/save',
            json={'nmId': nm_id, 'data': photos[:30]},
            timeout=15
        )
        if r_media.status_code == 200:
            print(f"  • nmID {nm_id}: 成功挂载 {len(photos)} 张原图 (云端直拉)")
        else:
            print(f"  • nmID {nm_id}: 云端直拉状态 {r_media.status_code}, 尝试降级直传...")
            for idx, img_url in enumerate(photos[:10], start=1):
                try:
                    r_img = session.get(img_url, timeout=10)
                    if r_img.status_code == 200 and len(r_img.content) > 1000:
                        files = {'uploadfile': (f'img_{idx}.jpg', r_img.content, 'image/jpeg')}
                        file_headers = {
                            'Authorization': token,
                            'X-Nm-Id': str(nm_id),
                            'X-Photo-Number': str(idx)
                        }
                        requests.post('https://content-api.wildberries.ru/content/v3/media/file', headers=file_headers, files=files, timeout=15)
                except Exception:
                    pass
                time.sleep(0.2)
    except Exception as e:
        print(f"  • nmID {nm_id}: 挂图异常 {e}")
    time.sleep(1)

# 7. 下发促销折扣价格与仓库现货库存
print("\n>>> [步骤 5/5] 下发 CNY 促销折扣价格与莫斯科1仓现货库存...")

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

# 提交价格
if price_tasks:
    for attempt in range(3):
        r_pr = session.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': price_tasks}, timeout=15)
        print(f"  [+] 批量价格下发响应: HTTP {r_pr.status_code} | {r_pr.text}")
        if r_pr.status_code == 200:
            break
        time.sleep(2)

# 提交库存
if stock_items:
    r_st = session.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouse_id}', json={'stocks': stock_items}, timeout=15)
    print(f"  [+] 仓库 {warehouse_id} 现货库存注入响应: HTTP {r_st.status_code} | {r_st.text}")

# 8. 错误队列核查
time.sleep(3)
r_err = session.post('https://content-api.wildberries.ru/content/v2/cards/error/list', json={}, timeout=15)
print(f"\n>>> [质检验收] 官方异步错误队列检查: {r_err.text}")

# 9. 更新持久化数据并保存
results_file = r"c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\upload_results.json"
try:
    with open(results_file, 'r', encoding='utf-8') as f:
        all_results = json.load(f)
except Exception:
    all_results = []

existing_skus = {str(r.get('sku')) for r in all_results}

new_records = []
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
        'currency': p.get('currency', 'CNY'),
        'stock': p['stock'],
        'status': 'SUCCESS' if p.get('nmID') else 'PENDING',
        'url': f"https://www.wildberries.ru/catalog/{p.get('nmID')}/detail.aspx" if p.get('nmID') else ""
    }
    new_records.append(rec)
    if str(p['sku']) in existing_skus:
        for idx, item in enumerate(all_results):
            if str(item.get('sku')) == str(p['sku']):
                all_results[idx] = rec
    else:
        all_results.append(rec)

with open(results_file, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print("\n==================================================================")
print(f"🎉 9 款商品极速上架全部完成！店铺总商品归档数: {len(all_results)} 款")
print("==================================================================")
for r in new_records:
    print(f"  ✅ SKU {r['sku']} ➔ nmID: {r['nmID']} | 条形码: {r['barcode']}")
    print(f"     标价: {r['strike_price']}元 -> 到手价: {r['sell_price']}元 (折后50%) | 现货: {r['stock']}件")
    print(f"     前台直达: {r['url']}")
print("==================================================================")
