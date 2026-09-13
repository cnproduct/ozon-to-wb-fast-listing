# -*- coding: utf-8 -*-
import sys, json, math, re, time
sys.path.insert(0, 'scripts')
from wb_uploader import WildberriesAPIClient

client = WildberriesAPIClient()
sys.stdout.reconfigure(encoding='utf-8')

# 检查当前卡片列表中的 nmID
r = client.session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={'settings': {'filter': {'withPhoto': -1}, 'cursor': {'limit': 15}}})
existing_cards = {c.get('vendorCode'): c.get('nmID') for c in r.json().get('cards', [])}
print("已分配 nmID 的卡片:", existing_cards)

remaining_skus = [
    ("5417462049", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\493\content.md", 372, "Гель для заживления шрамов, средство от рубцов, 30 мл"),
    ("5170757576", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\495\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("5499577418", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\497\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("5618226967", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\499\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
    ("5501981218", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\501\content.md", 372, "Чистотел от папиллом и бородавок, гель от мозолей, 3 мл"),
]

from ozon_crawler import OzonCrawler
from clean_descriptions import clean_and_decode_russian

crawler = OzonCrawler()
bcs = client.get_barcodes(len(remaining_skus))
print(f"申请后 5 款条形码: {bcs}")

batch_payload = []
for i, (sku, path, sub_id, title) in enumerate(remaining_skus):
    vc = f"OZON-{sku}-v1"
    if vc in existing_cards:
        print(f"SKU {sku} 已存在，跳过建卡")
        continue
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    pdp = crawler.parse_pdp_html(sku, html)
    raw_desc = pdp.get('description_clean', pdp.get('title', ''))
    sanitized_desc = clean_and_decode_russian(raw_desc, extra_brands=[pdp.get('brand')])
    specs = (
        f"\n\nОсновные характеристики:\n"
        f"- Вес с упаковкой: 300 г\n"
        f"- Габариты упаковки: 18 x 10 x 6 см\n"
        f"- Назначение: уход за кожей"
    )
    clean_desc = sanitized_desc[:1950-len(specs)].strip() + specs
    clean_desc = re.sub(r'[\U00010000-\U0010ffff]', '', clean_desc)
    clean_desc = re.sub(r'[✅🌟⭐💡🔥✨💪⚙️🏋️🎉📦📐👉🚀🏁⚠️ℹ️❌🛡️]+', '', clean_desc)
    
    ozon_price = float(pdp.get('ozon_price') or 500.0)
    strike_price = math.ceil(round(ozon_price * 5.0) / 0.5)
    
    batch_payload.append({
        "subjectID": sub_id,
        "variants": [{
            "vendorCode": vc,
            "title": title,
            "description": clean_desc,
            "dimensions": {
                "length": 18,
                "width": 10,
                "height": 6,
                "weightBrutto": 0.3
            },
            "characteristics": [
                {"Предмет": sub_id},
                {"ТНВЭД": "3304990000"}
            ],
            "sizes": [{
                "techSize": "0",
                "wbSize": "",
                "price": strike_price,
                "skus": [str(bcs[i])]
            }]
        }]
    })

print(f"提交批量建卡 payload (共 {len(batch_payload)} 款)...")
r_up = client.session.post('https://content-api.wildberries.ru/content/v2/cards/upload', json=batch_payload)
print(f"建卡响应: HTTP {r_up.status_code} | {r_up.text}")
