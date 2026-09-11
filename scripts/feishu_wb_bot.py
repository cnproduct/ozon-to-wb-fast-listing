# -*- coding: utf-8 -*-
"""
==============================================================================
Wildberries 极速智能上架助手 - 飞书 (Feishu / Lark) 官方长连接交互机器人 (v3.0)
==============================================================================
架构模式：官方 WebSocket 长连接模式 (免公网 IP、免内网穿透、免自建 Webhook)
核心功能：
1. 运营人员在飞书对话框直接发送单个/多个 Ozon SKU (如 "2780098271 2444330744")
2. 支持自然语言带参数快捷上架 (如 "3461665428 5355581747 售价5倍 50折 10库存")
3. 拖入 TXT/CSV 文件一键提取所有数字 SKU 并全自动批量流水线上架
4. 拖入 Excel 货盘表批量极速导入并自动化上架
5. 实时推送精美交互卡片（带 WB 在售超链接、大图、价格与现货库存）
6. 避坑词库动态管理 (查看避坑 / 添加避坑: 品牌1, 品牌2)
==============================================================================
"""

import os
import sys
import re
import json
import time
import logging
import threading
from typing import List, Dict, Any, Optional

import pandas as pd
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from wb_uploader import WildberriesAPIClient
from ozon_crawler import OzonCrawler

def load_bot_config() -> Dict[str, Any]:
    candidates = [
        os.path.join(WORKSPACE_DIR, 'config.json'),
        os.path.join(SCRIPT_DIR, 'config.json'),
        os.path.join(os.getcwd(), 'config.json'),
        r'd:\视频文件\config.json'
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

BOT_CONFIG = load_bot_config()
FEISHU_APP_ID = BOT_CONFIG.get("feishu_app_id") or os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = BOT_CONFIG.get("feishu_app_secret") or os.getenv("FEISHU_APP_SECRET", "")

lark_client = None
if FEISHU_APP_ID and FEISHU_APP_SECRET:
    lark_client = lark.Client.builder()         .app_id(FEISHU_APP_ID)         .app_secret(FEISHU_APP_SECRET)         .log_level(lark.LogLevel.INFO)         .build()

wb_client = WildberriesAPIClient()

def send_feishu_reply(chat_id: str, text: str):
    """向指定飞书聊天窗口发送文本消息"""
    if not lark_client:
        print(f"[-] [飞书未配置] 无法发送消息给 {chat_id}: {text}")
        return
    try:
        req = lark.BaseRequest()
        req.http_method = lark.HttpMethod.POST
        req.uri = "/open-apis/im/v1/messages?receive_id_type=chat_id"
        req.token_types = {lark.AccessTokenType.TENANT}
        req.body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False)
        }
        lark_client.request(req)
    except Exception as e:
        print(f"[-] 发送飞书文本消息异常: {e}")

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

def parse_inline_params(text: str, default_m: float = 5.0, default_d: int = 50, default_s: int = 10):
    """解析文本中的动态定价与库存参数 (支持 '售价*5倍', '库存设置10', '50折' 等格式)"""
    m = default_m
    d = default_d
    s = default_s

    # 倍数匹配: 支持 5倍、*5倍、x5、5.0倍、乘5倍、售价*5倍
    m_match = re.search(r'(?:售价|价格)?(?:\*|x|乘)?\s*(\d+(?:\.\d+)?)\s*倍', text, re.IGNORECASE)
    if m_match:
        try:
            m = float(m_match.group(1))
        except Exception:
            pass

    # 折扣匹配: 5折 -> 50, 50折/50% -> 50, 4折 -> 40
    d_match = re.search(r'(\d+)\s*(?:折|%)', text)
    if d_match:
        try:
            val = int(d_match.group(1))
            d = val * 10 if val <= 9 else val
        except Exception:
            pass

    # 库存匹配: 支持前缀式 (库存设置10, 库存10, 库存为10, 现货10) 与后缀式 (10件, 10个, 10库存)
    s_match = re.search(r'(?:库存(?:设置|为)?|现货)[:：\s]*(\d+)|(\d+)\s*(?:件|个|库存)', text)
    if s_match:
        try:
            val_str = s_match.group(1) or s_match.group(2)
            if val_str:
                s = int(val_str)
        except Exception:
            pass

    return m, d, s

def execute_single_listing_task(chat_id: str, sku: str, multiplier: float = 5.0, discount: int = 50, stock: int = 10, custom_dims: Dict = None, task_progress: str = "") -> bool:
    """后台执行单个 SKU 上架流水线"""
    prefix = f"{task_progress} " if task_progress else ""
    try:
        if not wb_client.token or wb_client.token == "YOUR_WB_API_TOKEN_HERE":
            send_feishu_reply(chat_id, f"❌ 上架失败 (SKU: {sku}): 未配置有效 WB_API_TOKEN！请在 config.json 中配置您的 Wildberries 卖家 Token。")
            return False

        # 1. 优先从本地 products.json 档案获取 (秒级命中)
        product_data = None
        ozon_price = 500.0
        json_path = os.path.join(WORKSPACE_DIR, 'products.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as pf:
                    cached_list = json.load(pf)
                    for cp in cached_list:
                        if str(cp.get('sku')) == str(sku):
                            product_data = dict(cp)
                            ozon_price = float(cp.get('ozon_price') or 500.0)
                            print(f"[+] SKU [{sku}] 命中本地 products.json 缓存: {product_data.get('title')[:30]}...")
                            break
            except Exception:
                pass

        # 2. 若未缓存，尝试从 Ozon 实时抓取
        if not product_data:
            crawler = OzonCrawler()
            fetched = crawler.fetch_product_by_sku(sku)
            if fetched and fetched.get("title") and fetched.get("photos"):
                product_data = fetched
                ozon_price = float(fetched.get("ozon_price") or 500.0)
                print(f"[+] SKU [{sku}] 从 Ozon 成功提取真实商品数据: {product_data.get('title')[:30]}...")

        # 3. 若抓取不到真实信息，安全阻断并提示，绝不盲目套用假数据
        if not product_data or not product_data.get("photos"):
            send_feishu_reply(chat_id, f"⚠️ {prefix}SKU [{sku}] 未能从 Ozon 提取到真实标题或高清相册（可能触发了 Ozon 防爬挑战验证或商品已下架）。\n💡 建议：可直接将包含该 SKU 的 Excel 货盘表发送给机器人一键导入！")
            return False

        if custom_dims:
            product_data.update(custom_dims)

        send_feishu_reply(chat_id, f"🚀 {prefix}正在为 SKU [{sku}]《{product_data['title'][:25]}...》启动 WB 官方 API 极速建卡流水线...")

        # 4. 调用 WB 客户端一键上架（带自动货号冲突递增与 60 字标题安全截断）
        res = wb_client.upload_single_product(
            product=product_data,
            ozon_price=ozon_price,
            multiplier=multiplier,
            discount=discount,
            stock=stock
        )

        # 5. 回写更新本地 products.json 记录
        try:
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as pf:
                    all_p = json.load(pf)
                updated = False
                for item in all_p:
                    if str(item.get('sku')) == str(sku):
                        item['nmID'] = res['nmID']
                        item['barcode'] = res['barcode']
                        item['vendorCode'] = res['vendorCode']
                        updated = True
                        break
                if not updated:
                    product_data['nmID'] = res['nmID']
                    product_data['barcode'] = res['barcode']
                    product_data['vendorCode'] = res['vendorCode']
                    all_p.append(product_data)
                with open(json_path, 'w', encoding='utf-8') as pf:
                    json.dump(all_p, pf, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 6. 组装飞书高亮卡片通知
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
        send_feishu_card(chat_id, f"🎉 {prefix}商品上架成功 (SKU: {sku})", card_lines, color="green")
        return True

    except Exception as e:
        send_feishu_reply(chat_id, f"❌ {prefix}上架失败 (SKU: {sku}):\n{str(e)}")
        return False

def batch_listing_worker(chat_id: str, skus: List[str], multiplier: float = 5.0, discount: int = 50, stock: int = 10):
    """批量上架任务工作线程 (支持列表文本与 TXT 文件)"""
    unique_skus = list(dict.fromkeys(skus))
    total = len(unique_skus)

    if total == 0:
        send_feishu_reply(chat_id, "⚠️ 未检测到有效数字 SKU 列表。")
        return

    start_card = [
        f"**任务总数**: 共识别到 **{total}** 款商品 SKU",
        f"**实售倍数**: **{multiplier} 倍** (到手实付 = Ozon原价 × {multiplier})",
        f"**促销折扣**: **{discount}%** (前台高吸引力大促划线标价)",
        f"**现货库存**: **{stock} 件** (莫斯科1仓现货秒级注入)",
        "---",
        "🚀 **流水线已启动，机器人正在按顺序逐一抓取、合规建卡、挂图与激活现货...**"
    ]
    send_feishu_card(chat_id, "📋 批量上架流水线启动", start_card, color="blue")

    success_count = 0
    failed_count = 0

    for i, sku in enumerate(unique_skus, 1):
        ok = execute_single_listing_task(
            chat_id=chat_id,
            sku=sku,
            multiplier=multiplier,
            discount=discount,
            stock=stock,
            task_progress=f"[{i}/{total}]"
        )
        if ok:
            success_count += 1
        else:
            failed_count += 1
            
        if i < total:
            time.sleep(2.0)

    # 最终汇总卡片
    summary_lines = [
        f"**处理结果**: 共 **{total}** 款商品",
        f"✅ **成功入库**: **{success_count}** 款",
        f"❌ **上架失败**: **{failed_count}** 款",
        "---",
        "💡 所有成功上架的商品均已实时配置售价、促销大促折与现货库存，买家端立即可搜！"
    ]
    summary_color = "green" if failed_count == 0 else "orange"
    send_feishu_card(chat_id, "🏁 批量上架任务处理完毕", summary_lines, color=summary_color)

def handle_excel_file_task(chat_id: str, file_path: str):
    """解析 Excel 表格并批量上架"""
    try:
        df = pd.read_excel(file_path)
        total = len(df)
        send_feishu_reply(chat_id, f"📊 成功读取表格，共检测到 {total} 行商品数据，开始批量流水线处理...")
        
        success = 0
        failed = 0
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

            ok = execute_single_listing_task(
                chat_id=chat_id,
                sku=sku,
                multiplier=float(row.get("售价倍数(默认5)", 5.0)),
                discount=int(row.get("折扣百分比(默认50)", 50)),
                stock=int(row.get("现货库存(默认10)", 10)),
                custom_dims=custom_dims,
                task_progress=f"[{idx+1}/{total}]"
            )
            if ok:
                success += 1
            else:
                failed += 1
            time.sleep(2.0)

        send_feishu_reply(chat_id, f"🏁 恭喜！当前表格中的全部商品已批量处理完毕 (成功: {success}, 失败: {failed})！")
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

    # 1. 查看避坑品牌
    if text_lower in ["避坑", "查看避坑", "敏感词", "品牌库", "品牌黑名单"]:
        brands_file = get_sensitive_brands_path()
        brands = []
        if os.path.exists(brands_file):
            with open(brands_file, "r", encoding="utf-8") as f:
                brands = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        lines = [
            f"**当前避坑品牌总数**: `{len(brands)} 个`",
            "**保护机制**: 上架商品时若标题或描述中含有这些品牌词，机器人将**自动脱敏为合规白牌**，严防 WB《要约》第 9.2.3 条违规封店！",
            "---",
            f"**部分词库列表**: {', '.join(brands[:25])}{'...' if len(brands) > 25 else ''}",
            "---",
            "💡 如需新增品牌，可发送：`添加避坑: 品牌A, 品牌B`"
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
        wh_id = cfg.get("wb_warehouse_id") or os.getenv("WB_WAREHOUSE_ID") or 2156484
        lines = [
            f"**Wildberries API Token**: {'✅ 已配置有效密钥' if token_set else '❌ 未配置 (请在 config.json 填入)'}",
            f"**履约仓库 ID**: `{wh_id}` (莫斯科1仓)",
            f"**默认售价倍数**: `{cfg.get('default_multiplier', 5.0)} 倍`",
            f"**默认官方折扣**: `{cfg.get('default_discount', 50)}%`",
            f"**默认备货库存**: `{cfg.get('default_stock', 10)} 件`",
            "---",
            "💡 如需上架商品，直接输入 SKU 列表、包含参数的指令，或将 TXT/Excel 文件拖入聊天框。"
        ]
        send_feishu_card(chat_id, "⚙️ 系统与店铺配置状态", lines, color="blue")
        return True

    return False

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

            # 匹配 SKU 数字列表 (7~12 位数字)
            found_skus = re.findall(r"\d{7,12}", raw_text)
            if found_skus:
                cfg = load_bot_config()
                def_m = float(cfg.get("default_multiplier", 5.0))
                def_d = int(cfg.get("default_discount", 50))
                def_s = int(cfg.get("default_stock", 10))
                m, d, s = parse_inline_params(raw_text, def_m, def_d, def_s)
                
                # 启动后台批量执行线程
                threading.Thread(target=batch_listing_worker, args=(chat_id, found_skus, m, d, s)).start()
            else:
                help_card = [
                    "👋 **我是 Wildberries 全自动极速上架助手！**",
                    "",
                    "你可以通过以下方式随时指挥我：",
                    "1️⃣ **直接发 SKU 列表**：直接发一个或多个 Ozon SKU（如 `3461665428 5355581747`），自动批量抓取并上架！",
                    "2️⃣ **带参数快捷上架**：发送 `3461665428 5355581747 上架，价格按售价*5倍，库存设置10`！",
                    "3️⃣ **拖入 TXT 文档**：把包含 SKU 列表的 `.txt` 文件直接发给机器人，自动批量处理！",
                    "4️⃣ **拖入 Excel 货盘表**：把包含 SKU 及规格属性的 `.xlsx` 表格发给机器人，自动批量上架！",
                    "5️⃣ **管理品牌避坑库**：发送 `查看避坑` 或 `添加避坑: 品牌1, 品牌2`",
                    "6️⃣ **查看状态**：发送 `状态` 查看店铺 API 与参数配置。"
                ]
                send_feishu_card(chat_id, "💡 WB 极速上架助手使用指南", help_card, color="blue")

        # 2. 用户发送文件 (Excel / TXT / CSV)
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

            elif file_name.endswith((".txt", ".csv")):
                os.makedirs("./downloads", exist_ok=True)
                save_path = os.path.join("./downloads", file_name)
                send_feishu_reply(chat_id, f"📥 收到 SKU 文本文件【{file_name}】，正在下载并提取...")
                
                if download_message_resource(msg.message_id, file_key, save_path):
                    with open(save_path, "r", encoding="utf-8", errors="ignore") as tf:
                        content = tf.read()
                    skus = re.findall(r"\d{7,12}", content)
                    unique_skus = list(dict.fromkeys(skus))
                    if unique_skus:
                        cfg = load_bot_config()
                        def_m = float(cfg.get("default_multiplier", 5.0))
                        def_d = int(cfg.get("default_discount", 50))
                        def_s = int(cfg.get("default_stock", 10))
                        m, d, s = parse_inline_params(file_name, def_m, def_d, def_s)

                        send_feishu_reply(chat_id, f"📄 从【{file_name}】成功提取出 {len(unique_skus)} 个有效商品 SKU，正在启动批量流水线！")
                        threading.Thread(target=batch_listing_worker, args=(
                            chat_id, 
                            unique_skus, 
                            m, 
                            d, 
                            s
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
