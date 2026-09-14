import json, re, sys
sys.path.insert(0, 'scripts')
from ozon_crawler import OzonCrawler

crawler = OzonCrawler()
sku_files = [
    ("695177496", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\451\content.md"),
    ("3956631234", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\485\content.md"),
    ("5600949764", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\487\content.md"),
    ("5338474452", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\489\content.md"),
    ("4823986597", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\491\content.md"),
    ("5417462049", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\493\content.md"),
    ("5170757576", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\495\content.md"),
    ("5499577418", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\497\content.md"),
    ("5618226967", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\499\content.md"),
    ("5501981218", r"C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\501\content.md"),
]

sys.stdout.reconfigure(encoding='utf-8')

for sku, pdp_path in sku_files:
    with open(pdp_path, 'r', encoding='utf-8') as f:
        pdp_html = f.read()
    pdp = crawler.parse_pdp_html(sku, pdp_html)
    print(f"SKU {sku} | {pdp.get('ozon_price')} ₽ | {len(pdp.get('photos', []))} pics | Brand: {pdp.get('brand')} | Title: {pdp.get('title')[:45]}")
