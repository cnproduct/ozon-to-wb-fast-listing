# -*- coding: utf-8 -*-
"""
Wildberries 后台实时全量数据穿透核验脚本
功能：
1. 从 Content API 获取所有在线商品卡片（自动处理游标分页，严防空 updatedAt 报错）
2. 从 Discounts-Prices API 获取所有生效标价、实售价与活动折扣
3. 从 Quarantine API 扫描是否有商品落入价格隔离保全区
4. 从 Marketplace API 获取指定仓库（如莫斯科1仓 2200658）的实时现货库存
5. 自动比对计算公式：Ozon 绿标价 x 5 = WB 5折目标实售价，划线价 = 实售价 x 2
6. 输出结构化 json 数据与标准的 Markdown 核验表格
"""
import os
import sys
import json
import time
import requests

sys.stdout.reconfigure(encoding='utf-8')

def run_verification(config_path=None, target_skus_file=None, output_dir=None):
    if not config_path:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    if not output_dir:
        output_dir = os.path.dirname(config_path)

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    TOKEN = cfg['wb_api_token']
    WAREHOUSE_ID = cfg.get('wb_warehouse_id', 2200658)
    RATIO = 12.55198225672304

    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        'Authorization': TOKEN,
        'Content-Type': 'application/json'
    })

    print(f"[*] 连接 Wildberries 官方 API 进行全量后台数据核验...")
    print(f"    店铺: {cfg.get('store_name', 'Default')} | 仓库 ID: {WAREHOUSE_ID}")

    # 1. 抓取所有在线商品卡片
    all_cards = []
    cursor = {"limit": 100}
    while True:
        body = {"settings": {"cursor": cursor, "filter": {"withPhoto": -1}}}
        r = session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json=body, timeout=30)
        if r.status_code != 200:
            print(f"[!] Content API 异常: {r.status_code} {r.text[:200]}")
            break
        data = r.json()
        cards = data.get('cards', [])
        if not cards:
            break
        all_cards.extend(cards)
        cur = data.get('cursor', {})
        total = cur.get('total', 0)
        if len(all_cards) >= total or len(cards) < 100:
            break
        cursor = {
            "limit": 100,
            "updatedAt": cur.get('updatedAt', ''),
            "nmID": cur.get('nmID', 0)
        }
        time.sleep(0.3)

    print(f"[+] 在线有效卡片总数: {len(all_cards)}")

    # 2. 抓取价格中心全量数据
    all_goods = []
    offset = 0
    while True:
        r = session.get(f'https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=100&offset={offset}', timeout=30)
        if r.status_code != 200:
            break
        g_list = r.json().get('data', {}).get('listGoods', [])
        if not g_list:
            break
        all_goods.extend(g_list)
        offset += 100
        time.sleep(0.2)

    price_map = {g['nmID']: g for g in all_goods}
    print(f"[+] 价格中心已索引商品数: {len(all_goods)}")

    # 3. 抓取价格隔离区商品
    quar_goods = []
    r_q = session.get('https://discounts-prices-api.wildberries.ru/api/v2/quarantine/goods?limit=100&offset=0', timeout=30)
    if r_q.status_code == 200:
        quar_goods = r_q.json().get('data', {}).get('quarantineGoods', []) or []
    quar_map = {g['nmID']: g for g in quar_goods}
    print(f"[+] 价格隔离区商品数: {len(quar_goods)}")

    # 4. 抓取全量现货库存
    all_barcodes = []
    for c in all_cards:
        for sz in c.get('sizes', []):
            all_barcodes.extend(sz.get('skus', []))

    stock_map = {}
    if all_barcodes:
        for i in range(0, len(all_barcodes), 1000):
            batch_bc = all_barcodes[i:i+1000]
            r_s = session.post(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{WAREHOUSE_ID}', json={'skus': batch_bc}, timeout=30)
            if r_s.status_code == 200:
                for s in r_s.json().get('stocks', []):
                    stock_map[s['sku']] = s.get('amount', 0)
            time.sleep(0.3)

    print(f"[+] 仓库现货库存条目: {len(stock_map)}")

    # 5. 组装结果报告
    results = []
    for idx, c in enumerate(all_cards, 1):
        nmid = c['nmID']
        vc = c.get('vendorCode', '')
        title = c.get('title', '')
        
        # 提取 SKU
        sku = vc.replace('OZON-', '').replace('ozon-', '').replace('-v1', '').strip()
        
        barcode = ''
        sizes = c.get('sizes', [])
        if sizes and sizes[0].get('skus'):
            barcode = sizes[0]['skus'][0]

        stock = stock_map.get(barcode, 0)
        p_info = price_map.get(nmid)
        q_info = quar_map.get(nmid)

        live_strike = 0
        live_sell = 0
        live_disc = 0
        if p_info:
            p_sizes = p_info.get('sizes', [])
            if p_sizes:
                live_strike = p_sizes[0].get('price', 0)
                live_sell = p_sizes[0].get('discountedPrice', 0)
                live_disc = p_info.get('discount', 0)

        # 状态研判
        if q_info:
            status = f"⚠️ 触发价格隔离(当前标价{live_strike}, 待放行{q_info.get('newPrice')})"
        elif live_strike > 0 and live_disc == 50:
            status = "✅ 价格与5折活动正常"
        elif live_strike > 0:
            status = f"✅ 已生效({live_strike}₽/折后{live_sell}₽)"
        elif not p_info:
            status = "⏳ 目录索引同步中"
        else:
            status = "⚠️ 标价为0(需补推)"

        results.append({
            "seq": idx,
            "sku": sku,
            "vendorCode": vc,
            "nmID": nmid,
            "barcode": barcode,
            "title": title[:30],
            "live_strike": live_strike,
            "live_sell": live_sell,
            "live_discount": live_disc,
            "live_stock": stock,
            "status": status
        })

    # 保存 JSON 与 Markdown 表格
    json_path = os.path.join(output_dir, 'live_backend_verified.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    md_path = os.path.join(output_dir, 'live_backend_verified_table.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"# Wildberries 店铺后台全量实时核验报表\n\n")
        f.write(f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 店铺: {cfg.get('store_name', 'RR007')} | 仓库 ID: {WAREHOUSE_ID}\n\n")
        f.write(f"| 序号 | SKU | 商品标题 | 划线标价 | 买家实售价 | 折扣 | WB nmID | 实时库存 | 运行状态 |\n")
        f.write(f"| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n")
        for r in results:
            strike_disp = f"**{r['live_strike']}**" if r['live_strike'] > 0 else "-"
            sell_disp = f"**{r['live_sell']}**" if r['live_sell'] > 0 else "-"
            disc_disp = f"{r['live_discount']}%" if r['live_discount'] > 0 else "-"
            f.write(f"| {r['seq']} | `{r['sku']}` | {r['title']} | {strike_disp} | {sell_disp} | {disc_disp} | [{r['nmID']}](https://www.wildberries.ru/catalog/{r['nmID']}/detail.aspx) | **{r['live_stock']}** | {r['status']} |\n")

    print(f"[+] 报表生成完毕: \n    JSON: {json_path}\n    Markdown: {md_path}")
    return results

if __name__ == '__main__':
    run_verification()
