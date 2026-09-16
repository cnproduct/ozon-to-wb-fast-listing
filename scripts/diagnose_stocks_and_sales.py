import requests
import json
import time
from scripts.session_manager import SessionManager

def diagnose():
    mgr = SessionManager()
    creds = mgr.get_active_session_credentials('c0b68ae1-a612-4886-b197-153f4a00bc57')
    token = creds['wb_api_token']
    wh_id = creds['wb_warehouse_id']
    headers = {'Authorization': token, 'Content-Type': 'application/json'}

    print(f"=== STORE AUDIT FOR KL005 (Warehouse: {wh_id}) ===")

    # 1. Fetch all cards
    cards = []
    cursor = {'limit': 100}
    while True:
        resp = requests.post(
            'https://content-api.wildberries.ru/content/v2/get/cards/list',
            headers=headers,
            json={'settings': {'cursor': cursor, 'filter': {'withPhoto': -1}}}
        )
        if resp.status_code != 200:
            print(f"Error fetching cards: {resp.status_code} {resp.text}")
            break
        data = resp.json()
        batch = data.get('cards', [])
        cards.extend(batch)
        cur = data.get('cursor', {})
        total = cur.get('total', 0)
        updated_at = cur.get('updatedAt', '')
        nm_id_cur = cur.get('nmID', 0)
        if len(batch) < 100 or not updated_at:
            break
        cursor = {'limit': 100, 'updatedAt': updated_at, 'nmID': nm_id_cur}

    print(f"Total live cards in seller catalog: {len(cards)}")

    # 2. Extract barcodes & nmIDs
    barcode_to_card = {}
    nmid_to_card = {}
    for c in cards:
        vendor_code = c.get('vendorCode', '')
        nm_id = c.get('nmID', 0)
        subject_id = c.get('subjectID', 0)
        subject_name = c.get('subjectName', '')
        photos = c.get('photos', [])
        sizes = c.get('sizes', [])
        
        bcs = []
        for s in sizes:
            for sk in s.get('skus', []):
                bcs.append(sk)
                barcode_to_card[sk] = {
                    'vendorCode': vendor_code,
                    'nmID': nm_id,
                    'subjectID': subject_id,
                    'subjectName': subject_name,
                    'hasPhoto': len(photos) > 0,
                    'photoCount': len(photos),
                    'title': c.get('title', '')
                }
        nmid_to_card[nm_id] = {
            'vendorCode': vendor_code,
            'barcodes': bcs,
            'subjectID': subject_id,
            'subjectName': subject_name,
            'photos': photos
        }

    all_barcodes = list(barcode_to_card.keys())
    print(f"Total barcodes mapped: {len(all_barcodes)}")

    # 3. Fetch stocks from warehouse
    stock_map = {}
    for i in range(0, len(all_barcodes), 1000):
        chunk = all_barcodes[i:i+1000]
        resp = requests.post(
            f'https://marketplace-api.wildberries.ru/api/v3/stocks/{wh_id}',
            headers=headers,
            json={'skus': chunk}
        )
        if resp.status_code == 200:
            stk_data = resp.json()
            for item in stk_data.get('stocks', []):
                stock_map[item.get('sku')] = item.get('amount', 0)
        else:
            print(f"Error fetching stocks: {resp.status_code} {resp.text}")

    zero_stock_bcs = []
    has_stock_bcs = []
    for sk in all_barcodes:
        amt = stock_map.get(sk, 0)
        if amt > 0:
            has_stock_bcs.append((sk, amt))
        else:
            zero_stock_bcs.append(sk)

    print(f"\n--- STOCK ANALYSIS ---")
    print(f"Barcodes with Stock > 0: {len(has_stock_bcs)}")
    print(f"Barcodes with Stock == 0: {len(zero_stock_bcs)}")
    if zero_stock_bcs:
        print("Zero stock samples:")
        for sk in zero_stock_bcs[:10]:
            info = barcode_to_card[sk]
            print(f"  Barcode: {sk} | SKU: {info['vendorCode']} | nmID: {info['nmID']} | Title: {info['title'][:40]}")

    # 4. Check prices & quarantine
    print(f"\n--- PRICE & PROMO AUDIT ---")
    nm_ids = list(nmid_to_card.keys())
    price_map = {}
    for i in range(0, len(nm_ids), 1000):
        chunk = nm_ids[i:i+1000]
        p_resp = requests.get(
            'https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',
            headers=headers,
            params={'limit': 1000}
        )
        if p_resp.status_code == 200:
            p_data = p_resp.json().get('data', {}).get('listGoods', [])
            for g in p_data:
                price_map[g.get('nmID')] = {
                    'price': g.get('sizes', [{}])[0].get('price', 0) if g.get('sizes') else 0,
                    'discount': g.get('discount', 0),
                    'currency': g.get('currencyIsoCode4217', '')
                }
        else:
            print(f"Price fetch failed: {p_resp.status_code} {p_resp.text}")

    no_price_nmids = [nid for nid in nm_ids if nid not in price_map or price_map[nid]['price'] == 0]
    print(f"Total nmIDs with valid price set: {len(price_map)}")
    print(f"Total nmIDs missing price or price=0: {len(no_price_nmids)}")

    # Check quarantine
    q_resp = requests.get('https://discounts-prices-api.wildberries.ru/api/v2/quarantine/goods', headers=headers)
    if q_resp.status_code == 200:
        q_data = q_resp.json().get('data', {}).get('quarantineGoods', [])
        print(f"Quarantine goods count: {len(q_data)}")
    else:
        print(f"Quarantine fetch status: {q_resp.status_code}")

    # 5. Check cards error list
    print(f"\n--- CARDS ERROR LIST AUDIT ---")
    err_resp = requests.get('https://content-api.wildberries.ru/content/v2/cards/error/list', headers=headers)
    if err_resp.status_code == 200:
        err_data = err_resp.json().get('data', [])
        print(f"Cards in error state: {len(err_data)}")
        for err in err_data[:10]:
            print(f"  VendorCode: {err.get('vendorCode')} | Errors: {err.get('errors')}")
    else:
        print(f"Error list fetch status: {err_resp.status_code}")

    # 6. Check trash cards
    print(f"\n--- TRASH CARDS AUDIT ---")
    trash_resp = requests.post(
        'https://content-api.wildberries.ru/content/v2/cards/trash',
        headers=headers,
        json={'settings': {'cursor': {'limit': 100}, 'filter': {'withPhoto': -1}}}
    )
    if trash_resp.status_code == 200:
        trash_cards = trash_resp.json().get('cards', [])
        print(f"Cards in Trash: {len(trash_cards)}")
        for tc in trash_cards[:5]:
            print(f"  Trash SKU: {tc.get('vendorCode')} | nmID: {tc.get('nmID')}")
    else:
        print(f"Trash fetch status: {trash_resp.status_code}")

    # 7. Check buyer-side status / availability on Wildberries catalog
    print(f"\n--- BUYER-SIDE (FRONTEND) DETAIL AUDIT ---")
    unsellable_frontend = []
    sellable_frontend = []
    # Test all nm_ids against detail API
    for i in range(0, len(nm_ids), 100):
        chunk = nm_ids[i:i+100]
        nm_str = ';'.join(map(str, chunk))
        wb_detail_resp = requests.get(
            f'https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&nm={nm_str}'
        )
        if wb_detail_resp.status_code == 200:
            products = wb_detail_resp.json().get('data', {}).get('products', [])
            prod_map = {p['id']: p for p in products}
            for nid in chunk:
                if nid not in prod_map:
                    unsellable_frontend.append((nid, 'NOT_IN_WB_INDEX (未收录或已下架/封禁)'))
                else:
                    p = prod_map[nid]
                    total_wh_stocks = sum(sum(st.get('qty', 0) for st in sz.get('stocks', [])) for sz in p.get('sizes', []))
                    if total_wh_stocks == 0:
                        unsellable_frontend.append((nid, f"IN_INDEX_BUT_ZERO_QTY (前台收录但买家端显示缺货/0件)"))
                    else:
                        sellable_frontend.append((nid, total_wh_stocks, p.get('name', '')))
        else:
            print(f"Frontend detail fetch error: {wb_detail_resp.status_code}")

    print(f"Frontend Sellable (买家端可加购/有库存): {len(sellable_frontend)}")
    print(f"Frontend Unsellable (买家端不可售/无库存/未收录): {len(unsellable_frontend)}")
    
    if unsellable_frontend:
        print("\n--- UNSELLABLE FRONTEND BREAKDOWN ---")
        for nid, reason in unsellable_frontend:
            c_info = nmid_to_card.get(nid, {})
            bcs = c_info.get('barcodes', [])
            wh_stock = sum(stock_map.get(b, 0) for b in bcs)
            price_info = price_map.get(nid, {})
            print(f"nmID: {nid} | SKU: {c_info.get('vendorCode')} | Reason: {reason} | WH Stock: {wh_stock} | Price: {price_info.get('price')} (Discount: {price_info.get('discount')}%)")

if __name__ == '__main__':
    diagnose()
