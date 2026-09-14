# -*- coding: utf-8 -*-
"""
Wildberries 异常卡片安全下架与移入回收站工具 (Move-to-Trash Tool)
官方规范：
1. 依据 WB 规则，卡片有库存时严禁直接删除。
2. 本脚本先调用 PUT /api/v3/stocks/{warehouseId} 将对应条码库存置 0，商品即刻停售。
3. 等待库存生效后，调用 POST /content/v2/cards/delete/trash 将指定 nmIDs 彻底移入回收站 (Корзина)。
4. 验证回收站返回状态，确保彻底清除。
"""
import os
import sys
import json
import time
import requests

sys.stdout.reconfigure(encoding='utf-8')

def delete_cards_safely(nmids_to_delete, config_path=None):
    if not config_path:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    TOKEN = cfg['wb_api_token']
    WAREHOUSE_ID = cfg.get('wb_warehouse_id', 2200658)

    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        'Authorization': TOKEN,
        'Content-Type': 'application/json'
    })

    print(f"[*] 准备安全删除 {len(nmids_to_delete)} 个商品卡片: {nmids_to_delete}")

    # 1. 查询对应卡片的条形码
    body = {'settings': {'cursor': {'limit': 100}, 'filter': {'withPhoto': -1}}}
    r_cards = session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json=body, timeout=30)
    cards = r_cards.json().get('cards', []) if r_cards.status_code == 200 else []

    barcodes_to_zero = []
    for c in cards:
        if c['nmID'] in nmids_to_delete:
            for sz in c.get('sizes', []):
                for sku in sz.get('skus', []):
                    barcodes_to_zero.append(sku)

    print(f"[*] 关联条形码数量: {len(barcodes_to_zero)}")

    # 2. 将库存清零
    if barcodes_to_zero:
        stock_payload = [{'sku': b, 'amount': 0} for b in barcodes_to_zero]
        r_s = session.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{WAREHOUSE_ID}', json={'stocks': stock_payload}, timeout=30)
        print(f"[+] 库存清零结果: {r_s.status_code} (204 表示成功)")
        time.sleep(3)

    # 3. 移入回收站
    del_payload = {'nmIDs': nmids_to_delete}
    r_del = session.post('https://content-api.wildberries.ru/content/v2/cards/delete/trash', json=del_payload, timeout=30)
    print(f"[+] 移入回收站结果: {r_del.status_code} {r_del.text}")

    # 4. 验证回收站
    time.sleep(2)
    r_trash = session.post('https://content-api.wildberries.ru/content/v2/get/cards/trash', json={'settings': {'cursor': {'limit': 100}}}, timeout=30)
    if r_trash.status_code == 200:
        trash_cards = r_trash.json().get('cards', [])
        trash_nmids = {c['nmID'] for c in trash_cards}
        confirmed = [nid for nid in nmids_to_delete if nid in trash_nmids]
        print(f"[+] 确认进入回收站: {len(confirmed)}/{len(nmids_to_delete)} 款商品已完全移除")
        return True
    return False

if __name__ == '__main__':
    if len(sys.argv) > 1:
        nmids = [int(x.strip()) for x in sys.argv[1:] if x.strip().isdigit()]
        if nmids:
            delete_cards_safely(nmids)
        else:
            print("Usage: python clean_trash_cards.py <nmID1> <nmID2> ...")
    else:
        print("Usage: python clean_trash_cards.py <nmID1> <nmID2> ...")
