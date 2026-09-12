# -*- coding: utf-8 -*-
"""
重新上架两个失败 SKU (3039067027, 5669963108) 到 Wildberries
修复: subjectID 246 → 192 (Футболки)
"""
import sys
import os
import json

# 将 scripts 目录加入路径
scripts_dir = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, os.path.abspath(scripts_dir))

from wb_uploader import WildberriesAPIClient

# 加载产品数据
project_dir = os.path.join(os.path.dirname(__file__), '..')
products_path = os.path.join(project_dir, 'products.json')
config_path = os.path.join(project_dir, 'config.json')

with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

with open(products_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

# 找到两个失败的 SKU
target_skus = ['3039067027', '5669963108']
target_products = [p for p in products if p.get('sku') in target_skus]

if not target_products:
    print("❌ 未找到目标 SKU，退出")
    sys.exit(1)

print(f"✅ 找到 {len(target_products)} 个待上架产品")

# 初始化 WB 客户端
client = WildberriesAPIClient(
    api_token=config['wb_api_token'],
    warehouse_id=config.get('wb_warehouse_id', 2200658)
)

multiplier = config.get('default_multiplier', 5.0)
discount = config.get('default_discount', 50)
stock = config.get('default_stock', 10)

for idx, product in enumerate(target_products, 1):
    sku = product['sku']
    title = product.get('title', 'N/A')
    ozon_price = float(product.get('ozon_price', 0))
    
    print(f"\n🚀 [{idx}/{len(target_products)}] 正在上架 SKU [{sku}]《{title}》到店铺【{config.get('store_name', 'RR007')}】...")
    print(f"   subjectID: {product.get('subjectID')} → 映射后: 192 (Футболки)")
    print(f"   Ozon 价格: {ozon_price} → WB 售价: {round(ozon_price * multiplier)}")
    
    try:
        result = client.upload_single_product(
            product=product,
            ozon_price=ozon_price,
            multiplier=multiplier,
            discount=discount,
            stock=stock
        )
        print(f"✅ [{idx}/{len(target_products)}] 上架成功!")
        print(f"   nmID: {result['nmID']}")
        print(f"   条码: {result['barcode']}")
        print(f"   货号: {result['vendorCode']}")
        print(f"   标价: {result['strike_price']} | 折扣: {result['discount']}% | 售价: {result['sell_price']}")
        print(f"   库存: {result['stock']}")
        
        # 更新 products.json 中的数据
        for p in products:
            if p.get('sku') == sku:
                p['nmID'] = result['nmID']
                p['barcode'] = result['barcode']
                p['vendorCode'] = result['vendorCode']
                p['strike_price'] = result['strike_price']
                p['sell_price'] = result['sell_price']
                p['stock'] = result['stock']
                break
                
    except Exception as e:
        print(f"❌ [{idx}/{len(target_products)}] 上架失败 (SKU: {sku}):")
        print(f"   {e}")

# 保存更新后的 products.json
try:
    with open(products_path, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print("\n📝 products.json 已更新保存")
except Exception as e:
    print(f"\n⚠️ 保存 products.json 失败: {e}")

print("\n🏁 全部完成！")
