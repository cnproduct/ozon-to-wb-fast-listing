# -*- coding: utf-8 -*-
"""
==============================================================================
Ozon 商品数据智能抓取与解析器 (Ozon Dual-Route Crawler & Extractor v3.5)
==============================================================================
遵循 Ozon 双路由抓取规范：
1. 主商品详情页 (PDP 主页): https://www.ozon.ru/product/{sku}/
   - 提取商品俄文主标题 (JSON-LD name / <h1> / og:title)
   - 提取主画廊 (webGallery) 全部 1000px 无水印大图 (/wc1000/)，过滤关联推荐杂图
   - 提取 Ozon 卢布当前实时售价 (offers.price / 价格正则)
   - 提取品类面包屑 (category breadcrumbs)
   - 提取品牌 (brand)，支持自动敏感词脱敏校验

2. 商品完整规格特性页 (Features 深层页): https://www.ozon.ru/product/{sku}/features/
   - 提取包装外箱长宽高: Размер упаковки (Длина x Ширина x Высота), см -> floor-rounded 整数
   - 提取包装毛重: Вес с упаковкой / Вес товара, г
   - 提取完整商品规格特性字典 (Тип, Материал, Цвет, ТН ВЭД 等)
==============================================================================
"""

import os
import re
import sys
import json
import time
import argparse
import html as html_lib
from typing import List, Dict, Any, Optional

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    from clean_descriptions import clean_and_decode_russian
except ImportError:
    try:
        from scripts.clean_descriptions import clean_and_decode_russian
    except ImportError:
        clean_and_decode_russian = lambda t, **kw: t

try:
    from morphology_engine import PhysicalMorphologyEngine
except ImportError:
    try:
        from scripts.morphology_engine import PhysicalMorphologyEngine
    except ImportError:
        PhysicalMorphologyEngine = None


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)

USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
]

def load_config() -> Dict[str, Any]:
    candidates = [
        os.path.join(WORKSPACE_DIR, 'config.json'),
        os.path.join(SCRIPT_DIR, 'config.json'),
        os.path.join(os.getcwd(), 'config.json')
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

class OzonCrawler:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.config = load_config()
        self.proxy = self.config.get("ozon_proxy") or os.getenv("OZON_PROXY")
        
        self.headers = {
            'User-Agent': USER_AGENTS[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Sec-Ch-Ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Upgrade-Insecure-Requests': '1'
        }

    def _get_page_html(self, url: str) -> Optional[str]:
        """通过支持浏览器指纹模拟的客户端发起请求"""
        proxies = {'http': self.proxy, 'https': self.proxy} if self.proxy else None
        
        # 优先使用 curl_cffi 模拟真实 Chrome TLS 握手特征
        if HAS_CURL_CFFI:
            try:
                s = curl_requests.Session(impersonate="chrome124")
                resp = s.get(url, headers=self.headers, proxies=proxies, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 307 and resp.headers.get("Location"):
                    redirect_url = resp.headers["Location"]
                    if not redirect_url.startswith("http"):
                        redirect_url = "https://www.ozon.ru" + redirect_url
                    r2 = s.get(redirect_url, headers=self.headers, proxies=proxies, timeout=self.timeout)
                    if r2.status_code == 200:
                        return r2.text
            except Exception:
                pass

        # 降级使用标准 requests
        try:
            import requests as standard_requests
            s = standard_requests.Session()
            s.headers.update(self.headers)
            resp = s.get(url, proxies=proxies, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass

        return None

    def parse_pdp_html(self, sku: str, html: str) -> Dict[str, Any]:
        """
        [路由 1] 解析主商品详情页 (PDP 主页: https://www.ozon.ru/product/{sku}/)
        提取核心数据：标题、原厂高清大图画廊 (webGallery)、实时售价、品类面包屑、品牌
        """
        data = {
            "sku": str(sku),
            "vendorCode": f"OZON-{sku}-v1",
            "title": "",
            "ozon_price": 0.0,
            "ozon_green_price": 0.0,
            "ozon_regular_price": 0.0,
            "brand": "",
            "photos": [],
            "description_clean": "",
            "category_path": "",
            "product_type": ""
        }

        # 1. 提取 JSON-LD 结构化数据 (兼容 <script nonce="..." type="application/ld+json">)
        json_ld_matches = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
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
                    if ld.get('brand'):
                        b = ld.get('brand')
                        data['brand'] = b.get('name', '').strip() if isinstance(b, dict) else str(b).strip()
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
                                data['ozon_regular_price'] = float(offers['price'])
                            except Exception:
                                pass
            except Exception:
                pass

        # 1.1 核心铁律：优先提取 Ozon 绿标卡价 (cardPrice / Ozon Карта 专属特惠价)
        # 无论在 webPrice JSON 还是 HTML 属性中，cardPrice 即为买家持卡实付的绿标底价
        cp_match = re.search(r'"cardPrice"\s*:\s*"([^"]+)"', html)
        if cp_match:
            val_str = cp_match.group(1).replace('\u2009', '').replace('\xa0', '').replace(' ', '').replace('₽', '').strip()
            try:
                data['ozon_green_price'] = float(val_str)
            except Exception:
                pass

        # 1.2 提取常规标价 (price)
        p_match = re.search(r'"price"\s*:\s*"([^"]+)"', html)
        if p_match:
            val_str = p_match.group(1).replace('\u2009', '').replace('\xa0', '').replace(' ', '').replace('₽', '').strip()
            try:
                data['ozon_regular_price'] = float(val_str)
            except Exception:
                pass

        # 2. 标题备选匹配 (h1 / og:title / title tag)
        if not data['title']:
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if h1_match:
                clean_title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
                if clean_title and len(clean_title) > 3:
                    data['title'] = clean_title

        if not data['title']:
            og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html)
            if og_title:
                clean_t = og_title.group(1).replace(' - купить на OZON', '').strip()
                if clean_t:
                    data['title'] = clean_t

        if not data['title']:
            t_match = re.search(r'<title>(.*?)</title>', html)
            if t_match:
                clean_t = re.sub(r'\s*купить на OZON.*$', '', t_match.group(1)).strip()
                if clean_t:
                    data['title'] = clean_t

        # 3. 提取品类面包屑导航 (Breadcrumbs)
        bc_matches = re.findall(r'''<a[^>]+href=["']/category/[^"']+["'][^>]*>(.*?)</a>''', html)
        if bc_matches:
            clean_bcs = [re.sub(r'<[^>]+>', '', b).strip() for b in bc_matches if re.sub(r'<[^>]+>', '', b).strip()]
            if clean_bcs:
                data['category_path'] = ' > '.join(clean_bcs[:4])

        # 4. 提取原厂高清大图画廊 (webGallery 容器，强制升级至 /wc1000/ 无水印大图)
        gallery_scope = html
        gallery_match = re.search(r'data-widget=["\']webGallery["\'][^>]*>(.*?)</div>\s*<div[^>]+data-widget=', html, re.DOTALL)
        if gallery_match:
            gallery_scope = gallery_match.group(1)
        elif 'data-widget="webGallery"' in html:
            start_idx = html.find('data-widget="webGallery"')
            gallery_scope = html[start_idx:start_idx+25000]

        photo_urls = re.findall(r'https://[^"\'\s<>]+/(?:s3/)?multimedia[^"\'\s<>]+\.(?:jpg|jpeg|png|webp)', gallery_scope)
        for u in photo_urls:
            if '/wc50/' in u or '/wc100/' in u:
                continue
            u_hd = re.sub(r'/[c|wc]\d+/', '/wc1000/', u)
            if u_hd not in data['photos']:
                data['photos'].append(u_hd)

        # 4.1 全文图片兜底抽取 (若 webGallery 容器未包含多图)
        if len(data['photos']) < 3:
            all_raw_urls = re.findall(r'https://ir[^\s\"\'<>]+/multimedia[^\s\"\'<>]+\.(?:jpg|jpeg|png|webp)', html)
            for u in all_raw_urls:
                u_hd = re.sub(r'/[c|wc]\d+/', '/wc1000/', u)
                if u_hd not in data['photos']:
                    data['photos'].append(u_hd)

        # 5. 绿标价 HTML 容器与兜底决策
        if data['ozon_green_price'] <= 0:
            wp_match = re.search(r'data-widget=["\']webPrice["\'][^>]*>(.*?)</div>\s*<div[^>]+data-widget=', html, re.DOTALL)
            if wp_match:
                wp_html = wp_match.group(1)
                h_match = re.search(r'class="tsHeadline[^"]*">([\d\s\u2009\xa0]+)\s*₽', wp_html)
                if h_match:
                    try:
                        data['ozon_green_price'] = float(h_match.group(1).replace('\u2009', '').replace('\xa0', '').replace(' ', ''))
                    except Exception:
                        pass

        # 核心铁律：必须且永远以 Ozon 绿标卡价为最终基准价！
        if data['ozon_green_price'] > 0:
            data['ozon_price'] = data['ozon_green_price']
        elif data['ozon_regular_price'] > 0:
            data['ozon_price'] = data['ozon_regular_price']
        else:
            price_match = re.search(r'(\d[\d\s]*)\s*₽', html)
            if price_match:
                try:
                    data['ozon_price'] = float(price_match.group(1).replace(' ', '').replace('\xa0', ''))
                    data['ozon_regular_price'] = data['ozon_price']
                except Exception:
                    pass

        # 6. 描述权威清洗与 Ozon 编码彻底剥离
        if data['description_clean']:
            data['description_clean'] = clean_and_decode_russian(
                data['description_clean'],
                extra_brands=[data.get('brand')] if data.get('brand') else None
            )

        return data

    def parse_features_html(self, html: str) -> Dict[str, Any]:
        """
        [路由 2] 解析商品完整规格特性页 (Features 深层页: https://www.ozon.ru/product/{sku}/features/)
        提取核心数据：包装外箱长宽高 (cm)、毛重 (g)、海关编码 (ТН ВЭД)、特性参数表
        """
        res = {
            "length_cm": None,
            "width_cm": None,
            "height_cm": None,
            "weight_g": None,
            "tnved": "",
            "raw_props": {}
        }

        # 1. 提取 data-state 中包含的完整 characteristics 结构树
        states = re.findall(r'data-state=([\"\'])(.*?)\1', html, re.DOTALL)
        for quote, val in states:
            if 'characteristics' in val or 'Weight_0' in val or 'Вес' in val:
                try:
                    data = json.loads(html_lib.unescape(val))
                    if 'characteristics' in data:
                        for grp in data.get('characteristics', []):
                            for item in grp.get('short', []) + grp.get('long', []):
                                name = item.get('name', '').strip()
                                vals = [v.get('text', '').strip() for v in item.get('values', []) if v.get('text')]
                                if name and vals:
                                    res['raw_props'][name] = ', '.join(vals)
                except Exception:
                    pass

        props = res['raw_props']

        # 2. 从属性键值对精准匹配包装规格与毛重
        for k, v in props.items():
            k_lower = k.lower()
            if 'размер упаковки' in k_lower or 'габариты' in k_lower:
                nums = re.findall(r'\d+(?:\.\d+)?', v.replace(',', '.'))
                if len(nums) >= 3:
                    try:
                        res['length_cm'] = float(nums[0])
                        res['width_cm'] = float(nums[1])
                        res['height_cm'] = float(nums[2])
                    except Exception:
                        pass
            elif 'вес' in k_lower:
                nums = re.findall(r'\d+(?:\.\d+)?', v.replace(',', '.'))
                if nums:
                    try:
                        val = float(nums[0])
                        res['weight_g'] = int(val * 1000) if 'кг' in v.lower() else int(val)
                    except Exception:
                        pass
            elif 'тн вэд' in k_lower or 'тнвэд' in k_lower:
                res['tnved'] = v.strip()

        # 3. 尺寸单独字段兜底 (Высота, см / Ширина, см / Глубина, см)
        if res['length_cm'] is None:
            h = props.get('Высота, см') or props.get('Высота')
            w = props.get('Ширина, см') or props.get('Ширина')
            d = props.get('Глубина, см') or props.get('Длина, см') or props.get('Толщина, см') or '15'
            if h and w:
                try:
                    res['height_cm'] = float(re.findall(r'\d+(?:\.\d+)?', h.replace(',', '.'))[0])
                    res['width_cm'] = float(re.findall(r'\d+(?:\.\d+)?', w.replace(',', '.'))[0])
                    res['length_cm'] = float(re.findall(r'\d+(?:\.\d+)?', d.replace(',', '.'))[0]) if d else 15.0
                except Exception:
                    pass

        # 4. 全文正则兜底提取包装长宽高与毛重 (应对未渲染为 JSON 的 HTML 片段)
        if res['length_cm'] is None:
            dim_match = re.search(r'(?:Размер упаковки|Габариты)[^:]*:\s*([\d\.,\s/xх*]+)\s*см', html, re.IGNORECASE)
            if dim_match:
                nums = re.findall(r'\d+(?:\.\d+)?', dim_match.group(1).replace(',', '.'))
                if len(nums) >= 3:
                    try:
                        res['length_cm'] = float(nums[0])
                        res['width_cm'] = float(nums[1])
                        res['height_cm'] = float(nums[2])
                    except Exception:
                        pass

        if res['weight_g'] is None:
            weight_match = re.search(r'(?:Вес|Вес с упаковкой|Вес товара)[^:]*:\s*([\d\.,\s]+)\s*(г|кг)', html, re.IGNORECASE)
            if weight_match:
                try:
                    val = float(weight_match.group(1).replace(',', '.').strip())
                    unit = weight_match.group(2).lower()
                    res['weight_g'] = int(val * 1000) if 'кг' in unit else int(val)
                except Exception:
                    pass

        # 5. 基于容量 (Объем, мл) 或特性推导实际包装长宽高 (避免全店千篇一律假模板数值)
        if res['length_cm'] is None:
            vol_str = props.get('Объем, мл') or props.get('Объем') or props.get('Объём, мл') or props.get('Объём') or ''
            if not vol_str:
                m_v = re.search(r'(\d+)\s*(?:мл|ml)\b', html, re.IGNORECASE)
                if m_v:
                    vol_str = m_v.group(1)
            vol_nums = re.findall(r'\d+', str(vol_str))
            if vol_nums:
                v_ml = int(vol_nums[0])
                if v_ml <= 5:
                    res['length_cm'], res['width_cm'], res['height_cm'] = 12.0, 3.0, 2.0
                    res['weight_g'] = res['weight_g'] or 40
                elif v_ml <= 15:
                    res['length_cm'], res['width_cm'], res['height_cm'] = 13.0, 4.0, 3.0
                    res['weight_g'] = res['weight_g'] or 60
                elif v_ml <= 30:
                    res['length_cm'], res['width_cm'], res['height_cm'] = 11.0, 4.0, 4.0
                    res['weight_g'] = res['weight_g'] or 100
                elif v_ml <= 50:
                    res['length_cm'], res['width_cm'], res['height_cm'] = 8.0, 8.0, 6.0
                    res['weight_g'] = res['weight_g'] or 160
                elif v_ml <= 100:
                    res['length_cm'], res['width_cm'], res['height_cm'] = 16.0, 5.0, 4.0
                    res['weight_g'] = res['weight_g'] or 150
                elif v_ml <= 150:
                    res['length_cm'], res['width_cm'], res['height_cm'] = 17.0, 5.0, 5.0
                    res['weight_g'] = res['weight_g'] or 210
                elif v_ml <= 250:
                    res['length_cm'], res['width_cm'], res['height_cm'] = 19.0, 6.0, 6.0
                    res['weight_g'] = res['weight_g'] or 320
                elif v_ml <= 500:
                    res['length_cm'], res['width_cm'], res['height_cm'] = 22.0, 8.0, 7.0
                    res['weight_g'] = res['weight_g'] or 560

        return res

    def fetch_product_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        完整执行 Ozon 双路由抓取并合并输出标准化商品结构
        """
        sku_str = str(sku).strip()

        # 1. 优先检索本地 products.json 缓存档案 (极速命中，零网络依赖)
        json_path = os.path.join(WORKSPACE_DIR, 'products.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    cached_items = json.load(f)
                    for item in cached_items:
                        if str(item.get('sku')) == sku_str and item.get('title') and item.get('photos'):
                            print(f"[+] SKU [{sku_str}] 秒级命中本地 products.json 知识库档案: 《{item.get('title')[:30]}...》")
                            return dict(item)
            except Exception:
                pass

        # 2. 发起双路由网络抓取
        pdp_url = f"https://www.ozon.ru/product/{sku_str}/"
        features_url = f"https://www.ozon.ru/product/{sku_str}/features/"

        print(f"[*] [路由 1] 正在请求 Ozon PDP 主页: {pdp_url}")
        pdp_html = self._get_page_html(pdp_url)
        
        if not pdp_html or len(pdp_html) < 2000 or 'Похоже, нет соединения' in pdp_html:
            print(f"[-] SKU [{sku_str}] PDP 请求受阻 (触发 Ozon 反爬或无网络响应)")
            return None

        product_data = self.parse_pdp_html(sku_str, pdp_html)
        if not product_data.get('title') or not product_data.get('photos'):
            print(f"[-] SKU [{sku_str}] PDP 未能提取到有效标题或相册")
            return None

        print(f"  [+] PDP 提取成功: 《{product_data['title'][:35]}...》 | Ozon绿标价: {product_data['ozon_price']}₽ (常规标价: {product_data.get('ozon_regular_price', 0)}₽) | 图片: {len(product_data['photos'])} 张")

        # 请求规格特性页 (Features)
        print(f"[*] [路由 2] 正在请求 Ozon Features 规格页: {features_url}")
        feat_html = self._get_page_html(features_url)
        if feat_html and len(feat_html) > 1000 and 'Похоже, нет соединения' not in feat_html:
            features_data = self.parse_features_html(feat_html)
            if features_data.get('length_cm'):
                product_data['length_cm'] = int(features_data['length_cm'])
                product_data['width_cm'] = int(features_data['width_cm'])
                product_data['height_cm'] = int(features_data['height_cm'])
            if features_data.get('weight_g'):
                product_data['weight_g'] = int(features_data['weight_g'])
            if features_data.get('tnved'):
                product_data['tnved'] = features_data['tnved']
            product_data['characteristics'] = features_data.get('raw_props', {})
            print(f"  [+] Features 提取成功: 规格 {product_data.get('length_cm')}x{product_data.get('width_cm')}x{product_data.get('height_cm')} cm | 毛重 {product_data.get('weight_g')}g")

        # 真实物理形态包装尺寸与毛重推导 (严格遵循 Rule 4 物理形态推导铁律)
        if not product_data.get('length_cm') or not product_data.get('weight_g'):
            if PhysicalMorphologyEngine:
                m_res = PhysicalMorphologyEngine.deduce_dimensions_and_weight(
                    title=product_data.get('title', ''),
                    raw_props=product_data.get('characteristics', {}),
                    html_content=pdp_html or "",
                    sku=sku_str
                )
                product_data['length_cm'] = m_res['length_cm']
                product_data['width_cm'] = m_res['width_cm']
                product_data['height_cm'] = m_res['height_cm']
                product_data['weight_g'] = m_res['weight_g']
                product_data['weightBrutto'] = m_res['weightBrutto']
            else:
                product_data['length_cm'] = 16
                product_data['width_cm'] = 6
                product_data['height_cm'] = 5
                product_data['weight_g'] = 55
                product_data['weightBrutto'] = 0.06

        # 回写更新本地 products.json 档案
        try:
            all_cached = []
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    all_cached = json.load(f)
            updated = False
            for idx, c in enumerate(all_cached):
                if str(c.get('sku')) == sku_str:
                    all_cached[idx] = product_data
                    updated = True
                    break
            if not updated:
                all_cached.append(product_data)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(all_cached, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return product_data

    fetch_product = fetch_product_by_sku

def main():
    parser = argparse.ArgumentParser(description="Ozon 双路由商品数据智能抓取器")
    parser.add_argument("--skus", "-s", type=str, default=None, help="以逗号隔开的 SKU 列表")
    parser.add_argument("--output", "-o", type=str, default="products.json", help="输出标准 JSON 文件路径")
    args = parser.parse_args()

    if not args.skus:
        print("[-] 错误：请通过 --skus 指定待抓取的 SKU！")
        sys.exit(1)

    crawler = OzonCrawler()
    target_skus = [s.strip() for s in args.skus.split(",") if s.strip()]
    results = []
    for sku in target_skus:
        p = crawler.fetch_product_by_sku(sku)
        if p:
            results.append(p)

    if results:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] 抓取完成！共提取 {len(results)} 款商品数据已保存至: {args.output}")

if __name__ == '__main__':
    main()
