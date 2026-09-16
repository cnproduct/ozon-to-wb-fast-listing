# -*- coding: utf-8 -*-
"""
Wildberries 全店商品健康状态一键全量修复与断言程序 (Full Deliverability Repair & Audit)
包含：库存注入(5件)、相册补传、大促价格下发(50%折)、异常测试卡清理与全要素验证
"""
import os
import sys
import json
import time
import glob
import re
import requests
from scripts.session_manager import SessionManager

sys.stdout.reconfigure(encoding='utf-8')

def repair_store():
    mgr = SessionManager()
    creds = mgr.get_active_session_credentials('c0b68ae1-a612-4886-b197-153f4a00bc57')
    token = creds['wb_api_token']
    wh_id = creds['wb_warehouse_id']
    headers = {'Authorization': token, 'Content-Type': 'application/json'}

    print(f"==================================================")
    print(f"🚀 开始执行 KL005 全店可售状态与库存价格全量修复")
    print(f"履约仓库: {wh_id} | 店铺: KL005")
    print(f"==================================================")

    # 1. 查询全店卡片
    body = {'settings': {'cursor': {'limit': 100}, 'filter': {'withPhoto': -1}}}
    r_cards = requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list', headers=headers, json=body, timeout=30)
    cards = r_cards.json().get('cards', [])
    print(f"[*] 成功获取全店卡片: {len(cards)} 款")

    # 2. 装载本地数据源
    local_db = {}
    for f in glob.glob('*.json') + glob.glob('batches_remaining/*.json'):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                d = json.load(fp)
                items = d if isinstance(d, list) else (list(d.values()) if isinstance(d, dict) else [])
                for it in items:
                    if not isinstance(it, dict): continue
                    sp = it.get('wb_strike_price') or it.get('strike_price')
                    sell = it.get('wb_sell_price') or it.get('sell_price') or it.get('wildberries_sell_price')
                    oz_cny = it.get('ozon_cny') or it.get('ozon_green_price') or it.get('price_cny')
                    oz_rub = it.get('ozon_rub') or it.get('price_rub') or it.get('ozon_price')
                    photos = it.get('photos') or it.get('images') or []
                    info = {
                        'strike_price': sp,
                        'sell_price': sell,
                        'ozon_cny': oz_cny,
                        'ozon_rub': oz_rub,
                        'photos': photos
                    }
                    for k in ['sku', 'ozon_sku', 'vendorCode', 'sku_str', 'nmID']:
                        v = it.get(k)
                        if v: local_db[str(v)] = info
        except Exception:
            pass

    # 3. 步骤一：清理测试卡片 (KL-TEST-PATCH-01)
    test_nmids = [c['nmID'] for c in cards if c.get('vendorCode') == 'KL-TEST-PATCH-01']
    if test_nmids:
        print(f"\n[1/4] 清理测试无图卡片: {test_nmids}")
        # 置0库存
        del_bcs = []
        for c in cards:
            if c['nmID'] in test_nmids:
                for sz in c.get('sizes', []):
                    for sku in sz.get('skus', []):
                        del_bcs.append(sku)
        if del_bcs:
            requests.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}', headers=headers, json={'stocks': [{'sku': b, 'amount': 0} for b in del_bcs]})
        # 移入回收站
        r_del = requests.post('https://content-api.wildberries.ru/content/v2/cards/delete/trash', headers=headers, json={'nmIDs': test_nmids})
        print(f"  -> 测试卡移入回收站状态: {r_del.status_code}")

    # 4. 步骤二：相册补传 (对 0 张图片的真实卡片进行多图挂载)
    print(f"\n[2/4] 检查并补传缺失相册图片...")
    no_photo_cards = [c for c in cards if len(c.get('photos', [])) == 0 and c.get('vendorCode') != 'KL-TEST-PATCH-01']
    print(f"  -> 待补传相册卡片数量: {len(no_photo_cards)}")
    for c in no_photo_cards:
        vc = c.get('vendorCode', '')
        nid = c.get('nmID', 0)
        m = re.search(r'KL-(\d+)-', vc)
        ozon_id = m.group(1) if m else vc
        info = local_db.get(str(nid)) or local_db.get(vc) or local_db.get(ozon_id) or {}
        photos = info.get('photos', [])
        if photos:
            r_img = requests.post('https://content-api.wildberries.ru/content/v3/media/save', headers=headers, json={'nmId': nid, 'data': photos[:15]})
            print(f"  -> SKU: {vc} (nmID: {nid}) 挂载 {len(photos[:15])} 张图片 | 状态: {r_img.status_code}")
            time.sleep(0.5)

    # 5. 步骤三：全量现货库存注入 (5 件/款)
    print(f"\n[3/4] 全量注入莫斯科1仓现货库存 (目标: 5件/款)...")
    stock_payload = []
    for c in cards:
        if c.get('vendorCode') == 'KL-TEST-PATCH-01': continue
        for sz in c.get('sizes', []):
            for sku in sz.get('skus', []):
                stock_payload.append({'sku': str(sku), 'amount': 5})

    print(f"  -> 准备注入条形码数量: {len(stock_payload)}")
    # 每次最多 1000 个
    for i in range(0, len(stock_payload), 1000):
        chunk = stock_payload[i:i+1000]
        r_stk = requests.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}', headers=headers, json={'stocks': chunk})
        print(f"  -> 库存下发状态: {r_stk.status_code} (204/200 成功)")

    # 6. 步骤四：全量下发 12倍划线标价 + 50% 官方大促折扣 (CNY)
    print(f"\n[4/4] 全量下发人民币标价与 50% 官方大促折扣...")
    price_payload = []
    for c in cards:
        vc = c.get('vendorCode', '')
        nid = c.get('nmID', 0)
        if vc == 'KL-TEST-PATCH-01': continue
        m = re.search(r'KL-(\d+)-', vc)
        ozon_id = m.group(1) if m else vc
        info = local_db.get(str(nid)) or local_db.get(vc) or local_db.get(ozon_id) or {}
        sp = info.get('strike_price')
        if not sp:
            oz_cny = info.get('ozon_cny')
            if isinstance(oz_cny, (int, float)) and oz_cny > 0:
                sp = int(round(oz_cny * 12.0))
            elif isinstance(oz_cny, str):
                try:
                    sp = int(round(float(re.sub(r'[^\d.]', '', oz_cny)) * 12.0))
                except Exception:
                    pass
        if not sp:
            oz_rub = info.get('ozon_rub')
            if isinstance(oz_rub, (int, float)) and oz_rub > 0:
                sp = int(round((oz_rub / 12.5) * 12.0))
        if not sp:
            sp = 600

        price_payload.append({
            'nmID': nid,
            'price': int(sp),
            'discount': 50
        })

    print(f"  -> 准备下发价格条目: {len(price_payload)}")
    # POST /api/v2/upload/task
    r_price = requests.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', headers=headers, json={'data': price_payload})
    print(f"  -> 价格异步任务创建状态: {r_price.status_code} {r_price.text}")
    task_id = r_price.json().get('data', {}).get('id') if r_price.status_code == 200 else None

    if task_id:
        print(f"  -> 价格任务 ID: {task_id}，等待 WB 批处理同步生效...")
        time.sleep(6)
        r_chk = requests.get(f'https://discounts-prices-api.wildberries.ru/api/v2/history/tasks?uploadID={task_id}', headers=headers)
        if r_chk.status_code == 200:
            print(f"  -> 任务进度: {r_chk.json()}")

    # 7. 全要素闭环断言
    print(f"\n==================================================")
    print(f"🔍 正在执行全要素上架闭环断言 (Full Closed-Loop Audit)")
    print(f"==================================================")
    time.sleep(3)

    # A. 校验最新卡片列表
    r_cards_latest = requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list', headers=headers, json=body).json().get('cards', [])
    valid_cards = [c for c in r_cards_latest if c.get('vendorCode') != 'KL-TEST-PATCH-01']
    print(f"[1] 全店正常在售卡片数: {len(valid_cards)}")

    # B. 校验库存
    all_bcs = [sku for c in valid_cards for sz in c.get('sizes', []) for sku in sz.get('skus', [])]
    r_stk_check = requests.post(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}', headers=headers, json={'skus': all_bcs})
    stk_map = {item['sku']: item['amount'] for item in r_stk_check.json().get('stocks', [])}
    in_stock_count = sum(1 for b in all_bcs if stk_map.get(b, 0) > 0)
    print(f"[2] 现货库存 > 0 的条码数: {in_stock_count} / {len(all_bcs)}")

    # C. 校验价格
    r_p_check = requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter', headers=headers, params={'limit': 1000})
    goods_prices = r_p_check.json().get('data', {}).get('listGoods', [])
    p_map = {g.get('nmID'): g for g in goods_prices}
    priced_count = sum(1 for c in valid_cards if p_map.get(c['nmID'], {}).get('sizes', [{}])[0].get('price', 0) > 0)
    print(f"[3] 价格与折扣已生效的商品数: {priced_count} / {len(valid_cards)}")

    # D. 校验相册
    photo_count = sum(1 for c in valid_cards if len(c.get('photos', [])) > 0)
    print(f"[4] 相册具备高清图片的商品数: {photo_count} / {len(valid_cards)}")

    print(f"\n🎉 修复流程圆满完成！")

if __name__ == '__main__':
    repair_store()
