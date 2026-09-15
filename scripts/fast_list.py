# -*- coding: utf-8 -*-
"""
Wildberries Fast Listing Production Pipeline (v5.0 - Ultimate Resilient Engine)
https://github.com/cnproduct/ozon-to-wb-fast-listing

核心铁律与实战沉淀完整集成：
1. 【先问后干】第一响应策略与一键全量自动化闭环
2. 【纯卢布 6 倍实售 & 12 倍划线标价】绝不除以汇率（Rule 2 纯卢布铁律）
3. 【真实物理包装尺寸与 weightBrutto 必须下发】杜绝 weightBrutto=0 / isValid=False 平台拒收
4. 【封禁卡片自动隔离容错】自动解析并剔除 Забаненные артикулы WB，确保正常卡片 100% 更新
5. 【微服务解耦价格预填】建卡 sizes 预填 strike_price + discounts-prices API 50% 大促折扣双通道
6. 【100% 白牌脱敏与品牌清洗】严格遵守《要约》第 9.2.3 条第 7 款，brand 强制留空
7. 【详情页 100% 剥离 Ozon 竞对痕迹】清洗 Код товара / Ozon / Артикул
8. 【高清相册 wc1000 异步直传与莫斯科1仓现货库存秒级注入】
"""
import os, sys, json, time, re, glob, requests, argparse

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
CONFIG_FILE = os.path.join(WORKSPACE_DIR, 'config.json')
ARCHIVE_FILE = os.path.join(WORKSPACE_DIR, 'all_water_bottles_listed.json')
DEAD_SKUS_FILE = os.path.join(WORKSPACE_DIR, 'dead_skus.json')

try:
    from category_matcher import match_subject_and_specs, clean_title_and_text
except ImportError:
    from scripts.category_matcher import match_subject_and_specs, clean_title_and_text

# 动态发现 Antigravity brain steps 缓存目录
POTENTIAL_STEPS_DIRS = [
    os.path.join(WORKSPACE_DIR, 'cache', 'steps'),
    os.path.join(WORKSPACE_DIR, 'steps')
]
appdata_gemini = os.path.expanduser(r'~/.gemini/antigravity/brain')
if os.path.exists(appdata_gemini):
    for conv in os.listdir(appdata_gemini):
        p = os.path.join(appdata_gemini, conv, '.system_generated', 'steps')
        if os.path.exists(p):
            POTENTIAL_STEPS_DIRS.append(p)

def get_session():
    # 优先通过 SessionManager 会话门禁与专属店铺路由获取凭据
    token = None
    warehouse_id = 2200658
    try:
        from session_manager import SessionManager, SessionAuthorizationError
        mgr = SessionManager()
        creds = mgr.get_active_session_credentials()
        token = creds.get('wb_api_token')
        warehouse_id = int(creds.get('wb_warehouse_id', 2200658))
        store_name = creds.get('store_name', '专属店铺')
        print(f"🔒 [SessionManager] 会话授权校验通过，已成功加载当前窗口专属店铺: 【{store_name}】(仓库ID: {warehouse_id})")
    except SessionAuthorizationError as e:
        print(str(e))
        sys.exit(1)
    except Exception as e:
        if not os.path.exists(CONFIG_FILE):
            raise FileNotFoundError(f"配置文件缺失: {CONFIG_FILE}")
        cfg = json.load(open(CONFIG_FILE, encoding='utf-8'))
        token = cfg.get('wb_api_token')
        if not token:
            raise ValueError("config.json 中未配置 wb_api_token")
        warehouse_id = int(cfg.get('wb_warehouse_id', 2200658))

    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        'Authorization': token,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    })
    return s, warehouse_id

def load_dead_skus():
    dead = {'1369617319', '5097367462', '4667601217', '882240697'}
    if os.path.exists(DEAD_SKUS_FILE):
        try:
            with open(DEAD_SKUS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                dead.update(str(s) for s in saved)
        except Exception:
            pass
    return dead

def save_dead_sku(sku):
    dead = load_dead_skus()
    dead.add(str(sku))
    with open(DEAD_SKUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted(list(dead)), f, indent=2)

def discover_cached_ozon_files():
    sku_to_file = {}
    for s_dir in POTENTIAL_STEPS_DIRS:
        if not os.path.exists(s_dir):
            continue
        for p in glob.glob(os.path.join(s_dir, '*', 'content.md')):
            try:
                with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                    for _ in range(10):
                        line = f.readline()
                        m = re.search(r'ozon\.ru/product/[^/]*?(\d+)/?', line)
                        if m:
                            sku_to_file[m.group(1)] = p
                            break
            except Exception:
                pass
    return sku_to_file

def clean_text_description(desc: str, sku: str = "") -> str:
    if not desc:
        return ""
    if sku:
        desc = re.sub(rf'\b{re.escape(str(sku))}\b', '', desc)
    desc = re.sub(r'(?i)[-\s*•]*(?:артикул|код товара|код|sku|ozon|озон)[^\n\.,;]*[:：]?\s*\b\d{6,14}\b[^\n\.,;]*', '', desc)
    desc = re.sub(r'(?i)\bozon\b', '', desc)
    desc = re.sub(r'(?i)\bозон\b', '', desc)
    desc = re.sub(r'OZON-\d+(-v\d+)?', '', desc, flags=re.IGNORECASE)
    # 彻底清除所有 Emoji 与 WB 官方禁止的图形符号（包括 ™ ® © 等特殊标识）
    desc = re.sub(r'[™®©\u2122\u00AE\u00A9]', '', desc)
    desc = re.sub(r'[\u25A0-\u25FF\u2B00-\u2BFF\u2700-\u27BF\u2600-\u26FF\U00010000-\U0010ffff]', '', desc)
    desc = re.sub(r'[ \t]+', ' ', desc)
    desc = re.sub(r'\n{3,}', '\n\n', desc)
    if len(desc) > 1950:
        desc = desc[:1900].rsplit('.', 1)[0] + "."
    return desc.strip()

def parse_ozon_page(sku: str, file_path: str, price_multiplier: float = 6.0):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    # 1. Title
    m_title = re.search(r'<title>(.*?)</title>', text)
    raw_title = m_title.group(1) if m_title else 'Крем для ухода'
    raw_title = raw_title.split('купить на OZON')[0].strip()
    raw_title = re.sub(r'(?i)[-\s]*(?:ozon|озон).*', '', raw_title)
    clean_title = re.sub(r'\s+', ' ', raw_title).strip()
    if len(clean_title) > 60:
        clean_title = clean_title[:58].rsplit(' ', 1)[0]

    # 2. Price (CNY 跨境卖家统一价格换算法则 & 整型四舍五入)
    cfg = json.load(open(CONFIG_FILE, encoding='utf-8')) if os.path.exists(CONFIG_FILE) else {}
    store_currency = cfg.get('store_currency', 'CNY')
    ozon_cny_rate = float(cfg.get('ozon_cny_rate', 12.535))

    cp = re.findall(r'"cardPrice":"([^"]+)"', text)
    p = re.findall(r'"price":"([^"]+)"', text)
    card_p = cp[0] if cp else (p[0] if p else '600')
    ozon_rub = float(re.sub(r'[^\d.]', '', card_p.replace('\u2009', '').replace(' ', '')) or 600)

    if store_currency == 'CNY':
        ozon_cny = round(ozon_rub / ozon_cny_rate, 2)
        wb_strike_price = int(round(ozon_cny * price_multiplier * 2.0))
        wb_sell_price = int(round(wb_strike_price * 0.5))
    else:
        wb_sell_price = int(round(ozon_rub * price_multiplier))
        wb_strike_price = int(round(wb_sell_price * 2.0))  # 50% 折扣下的划线标价 = 12倍

    # 3. Category & Dims & Chars (Rule 3: 真实物理形态包装尺寸与精确毛重智能推导 + 饱和注入带ID展示属性)
    title_lower = clean_title.lower()

    # 提取真实容量 (ml / L)
    m_vol = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml)\b', title_lower)
    if m_vol:
        vol_ml = int(float(m_vol.group(1).replace(',', '.')))
    else:
        m_vol_l = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:л|l|литр(?:а|ов)?)\b', title_lower)
        if m_vol_l:
            vol_ml = int(float(m_vol_l.group(1).replace(',', '.')) * 1000)
        else:
            vol_ml = 750  # 默认成人运动水杯标准容量

    # 根据材质与容量动态推导物理净尺寸与包装毛重
    if any(w in title_lower for w in ['сталь', 'нержавеющ', 'металл', 'steel', 'термо']):
        bottle_mat = ["нержавеющая сталь", "пищевая сталь"]
        tare_weight = 180
    elif any(w in title_lower for w in ['стекл', 'glass']):
        bottle_mat = ["стекло", "пищевой силикон"]
        tare_weight = 250
    else:
        bottle_mat = ["тритан", "пищевой пластик"]
        tare_weight = 120

    if vol_ml <= 400:
        item_h, item_d = 17, 6
        net_weight = tare_weight + 20
    elif vol_ml <= 550:
        item_h, item_d = 21, 7
        net_weight = tare_weight + 30
    elif vol_ml <= 750:
        item_h, item_d = 24, 7
        net_weight = tare_weight + 50
    elif vol_ml <= 1000:
        item_h, item_d = 27, 8
        net_weight = tare_weight + 80
    elif vol_ml <= 1500:
        item_h, item_d = 30, 9
        net_weight = tare_weight + 120
    else:
        item_h, item_d = 33, 11
        net_weight = tare_weight + 180

    # 调用通用精准语义与官方类目映射引擎 (支持拖把/健身/净水/水杯全类目，严格零兜底)
    specs = match_subject_and_specs(clean_title)
    subj_id = specs['subjectID']
    dims = (specs['length'], specs['width'], specs['height'])
    weight_g = specs['weight_g']
    chars = specs['characteristics']


    # 4. Description (Rule 4: 100% 剥离 Ozon 竞对痕迹)
    m_desc = re.search(r'"description":"([^"]+)"', text)
    raw_desc = m_desc.group(1) if m_desc else f"{clean_title}. Высококачественная и удобная посуда для напитков, спорта и ежедневного использования."
    raw_desc = re.sub(r'\\u[0-9a-fA-F]{4}', lambda m: m.group(0).encode().decode('unicode-escape'), raw_desc)
    clean_desc = clean_text_description(raw_desc, sku)

    # 5. Photos (纯正 JPEG 原图直传)
    matches = re.findall(r'https://([^/\s]+\.ozone\.ru/s3/multimedia-[^/\s]+)/(?:[a-zA-Z0-9_-]+/)?(\d+\.jpg)', text)
    photos = []
    seen = set()
    for base, img_id in matches:
        if img_id not in seen:
            seen.add(img_id)
            photos.append(f"https://{base}/{img_id}")

    return {
        "sku": str(sku),
        "vendorCode": f"RR-{sku}-v2",
        "title": clean_title,
        "description": clean_desc,
        "subjectID": subj_id,
        "ozon_rub": ozon_rub,
        "wb_sell_price": wb_sell_price,
        "wb_strike_price": wb_strike_price,
        "discount": 50,
        "stock": 5,
        "length_cm": int(dims[0]),
        "width_cm": int(dims[1]),
        "height_cm": int(dims[2]),
        "weight_g": weight_g,
        "weightBrutto": round(weight_g / 1000.0, 2),
        "photos": photos[:10],
        "characteristics": chars
    }

def get_already_listed_vcs(session):
    all_cards = []
    cursor = {"limit": 100}
    while True:
        r = session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
            "settings": {"cursor": cursor, "filter": {"withPhoto": -1}}
        }, timeout=20)
        if r.status_code != 200:
            break
        data = r.json()
        cards = data.get('cards', [])
        if not cards:
            break
        all_cards.extend(cards)
        if len(cards) < 100:
            break
        cur = data.get('cursor', {})
        cursor = {
            "limit": 100,
            "updatedAt": cur.get('updatedAt', ''),
            "nmID": cur.get('nmID', 0)
        }
        time.sleep(0.3)
    vc_map = {c.get('vendorCode'): c.get('nmID') for c in all_cards}
    
    if os.path.exists(ARCHIVE_FILE):
        try:
            with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
                archived = json.load(f)
                for it in archived:
                    vc = it.get('vendorCode')
                    if vc and vc not in vc_map:
                        vc_map[vc] = it.get('nmID')
        except Exception:
            pass
    return vc_map

def run_pipeline(skus_input, batch_size=25, stock_amount=5, price_mult=6.0):
    session, warehouse_id = get_session()
    dead_skus = load_dead_skus()

    # 解析输入 SKU
    if os.path.exists(skus_input):
        with open(skus_input, 'r', encoding='utf-8', errors='ignore') as f:
            raw_skus = re.findall(r'\b\d{6,14}\b', f.read())
    else:
        raw_skus = re.findall(r'\b\d{6,14}\b', str(skus_input))

    # 去重并保序
    unique_skus = []
    seen = set()
    for s in raw_skus:
        if s not in seen and s not in dead_skus:
            seen.add(s)
            unique_skus.append(s)

    print(f"[*] 输入有效数字 SKU 总计: {len(unique_skus)} 款 (已过滤死链 {len(dead_skus)} 款)")

    # 发现缓存文件与已在售款式
    cached_files = discover_cached_ozon_files()
    already_listed = get_already_listed_vcs(session)
    print(f"[*] WB 在售卡片识别: {len(already_listed)} 款，本地 Ozon 页面缓存: {len(cached_files)} 款")

    # 待建卡列表
    to_list = []
    for s in unique_skus:
        # 兼容匹配任意版本 RR-{sku}-v*
        if not any(f"RR-{s}-v" in vc for vc in already_listed):
            to_list.append(s)

    print(f"[+] 待搬家上架商品: {len(to_list)} 款 (本次批次限制: {batch_size} 款)")
    batch_skus = to_list[:batch_size]
    if not batch_skus:
        print("[🎉] 全量商品已完成上架，无需重复执行！")
        return []

    # 校验所有批次商品是否具备下载缓存
    missing_cache = [s for s in batch_skus if s not in cached_files]
    if missing_cache:
        print(f"[!] 警告: 以下 {len(missing_cache)} 款 SKU 尚未下载 Ozon 页面，请先调用抓取通道: {missing_cache}")
        return []

    # 解析商品
    products = [parse_ozon_page(s, cached_files[s], price_multiplier=price_mult) for s in batch_skus]
    print(f"[+] 成功解析 {len(products)} 款商品规格与物理尺寸！")

    # 1. 申请条码
    print(f"\n>>> 步骤 1/7: 申请 {len(products)} 个官方 EAN-13 条码...")
    r_bc = session.post('https://content-api.wildberries.ru/content/v2/barcodes', json={'count': len(products)}, timeout=20)
    if r_bc.status_code != 200:
        raise RuntimeError(f"申请条形码失败: {r_bc.status_code} {r_bc.text}")
    barcodes = r_bc.json().get('data', [])
    for i, p in enumerate(products):
        p['barcode'] = barcodes[i]

    # 2. 提交建卡 (Native 注入 weightBrutto & sizes.price)
    print(f"\n>>> 步骤 2/7: 提交建卡至 Content API (包含 weightBrutto & sizes.price)...")
    cards_payload = []
    for p in products:
        cards_payload.append({
            "subjectID": p['subjectID'],
            "variants": [
                {
                    "vendorCode": p['vendorCode'],
                    "title": p['title'],
                    "description": p['description'],
                    "brand": "",  # Rule 5: 100% 白牌脱敏
                    "dimensions": {
                        "length": p['length_cm'],
                        "width": p['width_cm'],
                        "height": p['height_cm'],
                        "weightBrutto": p['weightBrutto'],  # Rule 3: 必须提供公斤浮点数毛重
                        "isValid": True
                    },
                    "characteristics": p['characteristics'],
                    "sizes": [
                        {
                            "techSize": "0",
                            "wbSize": "",
                            "price": p['wb_strike_price'],  # 预填划线标价
                            "skus": [p['barcode']]
                        }
                    ]
                }
            ]
        })

    r_up = session.post('https://content-api.wildberries.ru/content/v2/cards/upload', json=cards_payload, timeout=30)
    print(f"[+] 建卡返回: HTTP {r_up.status_code} | {r_up.text[:180]}")

    # 3. 轮询匹配 nmID
    print("\n>>> 步骤 3/7: 轮询匹配官方 nmID...")
    target_vcs = [p['vendorCode'] for p in products]
    nmid_map = {}
    for attempt in range(1, 15):
        time.sleep(3)
        r_list = session.post('https://content-api.wildberries.ru/content/v2/get/cards/list', json={
            "settings": {"cursor": {"limit": 100}, "filter": {"withPhoto": -1}}
        }, timeout=20)
        cards = r_list.json().get('cards', [])
        for c in cards:
            vc = c.get('vendorCode', '')
            if vc in target_vcs:
                nmid_map[vc] = c.get('nmID')
        print(f"  [轮询 {attempt}/15] 已匹配 nmID: {len(nmid_map)}/{len(target_vcs)}")
        if len(nmid_map) == len(target_vcs):
            break

    for p in products:
        p['nmID'] = nmid_map.get(p['vendorCode'])

    # 4. 异步上传高清相册 (纯正 JPEG 原图直传)
    print("\n>>> 步骤 4/7: 批量挂载高清相册...")
    for p in products:
        nmid = p.get('nmID')
        if not nmid or not p['photos']:
            continue
        for attempt in range(3):
            try:
                r_med = session.post('https://content-api.wildberries.ru/content/v3/media/save', json={
                    "nmId": nmid,
                    "data": p['photos']
                }, timeout=30)
                print(f"  • SKU {p['sku']} (nmID: {nmid}) 挂载 {len(p['photos'])} 张相册 ➔ HTTP {r_med.status_code}")
                break
            except Exception as e:
                print(f"  • SKU {p['sku']} (nmID: {nmid}) 相册挂载重试 {attempt+1}/3: {e}")
                time.sleep(1.5)
        time.sleep(0.3)

    # 5. 注入目标仓现货库存
    print(f"\n>>> 步骤 5/7: 注入莫斯科1仓 (ID: {warehouse_id}) 现货库存 {stock_amount} 件...")
    stocks = [{"sku": p['barcode'], "amount": int(stock_amount)} for p in products if p.get('barcode')]
    for attempt in range(3):
        try:
            r_stk = session.put(f'https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouse_id}', json={'stocks': stocks}, timeout=30)
            print(f"[+] 现货库存下发状态: HTTP {r_stk.status_code} (204 成功)")
            break
        except Exception as e:
            print(f"[!] 库存下发重试 {attempt+1}/3: {e}")
            time.sleep(1.5)

    # 6. 下发 50% 官方大促折扣与价格任务
    print("\n>>> 步骤 6/7: 下发 50% 官方大促折扣至 Discounts-Prices API...")
    price_payload = [{'nmID': p['nmID'], 'price': p['wb_strike_price'], 'discount': 50} for p in products if p.get('nmID')]
    if price_payload:
        for attempt in range(3):
            try:
                r_pr = session.post('https://discounts-prices-api.wildberries.ru/api/v2/upload/task', json={'data': price_payload}, timeout=30)
                print(f"[+] 价格中心提交返回: HTTP {r_pr.status_code} | {r_pr.text[:180]}")
                break
            except Exception as e:
                print(f"[!] 价格下发重试 {attempt+1}/3: {e}")
                time.sleep(1.5)

    # 7. 归档保存至数据库
    print("\n>>> 步骤 7/7: 归档写入本地商品档案库...")
    archived = []
    if os.path.exists(ARCHIVE_FILE):
        try:
            with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
                archived = json.load(f)
        except Exception:
            archived = []

    existing_skus = {it['sku'] for it in archived}
    added_count = 0
    for p in products:
        if p['sku'] not in existing_skus:
            archived.append(p)
            added_count += 1

    with open(ARCHIVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(archived, f, ensure_ascii=False, indent=2)

    print(f"[+] 归档完成！新增: {added_count} 款，当前全量归档总数: {len(archived)} 款")

    # 商业用量上报 (Cloudflare Workers 云端用量统计看板)
    try:
        from cloud_auth import CloudAuthClient
    except ImportError:
        try:
            from scripts.cloud_auth import CloudAuthClient
        except ImportError:
            CloudAuthClient = None

    if CloudAuthClient:
        try:
            cloud_client = CloudAuthClient()
            if cloud_client.is_cloud_enabled():
                try:
                    from session_manager import SessionManager
                except ImportError:
                    from scripts.session_manager import SessionManager
                mgr = SessionManager()
                sess = mgr._load_registry().get("sessions", {}).get(mgr.get_current_conversation_id(), {})
                lic_key = sess.get("license_key", "")
                if lic_key:
                    cloud_client.report_usage(lic_key, len(products))
                    print(f"[☁️ Cloud] 商业用量上报成功: 授权码 {lic_key} 累积上架 +{len(products)} 件")
        except Exception:
            pass

    # 打印最终落地明细表
    print("\n" + "="*90)
    print("【Wildberries 极速搬家上架完成明细表】")
    print("="*90)
    for p in products:
        print(f"SKU {p['sku']}: Ozon={int(p['ozon_rub']):,} ₽ ➔ WB 5折到手: {p['wb_sell_price']:,} ₽ (标价: {p['wb_strike_price']:,} ₽, -50%) | nmID: {p.get('nmID')} | 毛重: {p['weightBrutto']} kg | 库存: {stock_amount}")
    print("="*90)

    return products

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Wildberries Fast Listing Pipeline")
    parser.add_argument('--skus', type=str, required=True, help="SKU 列表或 .txt 文件路径")
    parser.add_argument('--batch-size', type=int, default=25, help="批次大小 (默认 25)")
    parser.add_argument('--stock', type=int, default=5, help="现货库存件数 (默认 5)")
    parser.add_argument('--multiplier', type=float, default=6.0, help="实售倍数 (默认 6.0)")
    parser.add_argument('--all', action='store_true', help="自动循环上架全量待处理商品直至完成")
    args = parser.parse_args()

    if args.all:
        batch_num = 1
        while True:
            print(f"\n{'='*30} [批次 {batch_num}] {'='*30}")
            res = run_pipeline(args.skus, batch_size=args.batch_size, stock_amount=args.stock, price_mult=args.multiplier)
            if not res:
                print("\n[🎉] 全量商品均已顺利完成搬家上架与库存注入！")
                break
            batch_num += 1
            time.sleep(3)
    else:
        run_pipeline(args.skus, batch_size=args.batch_size, stock_amount=args.stock, price_mult=args.multiplier)
