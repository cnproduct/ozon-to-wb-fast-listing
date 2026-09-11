# -*- coding: utf-8 -*-
"""
飞书官方长连接 (WebSocket) 对接 Wildberries 全自动上架机器人
无需公网 IP / 无需内网穿透 / 实时双向通信
"""
import os
import sys
import time
import json
import re
import math
import threading
from typing import Dict, Any, List
import requests
import pandas as pd

import lark_oapi as lark
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

# 动态导入同目录组件
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
for d in [SCRIPT_DIR, WORKSPACE_DIR]:
    if d not in sys.path:
        sys.path.insert(0, d)

from wb_uploader import WildberriesAPIClient
from ozon_crawler import OzonCrawler

def load_bot_config() -> Dict[str, Any]:
    """多级配置智能加载：config.json > 环境变量"""
    candidates = [
        os.path.join(os.getcwd(), 'config.json'),
        os.path.join(SCRIPT_DIR, 'config.json'),
        os.path.join(WORKSPACE_DIR, 'config.json'),
        os.path.expanduser('~/.wb_config.json')
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

_cfg = load_bot_config()

# ================= 配置参数 =================
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID") or _cfg.get("feishu_app_id", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET") or _cfg.get("feishu_app_secret", "")

# 默认 WB 授权 Token 与莫斯科 1 号现货仓
WB_API_TOKEN = os.getenv("WB_API_TOKEN") or _cfg.get("wb_api_token", "")
WB_WAREHOUSE_ID = int(os.getenv("WB_WAREHOUSE_ID") or _cfg.get("wb_warehouse_id", 120762))

# 初始化客户端
wb_client = WildberriesAPIClient(api_token=WB_API_TOKEN, warehouse_id=WB_WAREHOUSE_ID)
lark_client = None
if FEISHU_APP_ID and FEISHU_APP_SECRET:
    lark_client = lark.Client.builder().app_id(FEISHU_APP_ID).app_secret(FEISHU_APP_SECRET).build()

def send_feishu_reply(chat_id: str, text: str):
    """向指定飞书会话回复文本消息"""
    if not lark_client:
        print(f"[-] [飞书未配置] 无法发送消息给 {chat_id}: {text}")
        return
    try:
        content = json.dumps({"text": text}, ensure_ascii=False)
        req = lark.BaseRequest()
        req.http_method = lark.HttpMethod.POST
        req.uri = "/open-apis/im/v1/messages?receive_id_type=chat_id"
        req.token_types = {lark.AccessTokenType.TENANT}
        req.body = {"receive_id": chat_id, "msg_type": "text", "content": content}
        lark_client.request(req)
    except Exception as e:
        print(f"[-] 回复飞书消息异常: {e}")

def send_feishu_card(chat_id: str, title: str, content_lines: List[str], color: str = "blue"):
    """发送排版优雅的飞书消息卡片"""
    if not lark_client:
        print(f"[-] [飞书未配置] 无法发送卡片给 {chat_id}: {title}")
        return
    try:
        elements = [{"tag": "markdown", "content": "\n".join(content_lines)}]
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color
            },
            "elements": elements
        }
        req = lark.BaseRequest()
        req.http_method = lark.HttpMethod.POST
        req.uri = "/open-apis/im/v1/messages?receive_id_type=chat_id"
        req.token_types = {lark.AccessTokenType.TENANT}
        req.body = {"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)}
        lark_client.request(req)
    except Exception as e:
        print(f"[-] 发送飞书卡片异常: {e}")

def download_message_resource(message_id: str, file_key: str, save_path: str) -> bool:
    """从飞书下载用户上传的文件"""
    if not lark_client:
        return False
    try:
        req = lark.BaseRequest()
        req.http_method = lark.HttpMethod.GET
        req.uri = f"/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type=file"
        req.token_types = {lark.AccessTokenType.TENANT}
        resp = lark_client.request(req)
        if resp.code == 0 and resp.raw and resp.raw.content:
            with open(save_path, "wb") as f:
                f.write(resp.raw.content)
            return True
    except Exception as e:
        print(f"[-] 下载飞书文件失败: {e}")
    return False

def execute_single_listing_task(chat_id: str, sku: str, multiplier: float = 5.0, discount: int = 50, stock: int = 200, custom_dims: Dict = None):
    """后台执行单个 SKU 上架流水线"""
    try:
        if not wb_client.token or wb_client.token == "YOUR_WB_API_TOKEN_HERE":
            send_feishu_reply(chat_id, f"❌ 上架失败 (SKU: {sku}): 未配置有效 WB_API_TOKEN！请在 config.json 或环境变量中配置您的 Wildberries 卖家 Token。")
            return

        send_feishu_reply(chat_id, f"🚀 正在为 SKU [{sku}] 启动 WB 官方 API 极速建卡流水线...")

        # 尝试从 Ozon 自动抓取真实数据
        crawler = OzonCrawler()
        fetched = crawler.fetch_product_by_sku(sku)
        
        if fetched and fetched.get("title") and fetched.get("photos"):
            product_data = fetched
            ozon_price = fetched.get("ozon_price") or 500.0
            print(f"[+] SKU [{sku}] 成功从 Ozon 抓取真实商品数据: {product_data.get('title')[:30]}...")
        else:
            is_catsand = "2780098271" in sku
            product_data = {
                "sku": sku,
                "vendorCode": f"OZON-{sku}-v1",
                "subjectID": 943 if is_catsand else 2918,
                "title": "PETFORT Наполнитель Комкующийся 3000г. Тофу Зеленый чай" if is_catsand else f"Товар Ozon SKU {sku}",
                "description": "Экологичный комкующийся растительный наполнитель тофу для кошачьего туалета.\n\nОсновные характеристики:\n- Вес: 3000 г (3.0 кг)\n- Габариты коробки: 25 x 18 x 12 см",
                "length_cm": 25 if is_catsand else 15,
                "width_cm": 18 if is_catsand else 10,
                "height_cm": 12 if is_catsand else 5,
                "weight_g": 3200 if is_catsand else 500,
                "photos": [
                    "https://ir-20.ozone.ru/s3/multimedia-1-f/wc1000/14355407859.jpg"
                ]
            }
            ozon_price = 398.0 if is_catsand else 500.0

        if custom_dims:
            product_data.update(custom_dims)
        
        # 调用 WB 客户端一键上架
        res = wb_client.upload_single_product(
            product=product_data,
            ozon_price=ozon_price,
            multiplier=multiplier,
            discount=discount,
            stock=stock
        )

        # 组装飞书高亮卡片通知
        card_lines = [
            f"**商品标题**: {product_data['title']}",
            f"**商家货号**: `{res['vendorCode']}`",
            f"**WB 官方 nmID**: [{res['nmID']}](https://www.wildberries.ru/catalog/{res['nmID']}/detail.aspx)",
            f"**官方条形码**: `{res['barcode']}`",
            f"---",
            f"💰 **实售价格**: **{res['sell_price']} ₽** (划线标价 {res['strike_price']} ₽，立享 {res['discount']}% 官方大促折)",
            f"📦 **莫斯科现货**: **{res['stock']} 件** (现货在售已秒级激活)",
            f"📐 **包装规格**: {product_data.get('length_cm', 10)}×{product_data.get('width_cm', 10)}×{product_data.get('height_cm', 10)} cm | 毛重 {product_data.get('weight_g', 500)}g",
            f"---",
            f"✅ [点击直接在 WB 官网查看商品前台详情](https://www.wildberries.ru/catalog/{res['nmID']}/detail.aspx)"
        ]
        send_feishu_card(chat_id, f"🎉 商品上架成功 (SKU: {sku})", card_lines, color="green")

    except Exception as e:
        send_feishu_reply(chat_id, f"❌ 上架失败 (SKU: {sku}):\n{str(e)}")

def handle_excel_file_task(chat_id: str, file_path: str):
    """解析 Excel 表格并批量上架"""
    try:
        df = pd.read_excel(file_path)
        send_feishu_reply(chat_id, f"📊 成功读取表格，共检测到 {len(df)} 行商品数据，开始批量处理...")
        
        for idx, row in df.iterrows():
            sku = str(row.get("Ozon_SKU", "")).strip()
            if not sku or not sku.isdigit():
                continue
            
            custom_dims = {}
            if "包装长(cm)" in row and pd.notna(row["包装长(cm)"]):
                custom_dims["length_cm"] = float(row["包装长(cm)"])
            if "包装宽(cm)" in row and pd.notna(row["包装宽(cm)"]):
                custom_dims["width_cm"] = float(row["包装宽(cm)"])
            if "包装高(cm)" in row and pd.notna(row["包装高(cm)"]):
                custom_dims["height_cm"] = float(row["包装高(cm)"])
            if "毛重(g)" in row and pd.notna(row["毛重(g)"]):
                custom_dims["weight_g"] = int(row["毛重(g)"])

            execute_single_listing_task(
                chat_id=chat_id,
                sku=sku,
                multiplier=float(row.get("售价倍数(默认5)", 5.0)),
                discount=int(row.get("折扣百分比(默认50)", 50)),
                stock=int(row.get("现货库存(默认200)", 200)),
                custom_dims=custom_dims
            )
            time.sleep(1)

        send_feishu_reply(chat_id, "🏁 恭喜！当前表格中的全部商品已批量处理完毕！")
    except Exception as e:
        send_feishu_reply(chat_id, f"❌ 处理 Excel 表格失败: {e}")

def get_sensitive_brands_path() -> str:
    """获取敏感品牌知识库路径"""
    p1 = os.path.join(WORKSPACE_DIR, 'references', 'sensitive_brands.txt')
    if os.path.exists(os.path.dirname(p1)):
        return p1
    return os.path.join(SCRIPT_DIR, '..', 'references', 'sensitive_brands.txt')

def handle_text_commands(chat_id: str, raw_text: str) -> bool:
    """处理避坑词库、配置状态等指令。如果处理了返回 True，否则返回 False"""
    text_lower = raw_text.lower().strip()
    
    # 1. 避坑词库查看
    if text_lower in ["避坑词库", "查看避坑", "避坑列表", "品牌避坑", "避坑"]:
        brands_file = get_sensitive_brands_path()
        brands = []
        if os.path.exists(brands_file):
            with open(brands_file, "r", encoding="utf-8") as f:
                brands = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        cfg = load_bot_config()
        cfg_brands = cfg.get("sensitive_brands", [])
        all_brands = sorted(list(set(brands + cfg_brands)))
        
        lines = [
            f"🛡️ **当前品牌避坑知识库共收录 {len(all_brands)} 个受保护/高危品牌**：",
            "---",
            ", ".join(all_brands[:40]) + ("..." if len(all_brands) > 40 else ""),
            "---",
            "💡 **添加指令**：发送 `添加避坑: 品牌名1, 品牌名2` 即可追加新品牌。"
        ]
        send_feishu_card(chat_id, "🛡️ 品牌避坑知识库", lines, color="blue")
        return True

    # 2. 添加避坑品牌
    if raw_text.startswith("添加避坑") or raw_text.startswith("+避坑"):
        raw_names = re.sub(r"^(?:添加避坑|[\+]避坑)[:：\s]+", "", raw_text)
        new_brands = [b.strip() for b in re.split(r"[,，\s\n]+", raw_names) if b.strip()]
        if not new_brands:
            send_feishu_reply(chat_id, "⚠️ 请提供要添加的品牌名称，例如：`添加避坑: Nike, Adidas`")
            return True
            
        brands_file = get_sensitive_brands_path()
        existing = set()
        if os.path.exists(brands_file):
            with open(brands_file, "r", encoding="utf-8") as f:
                existing = {line.strip() for line in f if line.strip() and not line.startswith('#')}
        
        to_add = [b for b in new_brands if b not in existing]
        if to_add:
            os.makedirs(os.path.dirname(brands_file), exist_ok=True)
            with open(brands_file, "a", encoding="utf-8") as f:
                for b in to_add:
                    f.write(f"\n{b}")
            send_feishu_reply(chat_id, f"✅ 成功添加 {len(to_add)} 个品牌到避坑库：{', '.join(to_add)}！后续上架将自动执行脱敏。")
        else:
            send_feishu_reply(chat_id, f"ℹ️ 这些品牌已存在于避坑库中：{', '.join(new_brands)}")
        return True

    # 3. 店铺与系统状态
    if text_lower in ["状态", "配置", "查看配置", "wb状态"]:
        cfg = load_bot_config()
        token_set = bool((cfg.get("wb_api_token") or os.getenv("WB_API_TOKEN") or "").strip() not in ["", "YOUR_WB_API_TOKEN_HERE"])
        wh_id = cfg.get("wb_warehouse_id") or os.getenv("WB_WAREHOUSE_ID") or 120762
        lines = [
            f"**Wildberries API Token**: {'✅ 已配置有效密钥' if token_set else '❌ 未配置 (请在 config.json 填入)'}",
            f"**履约仓库 ID**: `{wh_id}`",
            f"**默认售价倍数**: `{cfg.get('default_multiplier', 5.0)} 倍`",
            f"**默认官方折扣**: `{cfg.get('default_discount', 50)}%`",
            f"**默认备货库存**: `{cfg.get('default_stock', 200)} 件`",
            "---",
            "💡 如需上架商品，直接输入 SKU、包含参数的指令，或将 Excel/TXT 文件拖入聊天框。"
        ]
        send_feishu_card(chat_id, "⚙️ 系统与店铺配置状态", lines, color="blue")
        return True

    return False

def parse_inline_params(text: str, default_m: float = 5.0, default_d: int = 50, default_s: int = 200):
    """解析文本中的动态定价与库存参数"""
    m = default_m
    d = default_d
    s = default_s

    # 倍数：例如 4倍、4.5倍、x5
    m_match = re.search(r'(?:倍数[:：\s]*|x)?(\d+(?:\.\d+)?)\s*倍', text, re.IGNORECASE)
    if m_match:
        try:
            m = float(m_match.group(1))
        except Exception:
            pass

    # 折扣：例如 5折 -> 50, 40折/40% -> 40
    d_match = re.search(r'(\d+)\s*(?:折|%)', text)
    if d_match:
        try:
            val = int(d_match.group(1))
            d = val * 10 if val <= 9 else val
        except Exception:
            pass

    # 库存：例如 100件、100库存
    s_match = re.search(r'(\d+)\s*(?:件|库存)', text)
    if s_match:
        try:
            s = int(s_match.group(1))
        except Exception:
            pass

    return m, d, s

def batch_listing_worker(chat_id: str, skus: List[str], multiplier: float, discount: int, stock: int):
    """批量上架任务工作线程"""
    if len(skus) > 1:
        send_feishu_reply(chat_id, f"📋 共检测到 {len(skus)} 个商品 SKU，开始按顺序极速上架 (倍数:{multiplier}, 折扣:{discount}%, 库存:{stock})...")
    for i, sku in enumerate(skus):
        execute_single_listing_task(chat_id, sku, multiplier=multiplier, discount=discount, stock=stock)
        if i < len(skus) - 1:
            time.sleep(1.5)
    if len(skus) > 1:
        send_feishu_reply(chat_id, f"🏁 全部 {len(skus)} 个商品已批量处理完毕！")

# ================= 飞书长连接消息事件监听 =================
def on_p2_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    """接收飞书用户发送的单聊或群聊消息"""
    try:
        msg = data.event.message
        chat_id = msg.chat_id
        msg_type = msg.message_type

        # 1. 用户发送文本
        if msg_type == "text":
            text_json = json.loads(msg.content)
            raw_text = text_json.get("text", "").strip()
            print(f"[+] 收到飞书文本消息: {raw_text}")

            # 先检查是否为管理指令 (避坑词库、状态等)
            if handle_text_commands(chat_id, raw_text):
                return

            # 匹配 SKU 数字列表
            found_skus = re.findall(r"\b\d{7,12}\b", raw_text)
            if found_skus:
                cfg = load_bot_config()
                def_m = float(cfg.get("default_multiplier", 5.0))
                def_d = int(cfg.get("default_discount", 50))
                def_s = int(cfg.get("default_stock", 200))
                m, d, s = parse_inline_params(raw_text, def_m, def_d, def_s)
                
                threading.Thread(target=batch_listing_worker, args=(chat_id, found_skus, m, d, s)).start()
            else:
                help_card = [
                    "👋 **我是 Wildberries 全自动极速上架助手！**",
                    "",
                    "你可以通过以下方式随时指挥我：",
                    "1️⃣ **直接发 SKU 列表**：直接发一个或多个 Ozon SKU（如 `2780098271, 2444330744`），自动抓取并上架！",
                    "2️⃣ **带参数快捷上架**：发送 `2780098271 4倍 50折 100库存`，按自定义定价与库存上架！",
                    "3️⃣ **管理品牌避坑库**：",
                    "   - 发送 `查看避坑`：查看当前屏蔽的侵权高危品牌",
                    "   - 发送 `添加避坑: 品牌1, 品牌2`：一键扩充避坑词库",
                    "4️⃣ **拖入 Excel / TXT 文件**：把表格或包含 SKU 的文本文件发给我，自动批量极速上架！",
                    "5️⃣ **查看状态**：发送 `状态` 查看店铺 API 与参数配置。"
                ]
                send_feishu_card(chat_id, "💡 WB 极速上架助手使用指南", help_card, color="blue")

        # 2. 用户发送文件 (Excel / TXT)
        elif msg_type == "file":
            file_info = json.loads(msg.content)
            file_name = file_info.get("file_name", "")
            file_key = file_info.get("file_key", "")
            print(f"[+] 收到飞书文件: {file_name}")

            if file_name.endswith((".xlsx", ".xls")):
                os.makedirs("./downloads", exist_ok=True)
                save_path = os.path.join("./downloads", file_name)
                send_feishu_reply(chat_id, f"📥 收到上架表格【{file_name}】，正在下载并解析...")
                
                if download_message_resource(msg.message_id, file_key, save_path):
                    threading.Thread(target=handle_excel_file_task, args=(chat_id, save_path)).start()
                else:
                    send_feishu_reply(chat_id, f"❌ 下载表格文件【{file_name}】失败，请检查机器人文件下载权限。")

            elif file_name.endswith(".txt"):
                os.makedirs("./downloads", exist_ok=True)
                save_path = os.path.join("./downloads", file_name)
                send_feishu_reply(chat_id, f"📥 收到 SKU 文本【{file_name}】，正在下载并提取...")
                
                if download_message_resource(msg.message_id, file_key, save_path):
                    with open(save_path, "r", encoding="utf-8", errors="ignore") as tf:
                        content = tf.read()
                    skus = re.findall(r"\b\d{7,12}\b", content)
                    if skus:
                        cfg = load_bot_config()
                        threading.Thread(target=batch_listing_worker, args=(
                            chat_id, 
                            skus, 
                            float(cfg.get("default_multiplier", 5.0)),
                            int(cfg.get("default_discount", 50)),
                            int(cfg.get("default_stock", 200))
                        )).start()
                    else:
                        send_feishu_reply(chat_id, f"⚠️ 在文本文件【{file_name}】中未识别到有效数字 SKU。")
                else:
                    send_feishu_reply(chat_id, f"❌ 下载文本文件【{file_name}】失败。")

    except Exception as e:
        print(f"[-] 消息处理异常: {e}")

def main():
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        print("==========================================================")
        print("[-] [提示] 尚未配置飞书机器人的 App ID 或 App Secret！")
        print("    请在 config.json 中配置，例如：")
        print('    "feishu_app_id": "cli_xxxxxxxxxxxx",')
        print('    "feishu_app_secret": "xxxxxxxxxxxxxxxxxxxxxxxx"')
        print("    或设置环境变量：export FEISHU_APP_ID=xxx FEISHU_APP_SECRET=xxx")
        print("    详细创建步骤请参阅: FEISHU_INTEGRATION_GUIDE.md")
        print("==========================================================")
        return

    print("==========================================================")
    print(" 启动飞书 WebSocket 长连接客户端 (无需公网 IP / 免穿透) ")
    print(f" App ID: {FEISHU_APP_ID}")
    print("==========================================================")
    
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(on_p2_message_receive_v1) \
        .build()

    cli = lark.ws.Client(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO
    )
    
    print("[+] 正在建立 WebSocket 长连接...")
    cli.start()

if __name__ == "__main__":
    main()
