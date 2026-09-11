# -*- coding: utf-8 -*-
"""
==============================================================================
Ozon 商品数据智能抓取与解析器 (Ozon Crawler & Extractor v3.0)
==============================================================================
职责：从 Ozon 提取真实标题、原版高清相册、价格、尺寸重量与规格参数，
输出符合 input-schema.md 规范的标准商品 JSON 数组，直接喂给 listing_engine.py。
==============================================================================
"""

import os
import re
import sys
import json
import time
import argparse
import requests
from typing import List, Dict, Any, Optional

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
]

class OzonCrawler:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENTS[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Sec-Ch-Ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"'
        })

    def parse_html_content(self, sku: str, html: str) -> Optional[Dict[str, Any]]:
        """从 Ozon 商品页面 HTML 中智能抽取全量商品结构数据"""
        data = {
            "sku": str(sku),
            "vendorCode": f"OZON-{sku}-v1",
            "title": "",
            "ozon_price": 0.0,
            "length_cm": None,
            "width_cm": None,
            "height_cm": None,
            "weight_g": None,
            "photos": [],
            "description_clean": "",
            "category_path": "",
            "product_type": "",
            "characteristics": []
        }

        # 1. 提取 JSON-LD 结构化数据
        json_ld_matches = re.findall(r'<script\s+type=["\']application/ld\+json["\']>(.*?)</script>', html, re.DOTALL)
        for jm in json_ld_matches:
            try:
                ld = json.loads(jm.strip())
                if isinstance(ld, list):
                    ld = ld[0]
                if ld.get('@type') in ['Product', 'IndividualProduct']:
                    if not data['title'] and ld.get('name'):
                        data['title'] = ld.get('name').strip()
                    if not data['description_clean'] and ld.get('description'):
                        data['description_clean'] = ld.get('description').strip()
                    if ld.get('image'):
                        imgs = ld.get('image')
                        if isinstance(imgs, str):
                            data['photos'].append(imgs)
                        elif isinstance(imgs, list):
                            data['photos'].extend(imgs)
                    if ld.get('offers'):
                        offers = ld.get('offers')
                        if isinstance(offers, dict) and 'price' in offers:
                            try:
                                data['ozon_price'] = float(offers['price'])
                            except Exception:
                                pass
            except Exception:
                pass

        
        # 1.5 提取 Ozon 原生面包屑与品类类型
        bc_matches = re.findall(r'''<a[^>]+href=["']/category/[^"']+["'][^>]*>(.*?)</a>''', html)
        if bc_matches:
            clean_bcs = [re.sub(r'<[^>]+>', '', b).strip() for b in bc_matches if re.sub(r'<[^>]+>', '', b).strip()]
            if clean_bcs:
                data['category_path'] = ' > '.join(clean_bcs[:4])

        type_match = re.search(r'(?:Тип|Категория)[^:]*:\s*([А-Яа-яЁё0-9\s,\-]+)', html)
        if type_match:
            data['product_type'] = type_match.group(1).strip()

        # 2. 正则兜底提取标题 (h1 / meta title)
        if not data['title']:
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if h1_match:
                clean_title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
                if clean_title and len(clean_title) > 5:
                    data['title'] = clean_title

        if not data['title']:
            og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html)
            if og_title:
                data['title'] = og_title.group(1).replace(' - купить на OZON', '').strip()

        # 3. 严格限定仅在主画廊 (webGallery) 容器范围内提取图片，杜绝推荐位/广告位杂图污染
        gallery_scope = html
        gallery_match = re.search(r'data-widget=["\']webGallery["\'][^>]*>(.*?)</div>\s*<div[^>]+data-widget=', html, re.DOTALL)
        if gallery_match:
            gallery_scope = gallery_match.group(1)
        elif 'data-widget="webGallery"' in html:
            # 截取从 webGallery 开始的局部内容
            start_idx = html.find('data-widget="webGallery"')
            gallery_scope = html[start_idx:start_idx+15000]

        photo_urls = re.findall(r'https://[^"\'\s<>]+/(?:s3/)?multimedia[^"\'\s<>]+\.(?:jpg|jpeg|png|webp)', gallery_scope)
        for u in photo_urls:
            if '/wc50/' in u or '/wc100/' in u:
                continue
            u_hd = re.sub(r'/wc\d+/', '/wc1000/', u)
            if u_hd not in data['photos']:
                data['photos'].append(u_hd)

        # 4. 提取价格
        if data['ozon_price'] <= 0:
            price_match = re.search(r'(\d[\d\s]*)\s*₽', html)
            if price_match:
                try:
                    data['ozon_price'] = float(price_match.group(1).replace(' ', '').replace('\xa0', ''))
                except Exception:
                    pass

        # 5. 提取尺寸与重量
        dim_match = re.search(r'(?:Размер упаковки|Габариты)[^:]*:\s*([\d\.,\s/xх*]+)\s*см', html, re.IGNORECASE)
        if dim_match:
            nums = re.findall(r'\d+(?:\.\d+)?', dim_match.group(1).replace(',', '.'))
            if len(nums) >= 3:
                try:
                    data['length_cm'] = float(nums[0])
                    data['width_cm'] = float(nums[1])
                    data['height_cm'] = float(nums[2])
                except Exception:
                    pass

        weight_match = re.search(r'(?:Вес|Вес с упаковкой|Вес товара)[^:]*:\s*([\d\.,\s]+)\s*(г|кг)', html, re.IGNORECASE)
        if weight_match:
            try:
                val = float(weight_match.group(1).replace(',', '.').strip())
                unit = weight_match.group(2).lower()
                data['weight_g'] = int(val * 1000) if 'кг' in unit else int(val)
            except Exception:
                pass

                # 严格真实性核验：尺寸或重量缺失时绝不填 0 静默兜底
        if data['length_cm'] is None or data['width_cm'] is None or data['height_cm'] is None:
            print(f"  [WARN] SKU {sku} 未能在页面中抓取到真实包装尺寸 (Габариты)！")
            data['dimensions_verified'] = False
        else:
            data['dimensions_verified'] = True

        if data['weight_g'] is None or data['weight_g'] <= 0:
            print(f"  [WARN] SKU {sku} 未能在页面中抓取到真实毛重 (Вес)！")
            data['weight_verified'] = False
        else:
            data['weight_verified'] = True

        return data if data['title'] and len(data['photos']) > 0 else None

    def fetch_product_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """发起网络请求获取 Ozon 商品页面并解析"""
        url = f"https://www.ozon.ru/product/{sku}/"
        print(f"[*] 正在抓取 Ozon SKU: {sku} ({url})...")
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                prod = self.parse_html_content(sku, resp.text)
                if prod:
                    print(f"  [+] 成功解析: 《{prod['title'][:35]}...》 | 原价: {prod['ozon_price']}₽ | 图片: {len(prod['photos'])} 张")
                    return prod
                else:
                    print(f"  [-] SKU {sku} 页面内容未匹配到有效标题或相册，可能触发了反爬验证。")
            else:
                print(f"  [-] 请求失败: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [-] 抓取网络异常: {e}")
        return None

    fetch_product = fetch_product_by_sku

def main():
    parser = argparse.ArgumentParser(description="Ozon 商品数据极速抓取与标准结构提取器")
    parser.add_argument("--skus", "-s", type=str, default=None, help="以逗号隔开的 SKU 列表")
    parser.add_argument("--txt", "-t", type=str, default=None, help="包含 SKU 列表的 TXT 文件路径")
    parser.add_argument("--output", "-o", type=str, default="products.json", help="输出标准 JSON 文件路径")
    args = parser.parse_args()

    target_skus = []
    if args.skus:
        target_skus = [s.strip() for s in args.skus.split(",") if s.strip()]
    elif args.txt:
        if os.path.exists(args.txt):
            with open(args.txt, "r", encoding="utf-8", errors="ignore") as f:
                target_skus = re.findall(r'\b\d{7,12}\b', f.read())
        else:
            print(f"[-] 错误：TXT 文件不存在: {args.txt}")
            sys.exit(1)

    if not target_skus:
        print("[-] 错误：请通过 --skus 或 --txt 指定待抓取的 SKU！")
        sys.exit(1)

    print(f"\n==================================================================")
    print(f"启动 Ozon 爬虫解析器 (待抓取 SKU 数量: {len(target_skus)})")
    print(f"==================================================================\n")

    crawler = OzonCrawler()
    results = []
    for sku in target_skus:
        p = crawler.fetch_product_by_sku(sku)
        if p:
            results.append(p)
        time.sleep(1.0)

    if results:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n[[OK]] 抓取完成！共成功提取 {len(results)}/{len(target_skus)} 款商品数据，已保存至: {args.output}")
        print(f"[TIP] 下一步可直接运行上架引擎：")
        print(f"   python scripts/listing_engine.py --input {args.output}")
    else:
        print("\n[-] 未能成功抓取商品数据。若遇到 Ozon 反爬验证，建议使用内置无头浏览器或直接由 AI 抓取后组装输入。")

if __name__ == '__main__':
    main()
