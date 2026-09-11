# -*- coding: utf-8 -*-
"""
Wildberries (WB) 官方 API 全链路独立上架客户端 (专供 Codex / 自动化程序使用)
依赖: pip install requests
"""
import os
import sys
import time
import math
import json
import re
import requests
from typing import List, Dict, Any, Optional

def load_config() -> Dict[str, Any]:
    """优先从 config.json 自动装载配置"""
    candidates = [
        r'd:\视频文件\config.json',
        os.path.join(os.getcwd(), 'config.json'),
        os.path.join(os.path.dirname(__file__), 'config.json'),
        os.path.join(os.path.dirname(__file__), '..', 'config.json')
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

class WildberriesAPIClient:
    def __init__(self, api_token: Optional[str] = None, warehouse_id: Optional[int] = None):
        """
        初始化 WB 客户端
        自动装载 config.json，并禁用无效系统代理 (trust_env=False)，确保直连稳定
        """
        cfg = load_config()
        self.token = (api_token or cfg.get('wb_api_token') or os.getenv('WB_API_TOKEN') or '').strip()
        self.warehouse_id = warehouse_id or cfg.get('wb_warehouse_id') or int(os.getenv('WB_WAREHOUSE_ID', '120762'))
        
        # 使用直连 Session，彻底屏蔽失效系统代理污染
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({
            'Authorization': self.token,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    # 1. 申请官方 EAN-13 条形码
    def get_barcodes(self, count: int = 1) -> List[str]:
        url = 'https://content-api.wildberries.ru/content/v2/barcodes'
        r = self.session.post(url, json={'count': count}, timeout=20)
        if r.status_code == 200:
            bcs = r.json().get('data', [])
            if len(bcs) == count:
                return bcs
        raise RuntimeError(f'申请条形码失败 (HTTP {r.status_code}): {r.text}')

    # 2. 提交创建卡片草稿
    def create_card(self, product: Dict[str, Any], barcode: str) -> bool:
        url = 'https://content-api.wildberries.ru/content/v2/cards/upload'
        
        # 尺寸严格向下取整 (Math.floor) 确保为整型，严禁浮点数防止 400
        l = max(1, math.floor(float(product.get('length_cm', 10))))
        w = max(1, math.floor(float(product.get('width_cm', 10))))
        h = max(1, math.floor(float(product.get('height_cm', 5))))
        weight_kg = round(int(product.get('weight_g', 200)) / 1000.0, 2)
        if weight_kg <= 0:
            weight_kg = 0.1

        # 属性列表：无品牌授权严禁带 brand/Бренд，保持白牌合规
        chars = product.get('characteristics', [
            {'Предмет': int(product['subjectID'])},
            {'ТНВЭД': str(product.get('tnved', '9504400000'))}
        ])

        # 严格标题长度限制 (WB 官方限制 <= 60 字符)
        raw_title = str(product.get('title', ''))
        title = raw_title
        if len(title) > 60 and '/' in title:
            parts = title.split('/')
            if len(parts[0].strip()) <= 60:
                title = parts[0].strip()
        if len(title) > 60 and ',' in title:
            parts = title.split(',')
            if len(parts[0].strip()) <= 60:
                title = parts[0].strip()
        if len(title) > 60:
            title = title[:60].strip()
            last_space = title.rfind(' ')
            if last_space > 40:
                title = title[:last_space].strip()

        # 严格描述清洗 (严禁任何 emoji 及违规特殊字符)
        desc = str(product.get('description', ''))
        desc = re.sub(r'[\U00010000-\U0010ffff]', '', desc)
        desc = re.sub(r'[✅🌟⭐💡🔥✨💪⚙️🏋️🎉📦📐👉🚀🏁⚠️ℹ️❌🛡️]+', '', desc)
        desc = re.sub(r'\n{3,}', '\n\n', desc).strip()

        max_attempts = 10
        orig_vc = str(product['vendorCode'])
        
        for attempt in range(max_attempts):
            curr_vc = str(product['vendorCode'])
            payload = [{
                'subjectID': int(product['subjectID']),
                'variants': [{
                    'vendorCode': curr_vc,
                    'title': title,
                    'description': desc,
                    'dimensions': {
                        'length': l,
                        'width': w,
                        'height': h,
                        'weightBrutto': weight_kg
                    },
                    'characteristics': chars,
                    'sizes': [{
                        'techSize': '0',
                        'wbSize': '',
                        'price': int(product['strike_price']),
                        'skus': [str(barcode)]
                    }]
                }]
            }]

            r = self.session.post(url, json=payload, timeout=25)
            if r.status_code in [200, 201]:
                return True
            
            if r.status_code == 400 and 'vendor code is used in other cards' in r.text:
                m = re.search(r'-v(\d+)$', curr_vc)
                if m:
                    next_ver = int(m.group(1)) + 1
                    next_vc = re.sub(r'-v\d+$', f'-v{next_ver}', curr_vc)
                else:
                    next_vc = f"{curr_vc}-v2"
                print(f"[!] [货号冲突自愈] 商家货号 {curr_vc} 已存在于店铺（含回收站），自动递增升级为 {next_vc} 并重试...")
                product['vendorCode'] = next_vc
                time.sleep(0.5)
                continue

            raise RuntimeError(f'建卡失败 (HTTP {r.status_code}): {r.text}')

        raise RuntimeError(f'建卡失败: 商家货号 {orig_vc} 及其后续 10 个版本均在店铺中被占用。')

    # 3. 轮询获取系统分配的 nmID
    # 3. 轮询获取系统分配的 nmID (带异步错误检测与120秒安全窗口)
    def wait_nm_id(self, vendor_code: str, max_wait_sec: int = 120, start_time: float = None) -> Optional[int]:
        url = 'https://content-api.wildberries.ru/content/v2/get/cards/list'
        payload = {'settings': {'filter': {'withPhoto': -1}, 'cursor': {'limit': 100}}}
        err_url = 'https://content-api.wildberries.ru/content/v2/cards/error/list'
        
        start = time.time()
        if start_time is None:
            start_time = start

        while time.time() - start < max_wait_sec:
            time.sleep(5)
            # 1. 查询卡片列表是否已成功入库并生成 nmID
            try:
                r = self.session.post(url, json=payload, timeout=15)
                if r.status_code == 200:
                    for card in r.json().get('cards', []):
                        if card.get('vendorCode') == vendor_code:
                            return card.get('nmID')
            except Exception:
                pass

            # 2. 检查异步报错列表，防止卡片被拒后无效盲等
            try:
                r_err = self.session.post(err_url, json={}, timeout=15)
                if r_err.status_code == 200:
                    items = r_err.json().get('data', {}).get('items', [])
                    for it in items:
                        if vendor_code in it.get('vendorCodes', []):
                            errs = it.get('errors', {}).get(vendor_code, [])
                            if errs:
                                raise RuntimeError(f'WB 异步建卡拒绝: {"; ".join(errs)}')
            except RuntimeError:
                raise
            except Exception:
                pass
        return None

    # 4. 挂载相册 (主通道：云端异步直拉)
    def upload_photos(self, nm_id: int, photo_urls: List[str]) -> bool:
        url = 'https://content-api.wildberries.ru/content/v3/media/save'
        payload = {'nmId': nm_id, 'data': photo_urls[:30]}
        try:
            r = self.session.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        
        # 降级通道：本地二进制流直传
        success = 0
        for idx, p_url in enumerate(photo_urls[:10], start=1):
            try:
                r_img = self.session.get(p_url, timeout=10)
                if r_img.status_code == 200:
                    headers = {
                        'Authorization': self.token,
                        'X-Nm-Id': str(nm_id),
                        'X-Photo-Number': str(idx)
                    }
                    files = {'uploadfile': (f'img_{idx}.jpg', r_img.content, 'image/jpeg')}
                    r_f = requests.post('https://content-api.wildberries.ru/content/v3/media/file', headers=headers, files=files, timeout=15)
                    if r_f.status_code == 200:
                        success += 1
            except Exception:
                pass
        return success > 0

    # 5. 下发标价与官方促销折扣
    def set_price_and_discount(self, nm_id: int, strike_price: int, discount_percent: int = 50) -> bool:
        url = 'https://discounts-prices-api.wildberries.ru/api/v2/upload/task'
        payload = {'data': [{'nmID': nm_id, 'price': int(strike_price), 'discount': int(discount_percent)}]}
        for _ in range(3):
            try:
                r = self.session.post(url, json=payload, timeout=15)
                if r.status_code == 200:
                    return True
                time.sleep(2)
            except Exception:
                time.sleep(2)
        return False

    # 6. 注入目标现货仓库库存
    def update_stock(self, barcode: str, amount: int = 200) -> bool:
        url = f'https://marketplace-api.wildberries.ru/api/v3/stocks/{self.warehouse_id}'
        payload = {'stocks': [{'sku': str(barcode), 'amount': int(amount)}]}
        r = self.session.put(url, json=payload, timeout=15)
        return r.status_code in [200, 204]

    # 一键全自动上架流程封装
    def upload_single_product(self, product: Dict[str, Any], ozon_price: float, multiplier: float = 5.0, discount: int = 50, stock: int = 200) -> Dict[str, Any]:
        target_sell = round(ozon_price * multiplier)
        strike_price = math.ceil(target_sell / (1.0 - (discount / 100.0)))
        product['strike_price'] = strike_price

        # 1. 申请条码
        barcode = self.get_barcodes(1)[0]
        product['barcode'] = barcode

        # 2. 创建卡片
        self.create_card(product, barcode)

        # 3. 轮询 nmID
        nm_id = self.wait_nm_id(product['vendorCode'])
        if not nm_id:
            raise RuntimeError(f'未能检索到系统分配的 nmID (vendorCode: {product["vendorCode"]})')
        product['nmID'] = nm_id

        # 4. 直拉多图
        if product.get('photos'):
            self.upload_photos(nm_id, product['photos'])

        # 5. 下发折扣价格
        self.set_price_and_discount(nm_id, strike_price, discount)

        # 6. 注入库存
        self.update_stock(barcode, stock)

        return {
            'nmID': nm_id,
            'barcode': barcode,
            'vendorCode': product['vendorCode'],
            'strike_price': strike_price,
            'discount': discount,
            'sell_price': target_sell,
            'stock': stock
        }
