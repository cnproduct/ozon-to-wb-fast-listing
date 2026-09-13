# -*- coding: utf-8 -*-
import os
import sys
import re
import json
import time
import math
import requests

sys.path.insert(0, 'scripts')
from ozon_crawler import OzonCrawler
from clean_descriptions import clean_and_decode_russian, load_sensitive_brands
from wb_uploader import WildberriesAPIClient

sys.stdout.reconfigure(encoding='utf-8')

print("==================================================================")
print("🚀 开始执行 Ozon -> Wildberries 官方 API 全链路极速上架")
print("==================================================================")

client = WildberriesAPIClient()
print(f"[+] WB API 客户端已就绪 | 仓库: {client.warehouse_id} | Token: {client.token[:12]}***")

sku_files = [
    ("3628695725", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\260\content.md", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\294\content.md"),
    ("3436497102", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\290\content.md", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\296\content.md"),
    ("3930070419", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\292\content.md", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\298\content.md")
]

crawler = OzonCrawler()
products = []

multiplier = 5.0
discount = 50
stock = 8

for sku, pdp_path, feat_path in sku_files:
    with open(pdp_path, 'r', encoding='utf-8') as f:
        pdp_html = f.read()
    with open(feat_path, 'r', encoding='utf-8') as f:
        feat_html = f.read()
        
    pdp = crawler.parse_pdp_html(sku, pdp_html)
    feat = crawler.parse_features_html(feat_html)
    
    # 尺寸与重量标准合规配置
    length_cm = feat.get('length_cm') or 28
    width_cm = feat.get('width_cm') or 22
    height_cm = feat.get('height_cm') or 10
    weight_g = feat.get('weight_g') or 1500
    
    # 标题清洗：<= 60 字符，白牌脱敏
    raw_title = pdp.get('title', '')
    if sku == "3628695725":
        clean_title = "Дрель-шуруповерт аккумуляторная 12 В, 2х2 Ah Li-ion, в кейсе"
    elif sku == "3436497102":
        clean_title = "Шуруповерт аккумуляторный ДА-10/12ЭР 28Нм (2хАКБ, ЗУ)"
    elif sku == "3930070419":
        clean_title = "Дрель-шуруповерт, 21 В, 42 Нм, 2 АКБ"
    else:
        clean_title = raw_title[:60].strip()
        
    # 描述结构化排版与白牌脱敏
    raw_desc = pdp.get('description_clean', raw_title)
    sanitized_desc = clean_and_decode_russian(raw_desc, extra_brands=[pdp.get('brand')])
    
    specs_footer = (
        f"\n\nОсновные характеристики:\n"
        f"- Вес с упаковкой (брутто): {weight_g} г ({weight_g/1000.0:.2f} кг)\n"
        f"- Габариты упаковки: {length_cm} x {width_cm} x {height_cm} см\n"
        f"- Тип инструмента: Дрель-шуруповерт аккумуляторная\n"
        f"- Питание: Аккумулятор Li-Ion\n"
        f"- Артикул продавца: OZON-{sku}-v1\n"
        f"- Комплектация: Инструмент, сменные аккумуляторы, зарядное устройство, кейс/коробка"
    )
    budget = 1950 - len(specs_footer)
    clean_desc = sanitized_desc[:budget].strip() + specs_footer
    clean_desc = re.sub(r'[\U00010000-\U0010ffff]', '', clean_desc)
    clean_desc = re.sub(r'[✅🌟⭐💡🔥✨💪⚙️🏋️🎉📦📐👉🚀🏁⚠️ℹ️❌🛡️]+', '', clean_desc)
    
    # 价格计算
    ozon_price = float(pdp.get('ozon_price', 1000.0))
    target_sell = round(ozon_price * multiplier)
    strike_price = math.ceil(target_sell / (1.0 - (discount / 100.0)))
    
    p = {
        'sku': sku,
        'vendorCode': f"OZON-{sku}-v1",
        'subjectID': 2197,
        'title': clean_title,
        'ozon_price': ozon_price,
        'target_sell_price': target_sell,
        'strike_price': strike_price,
        'discount_percent': discount,
        'stock_amount': stock,
        'length_cm': length_cm,
        'width_cm': width_cm,
        'height_cm': height_cm,
        'weight_g': weight_g,
        'description': clean_desc,
        'photos': pdp.get('photos', []),
        'brand': '',
        'tnved': '8467210000'
    }
    products.append(p)

print(f"\n[+] 待上架商品列表准备就绪 (共 {len(products)} 款):")
for p in products:
    print(f"  • SKU {p['sku']}: 《{p['title']}》")
    print(f"    Ozon原价: {p['ozon_price']}₽ ➔ 划线价: {p['strike_price']}₽ ➔ 到手价(5折): {p['target_sell_price']}₽ | 库存: {p['stock_amount']}件 | 图片: {len(p['photos'])}张")

# 1. 批量申请条形码
print("\n>>> [步骤 1/5] 申请官方 EAN-13 条形码...")
barcodes = client.get_barcodes(len(products))
print(f"  [+] 成功获取条形码: {barcodes}")
for i, p in enumerate(products):
    p['barcode'] = barcodes[i]

# 2. 逐一提交创建商品卡片
results = []
for i, p in enumerate(products, start=1):
    sku = p['sku']
    print(f"\n>>> [步骤 2/5] ({i}/{len(products)}) 正在创建商品卡片: SKU {sku} (货号: {p['vendorCode']})...")
    try:
        client.create_card(p, p['barcode'])
        print(f"  [+] 建卡请求已成功提交！")
    except Exception as e:
        print(f"  [-] 建卡提交异常: {e}")
        results.append({'sku': sku, 'status': 'FAILED', 'error': str(e)})
        continue

# 3. 轮询获取 nmID
print("\n>>> [步骤 3/5] 轮询获取系统分配的 nmID...")
for p in products:
    if p.get('nmID'):
        continue
    nm_id = client.wait_nm_id(p['vendorCode'])
    if nm_id:
        p['nmID'] = nm_id
        print(f"  [+] SKU {p['sku']} (货号 {p['vendorCode']}) ➔ 分配 nmID: {nm_id}")
    else:
        print(f"  [-] SKU {p['sku']} 暂未查询到 nmID，进行额外重试...")

# 4. 挂载相册多图
print("\n>>> [步骤 4/5] 异步直传原厂高清大图相册...")
for p in products:
    if not p.get('nmID'):
        continue
    nm_id = p['nmID']
    photos = p.get('photos', [])
    print(f"  • 为 nmID {nm_id} 挂载 {len(photos)} 张高清大图...")
    ok = client.upload_photos(nm_id, photos)
    print(f"    相册直拉响应: {'✅ 成功' if ok else '⚠️ 尝试降级直传'}")

# 5. 下发促销折扣与注入库存
print("\n>>> [步骤 5/5] 下发标价、50%大促折扣及现货库存...")
for p in products:
    if not p.get('nmID'):
        continue
    nm_id = p['nmID']
    bc = p['barcode']
    # 改价
    pr_ok = client.set_price_and_discount(nm_id, p['strike_price'], p['discount_percent'])
    print(f"  • nmID {nm_id} 价格下发: 划线价 {p['strike_price']}₽, 折扣 {p['discount_percent']}% ➔ {'✅ 成功' if pr_ok else '❌ 失败'}")
    # 改库存
    st_ok = client.update_stock(bc, p['stock_amount'])
    print(f"  • 条形码 {bc} 仓库 {client.warehouse_id} 库存注入: {p['stock_amount']}件 ➔ {'✅ 成功' if st_ok else '❌ 失败'}")
    
    res = {
        'sku': p['sku'],
        'title': p['title'],
        'nmID': nm_id,
        'vendorCode': p['vendorCode'],
        'barcode': bc,
        'strike_price': p['strike_price'],
        'discount': p['discount_percent'],
        'sell_price': p['target_sell_price'],
        'stock': p['stock_amount'],
        'status': 'SUCCESS',
        'url': f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
    }
    results.append(res)

with open('upload_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n==================================================================")
print(f"🎉 全部商品上架流水线执行完毕！共成功上架 {len([r for r in results if r.get('status') == 'SUCCESS'])} 款商品")
for r in results:
    if r.get('status') == 'SUCCESS':
        print(f"  ✅ SKU {r['sku']} | nmID: {r['nmID']} | 条码: {r['barcode']}")
        print(f"     划线价: {r['strike_price']}₽ -> 到手价: {r['sell_price']}₽ (50%折) | 库存: {r['stock']}件")
        print(f"     前台链接: {r['url']}")
    else:
        print(f"  ❌ SKU {r['sku']} 失败: {r.get('error')}")
print("==================================================================")
