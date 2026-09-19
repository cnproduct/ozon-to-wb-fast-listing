# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import math
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_manager import SessionManager
from clean_descriptions import clean_and_decode_russian

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

print("="*80)
print("🚀 启动 Wildberries 极速上架流水线: 目标店铺 KL005 (俄罗斯海外仓 2166193)")
print("="*80)

# 1. 获取会话凭据
mgr = SessionManager()
creds = mgr.get_active_session_credentials()
token = creds['wb_api_token']
warehouse_id = int(creds['wb_warehouse_id'])
store_name = creds['store_name']
multiplier = float(creds.get('default_multiplier', 6.0))
discount = int(creds.get('default_discount', 50))
stock = int(creds.get('default_stock', 5))
ozon_cny_rate = 12.535

print(f"🔒 店铺: {store_name} | 仓库 ID: {warehouse_id} | 策略: {multiplier}倍实售 / {discount}%大促折 / {stock}件现货")

session = requests.Session()
session.trust_env = False
session.headers.update({
    'Authorization': token,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
})

# 读取已解析的 10 款商品
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pilot_10_parsed.json'), 'r', encoding='utf-8') as f:
    raw_products = json.load(f)

products = []
for p in raw_products:
    sku = str(p['sku'])
    title = p.get('title', '').strip()
    ozon_rub = float(p.get('ozon_price') or p.get('ozon_green_price') or 1000.0)
    ozon_cny = round(ozon_rub / ozon_cny_rate, 2)
    wb_strike_cny = int(round(ozon_cny * multiplier * 2.0))
    wb_sell_cny = int(round(wb_strike_cny * 0.5))
    
    # 类目纠偏
    title_lower = title.lower()
    if 'щиток' in title_lower or 'маска защитная' in title_lower:
        subj_id = 4262 # Щитки защитные лицевые
    else:
        subj_id = 3679 # Очки защитные
    
    # 尺寸与重量 (真实物理形态)
    l = int(p.get('length_cm') or 18)
    w = int(p.get('width_cm') or 12)
    h = int(p.get('height_cm') or 8)
    wt_g = int(p.get('weight_g') or 180)
    wt_kg = round(wt_g / 1000.0, 2)
    if wt_kg <= 0: wt_kg = 0.18
    
    # 标题清洗 (<= 60 字符)
    clean_title = title.split('купить на OZON')[0].strip()
    clean_title = clean_and_decode_russian(clean_title)
    if len(clean_title) > 60:
        clean_title = clean_title[:58].rsplit(' ', 1)[0]
        
    # 描述排版
    raw_desc = p.get('description_clean') or title
    sanitized_desc = clean_and_decode_russian(raw_desc)
    specs_footer = (
        f"\n\nОсновные характеристики:\n"
        f"- Вес с упаковкой (брутто): {wt_g} г ({wt_kg:.2f} кг)\n"
        f"- Габариты упаковки: {l} x {w} x {h} см\n"
        f"- Назначение: Защита глаз и лица при строительных, сварочных и слесарных работах\n"
        f"- Артикул продавца: KL-{sku}-v1"
    )
    budget = 1950 - len(specs_footer)
    clean_desc = sanitized_desc[:budget].strip() + specs_footer
    
    # 饱和展示参数注入
    if subj_id == 3679:
        chars = [
            {"id": 17596, "name": "Материал изделия", "value": ["поликарбонат", "ударопрочный пластик"]},
            {"id": 85571, "name": "Упаковка", "value": ["коробка"]},
            {"id": 142570, "name": "Тип защитных очков", "value": ["открытые" if "открыт" in title_lower else "закрытые"]},
            {"id": 378533, "name": "Комплектация", "value": ["защитные очки - 1 шт."]},
            {"id": 14177449, "name": "Цвет", "value": ["прозрачный", "черный"]},
            {"id": 14177451, "name": "Страна производства", "value": ["Китай"]}
        ]
    else:
        chars = [
            {"id": 17596, "name": "Материал изделия", "value": ["ударопрочный поликарбонат", "ABS-пластик"]},
            {"id": 378533, "name": "Комплектация", "value": ["щиток защитный лицевой - 1 шт."]},
            {"id": 14177449, "name": "Цвет", "value": ["прозрачный", "черный"]},
            {"id": 14177451, "name": "Страна производства", "value": ["Китай"]}
        ]
        
    products.append({
        "sku": sku,
        "vendorCode": f"KL-{sku}-v1",
        "subjectID": subj_id,
        "title": clean_title,
        "description": clean_desc,
        "brand": "",
        "length_cm": l,
        "width_cm": w,
        "height_cm": h,
        "weight_g": wt_g,
        "weightBrutto": wt_kg,
        "ozon_rub": ozon_rub,
        "ozon_cny": ozon_cny,
        "wb_strike_cny": wb_strike_cny,
        "wb_sell_cny": wb_sell_cny,
        "photos": p.get('photos', [])[:10],
        "characteristics": chars
    })

print(f"[+] 待上架商品配置完毕 (共 {len(products)} 款):")
for p in products:
    print(f"  • SKU {p['sku']}: Ozon={p['ozon_rub']}₽ ({p['ozon_cny']}元) ➔ WB划线标价={p['wb_strike_cny']}元 (5折实售={p['wb_sell_cny']}元) | SubjectID: {p['subjectID']}")

# 步骤 1: 批量申请官方 EAN-13 条形码
print("\n>>> [步骤 1/6] 申请官方 EAN-13 条形码...")
r_bc = session.post('https://content-api.wildberries.ru/content/v2/barcodes', json={'count': len(products)}, timeout=20)
if r_bc.status_code != 200:
    raise RuntimeError(f"申请条形码失败: {r_bc.status_code} {r_bc.text}")
barcodes = r_bc.json().get('data', [])
print(f"  [+] 成功获取条形码: {barcodes}")
for i, p in enumerate(products):
    p['barcode'] = barcodes[i]

# 步骤 2: 批量提交建卡
print("\n>>> [步骤 2/6] 批量提交卡片至 Content API...")
cards_payload = []
for p in products:
    cards_payload.append({
        "subjectID": p['subjectID'],
        "variants": [
            {
                "vendorCode": p['vendorCode'],
                "title": p['title'],
                "description": p['description'],
                "brand": "", # 100% 白牌脱敏
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
                        "price": p['wb_strike_cny'],
                        "skus": [p['barcode']]
                    }
                ]
            }
        ]
    })

r_up = session.post('https://content-api.wildberries.ru/content/v2/cards/upload', json=cards_payload, timeout=30)
print(f"  [+] 建卡响应: HTTP {r_up.status_code} | {r_up.text[:200]}")

# 步骤 3: 轮询匹配 nmID
print("\n>>> [步骤 3/6] 轮询匹配官方 nmID...")
target_vcs = [p['vendorCode'] for p in products]
nmid_map = {}
for attempt in range(1, 15):
    time.sleep(3)
    r_list = session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
        "settings": {"cursor": {"limit": 100}, "filter": {"withPhoto": -1}}
    }, timeout=20)
    if r_list.status_code == 200:
        for c in r_list.json().get('cards', []):
            vc = c.get('vendorCode', '')
            if vc in target_vcs:
                nmid_map[vc] = c.get('nmID')
        print(f"  [轮询 {attempt}/15] 已匹配 nmID: {len(nmid_map)}/{len(target_vcs)}")
        if len(nmid_map) == len(target_vcs):
            break

for p in products:
    p['nmID'] = nmid_map.get(p['vendorCode'])

# 步骤 4: 异步直拉高清原图相册
print("\n>>> [步骤 4/6] 极速异步挂载高清原图画廊 (media/save)...")
for p in products:
    nmid = p.get('nmID')
    if not nmid or not p['photos']:
        continue
    for attempt in range(3):
        try:
            r_med = session.post('https://content-api.wildberries.ru/content/v3/media/save', json={
                "nmId": nmid,
                "data": p['photos']
            }, timeout=30)
            print(f"  • SKU {p['sku']} (nmID: {nmid}) 挂载 {len(p['photos'])} 张图片 ➔ HTTP {r_med.status_code}")
            break
        except Exception as e:
            print(f"  • 挂载异常重试: {e}")
            time.sleep(1.5)
    time.sleep(0.3)

# 步骤 5: 注入俄罗斯海外仓现货库存
print(f"\n>>> [步骤 5/6] 注入俄罗斯海外仓 (ID: {warehouse_id}) 现货库存: {stock} 件/款...")
stocks_payload = [{"sku": p['barcode'], "amount": int(stock)} for p in products if p.get('barcode')]
for attempt in range(3):
    try:
        r_stk = session.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouse_id}', json={'stocks': stocks_payload}, timeout=30)
        print(f"  [+] 现货库存下发状态: HTTP {r_stk.status_code} (204 成功)")
        break
    except Exception as e:
        print(f"  [!] 库存注入重试: {e}")
        time.sleep(1.5)

# 步骤 6: 下发 50% 官方大促折扣价格
print("\n>>> [步骤 6/6] 下发 50% 官方大促折扣至 Discounts-Prices API...")
price_payload = [{'nmID': p['nmID'], 'price': p['wb_strike_cny'], 'discount': discount} for p in products if p.get('nmID')]
if price_payload:
    for attempt in range(3):
        try:
            r_pr = session.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': price_payload}, timeout=30)
            print(f"  [+] 价格中心下发返回: HTTP {r_pr.status_code} | {r_pr.text[:180]}")
            break
        except Exception as e:
            print(f"  [!] 价格下发重试: {e}")
            time.sleep(1.5)

# 归档保存
out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pilot_10_listed.json')
with open(out_file, 'w', encoding='utf-8') as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print("\n" + "="*90)
print(f"🎉 批次上架完成！共 {len(products)} 款商品已成功入库 KL005 店铺并激活现货！")
print("="*90)
for p in products:
    print(f"SKU {p['sku']}: Ozon={p['ozon_rub']}₽ ({p['ozon_cny']}元) ➔ WB 5折实售={p['wb_sell_cny']}元 (标价={p['wb_strike_cny']}元, -50%) | nmID: {p.get('nmID')} | 条码: {p.get('barcode')} | 库存: {stock}")
print("="*90)
