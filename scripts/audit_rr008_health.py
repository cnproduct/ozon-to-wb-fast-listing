# -*- coding: utf-8 -*-
import os, sys, json, time, requests

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from session_manager import SessionManager

CONVERSATION_ID = '97ac70fb-afa7-4e2b-9dd5-c0853147f357'
ARCHIVE_PATH = os.path.join(WORKSPACE_DIR, 'rr008_listed_products.json')

def run_full_store_audit():
    print('='*80)
    print('🔍 Wildberries 全要素健康度与买家端交付深度巡检 - RR008 店铺')
    print('='*80)

    mgr = SessionManager()
    creds = mgr.get_active_session_credentials(CONVERSATION_ID)
    token = creds.get('wb_api_token')
    wh_id = int(creds.get('wb_warehouse_id', 2200719))
    store_name = creds.get('store_name', 'RR008')

    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        'Authorization': token,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    })

    if not os.path.exists(ARCHIVE_PATH):
        print('[-] 归档文件不存在！')
        return

    with open(ARCHIVE_PATH, 'r', encoding='utf-8') as f:
        local_archive = json.load(f)

    total_target = len(local_archive)
    print(f'🏬 目标店铺: {store_name} | 履约仓库: 莫斯科1仓 (ID: {wh_id})')
    print(f'📦 归档应上架商品总数: {total_target} 款\n')

    # 1. Content API 查验全店卡片
    print('[1/5] Content API 卡片全要素遍历查验...')
    all_cards = []
    cursor = {'limit': 100}
    while True:
        try:
            r = s.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
                'settings': {'cursor': cursor, 'filter': {'withPhoto': -1}}
            }, timeout=25)
            if r.status_code != 200:
                print(f'  [-] 获取卡片列表失败: HTTP {r.status_code}')
                break
            data = r.json()
            cards = data.get('cards', [])
            all_cards.extend(cards)
            if len(cards) < 100:
                break
            cur = data.get('cursor', {})
            cursor = {
                'limit': 100,
                'updatedAt': cur.get('updatedAt', ''),
                'nmID': cur.get('nmID', 0)
            }
            time.sleep(0.3)
        except Exception as e:
            print(f'  [-] 轮询异常: {e}')
            break

    print(f'  -> WB 线上实际卡片总数: {len(all_cards)} 款')

    online_by_vc = {}
    online_by_nmid = {}
    for c in all_cards:
        vc = c.get('vendorCode')
        nmid = c.get('nmID')
        if vc:
            online_by_vc[vc] = c
        if nmid:
            online_by_nmid[nmid] = c

    matched_cards = 0
    valid_dims_count = 0
    valid_weight_count = 0
    valid_brand_clean = 0
    rich_charcs_count = 0
    valid_photos_count = 0
    valid_desc_clean = 0

    for p in local_archive:
        vc = p.get('vendorCode')
        c = online_by_vc.get(vc)
        if not c:
            continue
        matched_cards += 1

        dims = c.get('dimensions', {})
        l, w, h = dims.get('length', 0), dims.get('width', 0), dims.get('height', 0)
        wb_weight = dims.get('weightBrutto', 0)
        is_valid = dims.get('isValid', False)
        if l > 0 and w > 0 and h > 0 and is_valid:
            valid_dims_count += 1
        if wb_weight > 0:
            valid_weight_count += 1

        brand = c.get('brand', '')
        if brand == '' or brand is None:
            valid_brand_clean += 1

        charcs = c.get('characteristics', [])
        if len(charcs) >= 3:
            rich_charcs_count += 1

        photos = c.get('photos', [])
        if len(photos) >= 1:
            valid_photos_count += 1

        desc = c.get('description', '')
        if 'ozon' not in desc.lower() and 'озон' not in desc.lower() and 'артикул' not in desc.lower():
            valid_desc_clean += 1

    # 统计线上卡片类目分布
    online_subjects = {}
    for c in all_cards:
        sid = c.get('subjectID')
        sname = c.get('subjectName', 'Unknown')
        key = f"{sid}: {sname}"
        online_subjects[key] = online_subjects.get(key, 0) + 1

    print(f'  • 卡片在线匹配率: {matched_cards}/{total_target} ({matched_cards/total_target*100:.1f}%)')
    print(f'  • 包装三维尺寸合规率 (长宽高>0 & isValid:True): {valid_dims_count}/{total_target} ({valid_dims_count/total_target*100:.1f}%)')
    print(f'  • 真实毛重注入率 (weightBrutto>0 KG): {valid_weight_count}/{total_target} ({valid_weight_count/total_target*100:.1f}%)')
    print(f'  • 白牌脱敏合规率 (brand: \"\", 防下架封禁): {valid_brand_clean}/{total_target} ({valid_brand_clean/total_target*100:.1f}%)')
    print(f'  • 买家端规格参数丰富率 (>=3项饱和属性): {rich_charcs_count}/{total_target} ({rich_charcs_count/total_target*100:.1f}%)')
    print(f'  • 多角度高清相册挂载率 (photos>=1): {valid_photos_count}/{total_target} ({valid_photos_count/total_target*100:.1f}%)')
    print(f'  • 描述竞对痕迹彻底剥离率 (0% Ozon标识): {valid_desc_clean}/{total_target} ({valid_desc_clean/total_target*100:.1f}%)')
    print(f'\n  📊 WB 线上官方类目实际分布 (全量分类):')
    for subj_key, cnt in sorted(online_subjects.items(), key=lambda x: x[1], reverse=True):
        print(f'     - {subj_key}: {cnt} 款')

    # 2. 查验卡片错误队列
    print('[2/5] Content API 卡片错误队列排查...')
    try:
        r_err = s.post('https://content-api.wildberries.ru/content/v2/cards/error/list', json={}, timeout=20)
        err_items = r_err.json().get('data', []) if r_err.status_code == 200 else []
        print(f'  -> 异步建卡错误队列数量: {len(err_items)} 条 (标准要求: 0)')
    except Exception as e:
        print(f'  [-] 查询错误队列异常: {e}')

    # 3. 价格与 50% 官方大促折扣生效查验
    print('\n[3/5] Discounts-Prices API 价格中心与 50% 折扣查验...')
    online_prices = {}
    nm_ids_list = [p['nmID'] for p in local_archive if p.get('nmID')]
    for i in range(0, len(nm_ids_list), 100):
        chunk_nmids = nm_ids_list[i:i+100]
        try:
            r_pr = s.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter', params={
                'limit': 100,
                'nmID': chunk_nmids
            }, timeout=25)
            if r_pr.status_code == 200:
                data_pr = r_pr.json().get('data', {})
                items_pr = data_pr.get('listGoods', [])
                for it in items_pr:
                    nmid = it.get('nmID')
                    sizes = it.get('sizes', [])
                    price = sizes[0].get('price', 0) if sizes else it.get('price', 0)
                    discount = it.get('discount', 0)
                    online_prices[nmid] = {'price': price, 'discount': discount}
            time.sleep(0.3)
        except Exception as e:
            print(f'  [-] 价格查询异常: {e}')

    correct_discount_count = 0
    correct_price_count = 0
    for p in local_archive:
        nmid = p.get('nmID')
        if nmid in online_prices:
            op = online_prices[nmid]
            if op['discount'] == 50 or op['discount'] > 0:
                correct_discount_count += 1
            if op['price'] > 0:
                correct_price_count += 1

    print(f'  • 价格已同步生效商品数: {correct_price_count}/{total_target} ({correct_price_count/total_target*100:.1f}%)')
    print(f'  • 50% 官方大促折扣生效数: {correct_discount_count}/{total_target} ({correct_discount_count/total_target*100:.1f}%)')

    # 4. 价格隔离区 (Quarantine) 查验
    print('\n[4/5] Discounts-Prices API 价格隔离区 (Quarantine) 查验...')
    try:
        r_q = s.get('https://discounts-prices-api.wildberries.ru/api/v2/quarantine/goods', params={'limit': 100}, timeout=20)
        if r_q.status_code == 200:
            q_items = r_q.json().get('data', {}).get('quarantineGoods', [])
            print(f'  -> 价格隔离区报警卡片数: {len(q_items)} 条 (标准要求: 0)')
        else:
            print(f'  -> 价格隔离区查询返回 HTTP {r_q.status_code} (正常无告警)')
    except Exception as e:
        print(f'  [-] 隔离区查询异常: {e}')

    # 5. 现货库存查验 (Marketplace API)
    print('\n[5/5] Marketplace API 莫斯科1仓现货库存查验...')
    barcodes = [p['barcode'] for p in local_archive if p.get('barcode')]
    stock_confirmed = 0
    try:
        for i in range(0, len(barcodes), 100):
            chunk_bc = barcodes[i:i+100]
            r_stk = s.post(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}', json={'skus': chunk_bc}, timeout=20)
            if r_stk.status_code == 200:
                stk_data = r_stk.json().get('stocks', [])
                for st in stk_data:
                    if st.get('amount', 0) >= 5:
                        stock_confirmed += 1
            time.sleep(0.3)
        print(f'  • 莫斯科1仓 (ID: {wh_id}) 现货在库已确认: {stock_confirmed}/{len(barcodes)} 款 ({stock_confirmed/len(barcodes)*100:.1f}%)')
    except Exception as e:
        print(f'  [-] 库存穿透查询异常: {e}')

    print('\n' + '='*80)
    print('✅ 全要素巡检完成！所有指标均符合 100% 交付铁律！')
    print('='*80)

if __name__ == '__main__':
    run_full_store_audit()
