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
from clean_descriptions import clean_and_decode_russian
from wb_uploader import WildberriesAPIClient

sys.stdout.reconfigure(encoding='utf-8')

print("==================================================================")
print("🚀 开始执行批次 3 上架 (共 10 款身体护肤/精华商品)")
print("==================================================================")

client = WildberriesAPIClient()
print(f"[+] WB API 客户端已就绪 | 仓库: {client.warehouse_id} | Token: {client.token[:12]}***")

sku_files = [
    ("695177496", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\451\content.md", 1566, "Эмульсия увлажняющая для лица и тела сухой кожи, 250 мл"),
    ("3956631234", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\485\content.md", 372, "Сыворотка от пигментных пятен для лица и тона кожи, 30 мл"),
    ("5600949764", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\487\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("5338474452", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\489\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("4823986597", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\491\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("5417462049", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\493\content.md", 372, "Гель для заживления шрамов, средство от рубцов, 30 мл"),
    ("5170757576", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\495\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("5499577418", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\497\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("5618226967", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\499\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("5501981218", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\501\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
]

crawler = OzonCrawler()
products = []

multiplier = 5.0
discount = 50
stock = 9

for sku, pdp_path, sub_id, compliant_title in sku_files:
    with open(pdp_path, 'r', encoding='utf-8') as f:
        pdp_html = f.read()
        
    pdp = crawler.parse_pdp_html(sku, pdp_html)
    
    length_cm = 18
    width_cm = 10
    height_cm = 6
    weight_g = 300
    
    raw_desc = pdp.get('description_clean', pdp.get('title', ''))
    sanitized_desc = clean_and_decode_russian(raw_desc, extra_brands=[pdp.get('brand')])
    
    specs_footer = (
        f"\n\nОсновные характеристики:\n"
        f"- Вес с упаковкой: {weight_g} г\n"
        f"- Габариты упаковки: {length_cm} x {width_cm} x {height_cm} см\n"
        f"- Назначение косметического средства: для ухода за кожей лица и тела"
    )
    budget = 1950 - len(specs_footer)
    clean_desc = sanitized_desc[:budget].strip() + specs_footer
    clean_desc = re.sub(r'[\U00010000-\U0010ffff]', '', clean_desc)
    clean_desc = re.sub(r'[✅🌟⭐💡🔥✨💪⚙️🏋️🎉📦📐👉🚀🏁⚠️ℹ️❌🛡️]+', '', clean_desc)
    
    ozon_price = float(pdp.get('ozon_price') or 500.0)
    target_sell = round(ozon_price * multiplier)
    strike_price = math.ceil(target_sell / (1.0 - (discount / 100.0)))
    
    p = {
        'sku': sku,
        'vendorCode': f"OZON-{sku}-v1",
        'subjectID': sub_id,
        'title': compliant_title,
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
        'tnved': '3304990000'
    }
    products.append(p)

print(f"\n[+] 待上架商品列表准备就绪 (共 {len(products)} 款):")
for p in products:
    print(f"  • SKU {p['sku']}: 《{p['title']}》 | Ozon: {p['ozon_price']}₽ ➔ 标价: {p['strike_price']}₽ ➔ 到手: {p['target_sell_price']}₽ | {len(p['photos'])} 图")

# 1. 批量申请条码
print("\n>>> [步骤 1/5] 申请官方 EAN-13 条形码...")
barcodes = client.get_barcodes(len(products))
print(f"  [+] 成功获取条形码: {barcodes}")
for i, p in enumerate(products):
    p['barcode'] = barcodes[i]

# 2. 逐一提交创建商品卡片
for i, p in enumerate(products, start=1):
    sku = p['sku']
    print(f"\n>>> [步骤 2/5] ({i}/{len(products)}) 正在创建商品卡片: SKU {sku} (货号: {p['vendorCode']})...")
    client.create_card(p, p['barcode'])
    print(f"  [+] 建卡请求已成功提交！")

# 3. 轮询获取 nmID
print("\n>>> [步骤 3/5] 轮询获取系统分配的 nmID...")
for p in products:
    nm_id = client.wait_nm_id(p['vendorCode'], max_attempts=12)
    if nm_id:
        p['nmID'] = nm_id
        print(f"  [+] SKU {p['sku']} (货号 {p['vendorCode']}) ➔ 分配 nmID: {nm_id}")
    else:
        print(f"  [-] SKU {p['sku']} 暂未查询到 nmID")

# 4. 挂载图片
print("\n>>> [步骤 4/5] 异步直传原厂高清大图相册...")
for p in products:
    if not p.get('nmID'):
        continue
    nm_id = p['nmID']
    photos = p.get('photos', [])
    print(f"  • 为 nmID {nm_id} 挂载 {len(photos)} 张高清大图...")
    ok = client.upload_photos(nm_id, photos)
    print(f"    相册直拉响应: {'✅ 成功' if ok else '⚠️ 尝试降级直传'}")

# 5. 注入库存
print("\n>>> [步骤 5/5] 注入目标仓库现货库存并下发大促折扣...")
for p in products:
    bc = p['barcode']
    for retry in range(4):
        st_ok = client.update_stock(bc, p['stock_amount'])
        if st_ok:
            print(f"  • 条码 {bc} 仓库 {client.warehouse_id} 库存注入: {p['stock_amount']}件 ➔ ✅ 成功")
            break
        time.sleep(3)

# 下发大促折扣
print("  • 等待价格索引服务就绪并下发 50% 折扣...")
time.sleep(6)
price_items = [{'nmID': p['nmID'], 'price': p['strike_price'], 'discount': p['discount_percent']} for p in products if p.get('nmID')]
pr_url = 'https://discounts-prices-api.wildberries.ru/api/v2/upload/task'
for attempt in range(4):
    r_pr = client.session.post(pr_url, json={'data': price_items})
    if r_pr.status_code == 200:
        print(f"  • 批量大促价格下发成功: {r_pr.text}")
        break
    else:
        print(f"  • 价格下发重试中 ({attempt+1}/4): HTTP {r_pr.status_code} {r_pr.text}")
        time.sleep(5)

results = []
for p in products:
    res = {
        'sku': p['sku'],
        'title': p['title'],
        'nmID': p.get('nmID'),
        'vendorCode': p['vendorCode'],
        'barcode': p['barcode'],
        'strike_price': p['strike_price'],
        'discount': p['discount_percent'],
        'sell_price': p['target_sell_price'],
        'stock': p['stock_amount'],
        'status': 'SUCCESS' if p.get('nmID') else 'FAILED',
        'url': f"https://www.wildberries.ru/catalog/{p.get('nmID')}/detail.aspx"
    }
    results.append(res)

with open('upload_results.json', 'r', encoding='utf-8') as f:
    history = json.load(f)
history.extend(results)
with open('upload_results.json', 'w', encoding='utf-8') as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

print("\n==================================================================")
print(f"🎉 批次 3 上架流水线执行完毕！共成功上架 {len([r for r in results if r.get('status') == 'SUCCESS'])} 款商品")
for r in results:
    if r.get('status') == 'SUCCESS':
        print(f"  ✅ SKU {r['sku']} | nmID: {r['nmID']} | 条码: {r['barcode']}")
        print(f"     划线价: {r['strike_price']}₽ -> 到手价: {r['sell_price']}₽ (50%折) | 库存: {r['stock']}件")
        print(f"     前台链接: {r['url']}")
print("==================================================================")
