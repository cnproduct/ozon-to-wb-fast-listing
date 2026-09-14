# -*- coding: utf-8 -*-
"""
Wildberries 微服务索引监控与 0 标价自动补推工具 (Price Re-Pushing on Index Tool)
背景：
1. Wildberries 的 Content API（商品卡片）与 Discounts-Prices API（价格中心）是异步分离的微服务。
2. 新建卡片需要数十秒至数十分钟排队索引进价格库。刚进库时初始状态为 price: 0（前台隐藏不展示价格）。
3. 本脚本自动扫描全店卡片，发现从“未索引”变为“已入库但 price=0”时，立即调用 upload/task 补推目标划线价与 50% 折扣。
"""
import os
import sys
import json
import time
import requests

sys.stdout.reconfigure(encoding='utf-8')

def repush_missing_or_zero_prices(config_path=None, listing_meta_file=None):
    if not config_path:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    base_dir = os.path.dirname(config_path)

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    TOKEN = cfg['wb_api_token']
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        'Authorization': TOKEN,
        'Content-Type': 'application/json'
    })

    # 读取本地目标价格映射表
    if not listing_meta_file:
        for fname in ['final_74_water_bottles_complete_listing.json', 'products_to_upload.json', 'products.json']:
            fpath = os.path.join(base_dir, fname)
            if os.path.exists(fpath):
                listing_meta_file = fpath
                break

    target_price_map = {}
    if listing_meta_file and os.path.exists(listing_meta_file):
        with open(listing_meta_file, 'r', encoding='utf-8') as f:
            items = json.load(f)
            for it in items:
                nmid = it.get('nmID') or it.get('nm_id')
                strike = it.get('strike_price') or it.get('wb_strike_price')
                if nmid and strike:
                    target_price_map[nmid] = strike

    print(f"[*] 加载目标价格参考库: {len(target_price_map)} 条")

    # 获取价格中心当前商品
    r_p = session.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=1000&offset=0', timeout=30)
    if r_p.status_code != 200:
        print(f"[!] 获取价格列表失败: {r_p.status_code}")
        return

    goods = r_p.json().get('data', {}).get('listGoods', [])
    to_push = []

    for g in goods:
        nmid = g['nmID']
        sizes = g.get('sizes', [])
        p = sizes[0].get('price', 0) if sizes else 0
        if p == 0:
            target_strike = target_price_map.get(nmid)
            if target_strike:
                to_push.append({'nmID': nmid, 'price': target_strike, 'discount': 50})

    print(f"[*] 扫描到 price == 0 需补推的商品数: {len(to_push)}")
    if not to_push:
        print("[+] 恭喜！当前价格中心中所有已索引商品均具备有效价格。")
        return

    r_task = session.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': to_push}, timeout=30)
    print(f"[+] 下发价格补推任务状态: {r_task.status_code}")
    if r_task.status_code == 200:
        uid = r_task.json().get('data', {}).get('id')
        print(f"[+] 任务提交成功，Upload ID: {uid}，等待 4 秒查询处理状态...")
        time.sleep(4)
        r_chk = session.get(f'https://discounts-prices-api.wildberries.ru/api/v2/history/tasks?uploadID={uid}', timeout=30)
        print(f"[+] 任务处理反馈: {r_chk.json().get('data', {})}")

if __name__ == '__main__':
    repush_missing_or_zero_prices()
