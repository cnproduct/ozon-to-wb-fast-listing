# -*- coding: utf-8 -*-
"""
Wildberries 11款商品逐一批量上架流水线脚本
按照用户指定规则：
- 售价 = Ozon 售价 * 5 倍
- 折扣 = 50% 官方大促
- 现货库存 = 10 件 (莫斯科1仓 ID: 2156484)
"""
import os
import sys
import json
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from wb_uploader import WildberriesAPIClient

def main():
    json_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'products.json')
    if not os.path.exists(json_path):
        json_path = 'products.json'

    with open(json_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    client = WildberriesAPIClient()
    total = len(products)
    print("=" * 60)
    print(f"🚀 开始执行 Wildberries 11 款商品批量上架流水线 (共 {total} 款)")
    print(f"   店铺: RR006 | 仓库: 莫斯科1仓 ({client.warehouse_id})")
    print(f"   策略: 实售价 5.0 倍 | 折扣 50% | 库存 10 件")
    print("=" * 60)

    results = []

    for i, p in enumerate(products, 1):
        sku = p['sku']
        title = p['title']
        price = p['ozon_price']
        print(f"\n[{i}/{total}] >>> 正在处理 Ozon SKU: {sku}")
        print(f"   标题: {title}")
        print(f"   原价: {price} ₽ | 目标到手价: {round(price * 5)} ₽ | 图片: {len(p.get('photos', []))} 张")

        # 检查是否此前已上架成功
        if p.get('nmID'):
            nm_id = p['nmID']
            vc = p.get('vendorCode', f'OZON-{sku}')
            bc = p.get('barcode', '')
            res = {
                'sku': sku,
                'title': title,
                'nmID': nm_id,
                'vendorCode': vc,
                'barcode': bc,
                'strike_price': round(price * 10),
                'discount': 50,
                'sell_price': round(price * 5),
                'stock': 10,
                'status': 'SUCCESS',
                'url': f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
            }
            results.append(res)
            print(f"   ⚡ [已完成] 历史已上架成功! nmID: {nm_id} | 货号: {vc} | 链接: {res['url']}")
            continue

        try:
            res = client.upload_single_product(
                product=p,
                ozon_price=price,
                multiplier=5.0,
                discount=50,
                stock=10
            )
            res['sku'] = sku
            res['title'] = title
            res['status'] = 'SUCCESS'
            res['url'] = f"https://www.wildberries.ru/catalog/{res['nmID']}/detail.aspx"
            results.append(res)
            p['nmID'] = res['nmID']
            p['barcode'] = res['barcode']
            print(f"   ✅ 上架成功! nmID: {res['nmID']} | 货号: {res['vendorCode']} | 条码: {res['barcode']}")
            print(f"      标价: {res['strike_price']} ₽ -> 50%折 -> 到手: {res['sell_price']} ₽ | 库存: {res['stock']}件")
            print(f"      链接: {res['url']}")
        except Exception as e:
            print(f"   ❌ 上架异常: {e}")
            results.append({
                'sku': sku,
                'title': title,
                'status': 'FAILED',
                'error': str(e)
            })

        # 即时持久化，防止断点丢失
        with open('upload_results.json', 'w', encoding='utf-8') as rf:
            json.dump(results, rf, ensure_ascii=False, indent=2)
        with open(json_path, 'w', encoding='utf-8') as pf:
            json.dump(products, pf, ensure_ascii=False, indent=2)

        if i < total:
            time.sleep(3)

    print("\n" + "=" * 60)
    print("🏁 全部 11 款商品批量上架执行完毕！汇总汇报：")
    print("=" * 60)
    success_count = sum(1 for r in results if r.get('status') == 'SUCCESS')
    print(f"成功: {success_count}/{total} 款 | 失败: {total - success_count}/{total} 款\n")

    with open('upload_results.json', 'w', encoding='utf-8') as rf:
        json.dump(results, rf, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
