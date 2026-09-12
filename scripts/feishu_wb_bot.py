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
from store_manager import store_manager, decode_jwt_expiry
from store_analytics import store_analytics

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

def send_feishu_reply(chat_id: str, text: str, open_id: Optional[str] = None):
    """向指定飞书聊天窗口发送文本消息"""
    if not lark_client:
        print(f"[-] [飞书未配置] 无法发送消息给 {chat_id}: {text}")
        return
    try:
        receive_type = "open_id" if str(chat_id).startswith("ou_") else "chat_id"
        req = lark.BaseRequest()
        req.http_method = lark.HttpMethod.POST
        req.uri = f"/open-apis/im/v1/messages?receive_id_type={receive_type}"
        req.token_types = {lark.AccessTokenType.TENANT}
        req.body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False)
        }
        resp = lark_client.request(req)
        if resp.code == 0:
            print(f"[+] 飞书消息发送成功: {text[:30]}...")
            return
        print(f"[-] 飞书发送失败 (receive_id={chat_id}, type={receive_type}): code={resp.code}, msg={resp.msg}")
        if open_id and open_id != chat_id:
            req.uri = "/open-apis/im/v1/messages?receive_id_type=open_id"
            req.body["receive_id"] = open_id
            resp_fb = lark_client.request(req)
            if resp_fb.code == 0:
                print(f"[+] 飞书消息通过 open_id 发送成功: {text[:30]}...")
            else:
                print(f"[-] 飞书 open_id 备选发送亦失败: code={resp_fb.code}, msg={resp_fb.msg}")
    except Exception as e:
        print(f"[-] 发送飞书文本消息异常: {e}")

def send_feishu_card(chat_id: str, title: str, content_lines: List[str], color: str = "blue", open_id: Optional[str] = None):
    """发送排版优雅的飞书消息卡片"""
    if not lark_client:
        print(f"[-] [飞书未配置] 无法发送卡片给 {chat_id}: {title}")
        return
    try:
        receive_type = "open_id" if str(chat_id).startswith("ou_") else "chat_id"
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
        req.uri = f"/open-apis/im/v1/messages?receive_id_type={receive_type}"
        req.token_types = {lark.AccessTokenType.TENANT}
        req.body = {"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)}
        resp = lark_client.request(req)
        if resp.code == 0:
            print(f"[+] 飞书卡片发送成功: {title}")
            return
        print(f"[-] 飞书卡片发送失败 (receive_id={chat_id}, type={receive_type}): code={resp.code}, msg={resp.msg}")
        if open_id and open_id != chat_id:
            req.uri = "/open-apis/im/v1/messages?receive_id_type=open_id"
            req.body["receive_id"] = open_id
            resp_fb = lark_client.request(req)
            if resp_fb.code == 0:
                print(f"[+] 飞书卡片通过 open_id 发送成功: {title}")
            else:
                print(f"[-] 飞书卡片 open_id 备选发送亦失败: code={resp_fb.code}, msg={resp_fb.msg}")
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

def execute_single_listing_task(chat_id: str, sku: str, multiplier: float = 5.0, discount: int = 50, stock: int = 10, custom_dims: Dict = None, task_progress: str = "", open_id: Optional[str] = None, store_cfg: Optional[Dict] = None) -> bool:
    """后台执行单个 SKU 上架流水线 (支持按 chat_id 动态路由目标店铺与凭据)"""
    prefix = f"{task_progress} " if task_progress else ""
    try:
        if not store_cfg:
            store_cfg = store_manager.get_store_for_chat(chat_id)

        target_token = store_cfg.get("wb_api_token", "").strip()
        target_wh_id = int(store_cfg.get("wb_warehouse_id") or 2200658)
        target_store_name = store_cfg.get("store_name", "默认店铺")
        target_wh_name = store_cfg.get("warehouse_name", "履约仓")

        if not target_token or target_token == "YOUR_WB_API_TOKEN_HERE":
            send_feishu_reply(chat_id, f"❌ 上架失败 (SKU: {sku}): 本群尚未绑定有效 WB API 密钥！\n👉 请在群内发送：`绑定店铺 店铺名 密钥:eyJ... 仓库:ID` 进行配置。", open_id=open_id)
            return False

        wb_client = WildberriesAPIClient(api_token=target_token, warehouse_id=target_wh_id)

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
            send_feishu_reply(chat_id, f"⚠️ {prefix}SKU [{sku}] 未能从 Ozon 提取到真实标题或高清相册（可能触发了 Ozon 防爬挑战验证或商品已下架）。\n💡 建议：可直接将包含该 SKU 的 Excel 货盘表发送给机器人一键导入！", open_id=open_id)
            return False

        if custom_dims:
            product_data.update(custom_dims)

        send_feishu_reply(chat_id, f"🚀 {prefix}正在为 SKU [{sku}]《{product_data['title'][:25]}...》上架至店铺【{target_store_name}】...", open_id=open_id)

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
                        item['target_store'] = target_store_name
                        updated = True
                        break
                if not updated:
                    product_data['nmID'] = res['nmID']
                    product_data['barcode'] = res['barcode']
                    product_data['vendorCode'] = res['vendorCode']
                    product_data['target_store'] = target_store_name
                    all_p.append(product_data)
                with open(json_path, 'w', encoding='utf-8') as pf:
                    json.dump(all_p, pf, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 6. 组装飞书高亮卡片通知
        card_lines = [
            f"**目标店铺**: `{target_store_name}` ({target_wh_name} `ID:{target_wh_id}`)",
            f"**商品标题**: {product_data['title']}",
            f"**商家货号**: `{res['vendorCode']}`",
            f"**WB 官方 nmID**: [{res['nmID']}](https://www.wildberries.ru/catalog/{res['nmID']}/detail.aspx)",
            f"**官方条形码**: `{res['barcode']}`",
            f"---",
            f"💰 **实售价格**: **{res['sell_price']} ₽** (划线标价 {res['strike_price']} ₽，立享 {res['discount']}% 官方大促折)",
            f"📦 **现货库存**: **{res['stock']} 件** (现货在售已秒级激活)",
            f"📐 **包装规格**: {product_data.get('length_cm', 10)}×{product_data.get('width_cm', 10)}×{product_data.get('height_cm', 10)} cm | 毛重 {product_data.get('weight_g', 500)}g",
            f"---",
            f"✅ [点击直接在 WB 官网查看商品前台详情](https://www.wildberries.ru/catalog/{res['nmID']}/detail.aspx)"
        ]
        send_feishu_card(chat_id, f"🎉 {prefix}商品上架成功 (SKU: {sku})", card_lines, color="green", open_id=open_id)
        return True

    except Exception as e:
        send_feishu_reply(chat_id, f"❌ {prefix}上架失败 (SKU: {sku}):\n{str(e)}", open_id=open_id)
        return False

def batch_listing_worker(chat_id: str, skus: List[str], multiplier: float = 5.0, discount: int = 50, stock: int = 10, open_id: Optional[str] = None):
    """批量上架任务工作线程 (支持列表文本与 TXT 文件)"""
    store_cfg = store_manager.get_store_for_chat(chat_id)
    target_store_name = store_cfg.get("store_name", "默认店铺")
    target_wh_name = store_cfg.get("warehouse_name", "履约仓")
    target_wh_id = store_cfg.get("wb_warehouse_id", 2200658)
    is_custom = store_cfg.get("is_custom_binding", False)

    unique_skus = list(dict.fromkeys(skus))
    total = len(unique_skus)

    if total == 0:
        send_feishu_reply(chat_id, "⚠️ 未检测到有效数字 SKU 列表。", open_id=open_id)
        return

    start_card = [
        f"**目标店铺**: `{target_store_name}` {'(专属绑定)' if is_custom else '(全局默认)'}",
        f"**履约仓库**: `{target_wh_name}` (ID: `{target_wh_id}`)",
        f"**任务总数**: 共识别到 **{total}** 款商品 SKU",
        f"**实售倍数**: **{multiplier} 倍** (到手实付 = Ozon原价 × {multiplier})",
        f"**促销折扣**: **{discount}%** (前台高吸引力大促划线标价)",
        f"**现货库存**: **{stock} 件** (现货秒级注入)",
        "---",
        "🚀 **流水线已启动，机器人正在按顺序逐一抓取、合规建卡、挂图与激活现货...**"
    ]
    send_feishu_card(chat_id, "📋 批量上架流水线启动", start_card, color="blue", open_id=open_id)

    success_count = 0
    failed_count = 0

    for i, sku in enumerate(unique_skus, 1):
        try:
            ok = execute_single_listing_task(
                chat_id=chat_id,
                sku=sku,
                multiplier=multiplier,
                discount=discount,
                stock=stock,
                task_progress=f"[{i}/{total}]",
                open_id=open_id,
                store_cfg=store_cfg
            )
            if ok:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            failed_count += 1
            send_feishu_reply(chat_id, f"❌ [{i}/{total}] SKU {sku} 运行异常: {e}", open_id=open_id)
            
        if i < total:
            time.sleep(2.0)

    # 最终汇总卡片
    summary_lines = [
        f"**目标店铺**: `{target_store_name}` (仓号: `{target_wh_id}`)",
        f"**处理结果**: 共 **{total}** 款商品",
        f"✅ **成功入库**: **{success_count}** 款",
        f"❌ **上架失败**: **{failed_count}** 款",
        "---",
        "💡 所有成功上架的商品均已实时配置售价、促销大促折与现货库存，买家端立即可搜！"
    ]
    summary_color = "green" if failed_count == 0 else "orange"
    send_feishu_card(chat_id, "🏁 批量上架任务处理完毕", summary_lines, color=summary_color, open_id=open_id)

def handle_excel_file_task(chat_id: str, file_path: str, open_id: Optional[str] = None):
    """解析 Excel 表格并批量上架"""
    try:
        store_cfg = store_manager.get_store_for_chat(chat_id)
        df = pd.read_excel(file_path)
        total = len(df)
        send_feishu_reply(chat_id, f"📊 成功读取表格，共检测到 {total} 行商品数据，将上架至店铺【{store_cfg.get('store_name')}】，开始批量流水线处理...", open_id=open_id)
        
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
                multiplier=float(row.get("售价倍数(默认5)", store_cfg.get("default_multiplier", 5.0))),
                discount=int(row.get("折扣百分比(默认50)", store_cfg.get("default_discount", 50))),
                stock=int(row.get("现货库存(默认10)", store_cfg.get("default_stock", 10))),
                custom_dims=custom_dims,
                task_progress=f"[{idx+1}/{total}]",
                open_id=open_id,
                store_cfg=store_cfg
            )
            if ok:
                success += 1
            else:
                failed += 1
            time.sleep(2.0)

        send_feishu_reply(chat_id, f"🏁 恭喜！当前表格中的全部商品已批量处理完毕 (成功: {success}, 失败: {failed})！", open_id=open_id)
    except Exception as e:
        send_feishu_reply(chat_id, f"❌ 处理 Excel 表格失败: {e}", open_id=open_id)

def get_sensitive_brands_path() -> str:
    """获取敏感品牌知识库路径"""
    p1 = os.path.join(WORKSPACE_DIR, 'references', 'sensitive_brands.txt')
    if os.path.exists(os.path.dirname(p1)):
        return p1
    return os.path.join(SCRIPT_DIR, '..', 'references', 'sensitive_brands.txt')

def handle_text_commands(chat_id: str, raw_text: str, open_id: Optional[str] = None) -> bool:
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
        send_feishu_card(chat_id, "🛡️ 品牌避坑知识库", lines, color="blue", open_id=open_id)
        return True

    # 2. 添加避坑品牌
    if raw_text.startswith("添加避坑") or raw_text.startswith("+避坑"):
        raw_names = re.sub(r"^(?:添加避坑|[\+]避坑)[:：\s]+", "", raw_text)
        new_brands = [b.strip() for b in re.split(r"[,，\s\n]+", raw_names) if b.strip()]
        if not new_brands:
            send_feishu_reply(chat_id, "⚠️ 请提供要添加的品牌名称，例如：`添加避坑: Nike, Adidas`", open_id=open_id)
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
            send_feishu_reply(chat_id, f"✅ 成功添加 {len(to_add)} 个品牌到避坑库：{', '.join(to_add)}！后续上架将自动执行脱敏。", open_id=open_id)
        else:
            send_feishu_reply(chat_id, f"ℹ️ 这些品牌已存在于避坑库中：{', '.join(new_brands)}", open_id=open_id)
        return True

    # 3. 店铺与系统状态 (支持群级别独立显示)
    if text_lower in ["状态", "配置", "查看配置", "wb状态", "店铺状态", "查看店铺"]:
        store_cfg = store_manager.get_store_for_chat(chat_id)
        is_custom = store_cfg.get("is_custom_binding", False)
        token_set = bool(store_cfg.get("wb_api_token") and "YOUR_WB_API_TOKEN" not in store_cfg.get("wb_api_token"))
        wh_id = store_cfg.get("wb_warehouse_id", 2200658)
        wh_name = store_cfg.get("warehouse_name", "莫斯科1仓")
        store_name = store_cfg.get("store_name", "RR007")
        exp = store_cfg.get("token_expiry") or decode_jwt_expiry(store_cfg.get("wb_api_token", ""))
        bound_at = store_cfg.get("bound_at", "初始系统预置")
        
        lines = [
            f"**当前会话 ID**: `{chat_id}`",
            f"**店铺绑定状态**: {'🟢 **专属店铺绑定** (多租户独立隔离)' if is_custom else '⚪ **全局默认店铺** (兜底共享)'}",
            f"**当前目标店铺**: `{store_name}`",
            f"**履约仓库信息**: `{wh_name}` (ID: `{wh_id}`)",
            f"**Wildberries 密钥**: {'✅ 已配置有效密钥' if token_set else '❌ 未配置'} (有效期至: `{exp}`)",
            f"**默认售价倍数**: `{store_cfg.get('default_multiplier', 5.0)} 倍`",
            f"**默认官方折扣**: `{store_cfg.get('default_discount', 50)}%`",
            f"**默认现货库存**: `{store_cfg.get('default_stock', 10)} 件`",
            f"**配置绑定时间**: `{bound_at}`",
            "---",
            "💡 **多群路由指令**：",
            "👉 绑定/更换本群店铺：`绑定店铺 店铺名 密钥:eyJ... 仓库:ID 4.5倍 50折 12库存`",
            "👉 解绑恢复全局默认：`解绑店铺`"
        ]
        send_feishu_card(chat_id, "⚙️ 系统与店铺配置状态", lines, color="blue", open_id=open_id)
        return True

    # 4. 绑定专属店铺 (支持自然语言多字段提取与官方 API 实时验真)
    if raw_text.startswith("绑定店铺") or raw_text.startswith("+店铺") or raw_text.startswith("绑定"):
        parsed = store_manager.parse_binding_command(raw_text)
        if parsed and parsed.get("token"):
            send_feishu_reply(chat_id, "⏳ 正在通过 Wildberries 官方 API 验真您的店铺密钥与可用仓库列表，请稍候...", open_id=open_id)
            ok, msg, store = store_manager.bind_store(
                chat_id=chat_id,
                store_name=parsed.get("store_name", ""),
                token=parsed["token"],
                warehouse_id=parsed.get("warehouse_id"),
                multiplier=parsed.get("multiplier", 5.0),
                discount=parsed.get("discount", 50),
                stock=parsed.get("stock", 10),
                bound_by=str(open_id or chat_id)
            )
            if ok:
                send_feishu_reply(chat_id, msg, open_id=open_id)
            else:
                send_feishu_reply(chat_id, msg, open_id=open_id)
            return True
        else:
            curr_store = store_manager.get_store_for_chat(chat_id)
            guide_lines = [
                "🏢 **Wildberries 多群多租户店铺绑定指南**",
                f"当前群绑定状态: **{'【专属店铺】' if curr_store.get('is_custom_binding') else '【全局默认店铺】'}** `{curr_store.get('store_name')}`",
                f"当前履约仓: `{curr_store.get('warehouse_name', '仓库')}` (ID: `{curr_store.get('wb_warehouse_id')}`)",
                "---",
                "👉 **在本群直接发送绑定指令（任选一种格式即可）：**",
                "",
                "1️⃣ **自然语言式（最灵活）**：",
                "`绑定店铺 店铺简称:RR008 密钥:eyJ... 仓库:2200658 4.5倍 50折 12库存`",
                "",
                "2️⃣ **快捷简短式（最快速）**：",
                "`绑定店铺 RR008 eyJhbGciOi... 2200658`",
                "---",
                "🔒 **安全与隔离保障**：",
                "• 机器人自动通过 WB 官方 API 验真 Token 有效性，验证失败绝不保存。",
                "• 绑定成功后，本群所有成员发送的 SKU / 表格将 100% 自动上架至该专属店铺！",
                "• 如需恢复默认共享店铺，直接发送：`解绑店铺`"
            ]
            send_feishu_card(chat_id, "📋 店铺绑定操作向导", guide_lines, color="blue", open_id=open_id)
            return True

    # 5. 解绑专属店铺
    if text_lower in ["解绑店铺", "解绑", "重置店铺", "清除店铺"]:
        ok, msg = store_manager.unbind_store(chat_id)
        send_feishu_reply(chat_id, msg, open_id=open_id)
        return True

    # 6. 跨境运营问答与实时数据中枢 (销量/出单/待发货/库存盘点/单品诊断/利润测算/避坑法规)
    store_cfg = store_manager.get_store_for_chat(chat_id)
    op_res = store_analytics.handle_operations_query(raw_text, store_cfg)
    if op_res:
        title, lines, color = op_res
        send_feishu_card(chat_id, title, lines, color=color, open_id=open_id)
        return True

    return False

# ================= 飞书长连接消息事件监听 =================
def on_p2_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    """接收飞书用户发送的单聊或群聊消息"""
    try:
        msg = data.event.message
        chat_id = msg.chat_id
        msg_type = msg.message_type
        sender = getattr(data.event, "sender", None)
        sender_id = getattr(sender, "sender_id", None) if sender else None
        open_id = getattr(sender_id, "open_id", None) if sender_id else None

        # 1. 用户发送文本
        if msg_type == "text":
            text_json = json.loads(msg.content)
            raw_text = text_json.get("text", "").strip()
            print(f"[+] 收到飞书文本消息 (chat_id={chat_id}, open_id={open_id}): {raw_text}")

            # 先检查是否为管理指令 (避坑词库、状态、店铺绑定、运营数据查询等)
            if handle_text_commands(chat_id, raw_text, open_id=open_id):
                return

            # 匹配 SKU 数字列表 (7~12 位数字，完美支持换行、空格、逗号等各类分隔符)
            found_skus = re.findall(r"(?<!\d)\d{7,12}(?!\d)", raw_text)
            unique_skus = list(dict.fromkeys(found_skus))
            if unique_skus:
                store_cfg = store_manager.get_store_for_chat(chat_id)
                def_m = float(store_cfg.get("default_multiplier", 5.0))
                def_d = int(store_cfg.get("default_discount", 50))
                def_s = int(store_cfg.get("default_stock", 10))
                m, d, s = parse_inline_params(raw_text, def_m, def_d, def_s)
                
                # 启动后台批量执行线程
                threading.Thread(target=batch_listing_worker, args=(chat_id, unique_skus, m, d, s, open_id)).start()
            else:
                curr_store = store_manager.get_store_for_chat(chat_id)
                help_card = [
                    "👋 **我是 Wildberries 全自动极速上架与智能运营管家！**",
                    f"🏢 **当前群绑定店铺**: `{curr_store.get('store_name')}` ({curr_store.get('warehouse_name')} `{curr_store.get('wb_warehouse_id')}`)",
                    "",
                    "你可以随时通过自然语言在群内向我提问：",
                    "📈 **销售大盘**：发送 `今日销量`、`近7天销售额`、`出单`、`爆款排行`",
                    "🚚 **履约发货**：发送 `待发货`、`新订单`、`发货截止时间` (严防 50% 违约罚款)",
                    "📦 **现货库存**：发送 `查库存`、`剩余库存`、`缺货预警`",
                    "🗂️ **商品健康**：发送 `卡片总数`、`审核状态`、`被拒原因` 或直接发送 `查 1873753217`",
                    "🧮 **利润测算**：发送 `测算利润 990 4.5倍` 实时核算到手卢布与折合人民币净利",
                    "🛡️ **运营合规**：发送 `罚款规则`、`类目佣金`、`俄罗斯尺码`、`查看避坑`",
                    "⚙️ **店铺路由**：发送 `状态` 或 `绑定店铺 店铺名 密钥:eyJ... 仓库:ID`",
                    "🚀 **极速上架**：直接发送 SKU 列表、自然语言带参数，或将 TXT/Excel 文件拖入聊天框！"
                ]
                send_feishu_card(chat_id, "💡 WB 极速上架助手使用指南", help_card, color="blue", open_id=open_id)

        # 2. 用户发送文件 (Excel / TXT / CSV)
        elif msg_type == "file":
            file_info = json.loads(msg.content)
            file_name = file_info.get("file_name", "")
            file_key = file_info.get("file_key", "")
            print(f"[+] 收到飞书文件: {file_name}")

            if file_name.endswith((".xlsx", ".xls")):
                os.makedirs("./downloads", exist_ok=True)
                save_path = os.path.join("./downloads", file_name)
                send_feishu_reply(chat_id, f"📥 收到上架表格【{file_name}】，正在下载并解析...", open_id=open_id)
                
                if download_message_resource(msg.message_id, file_key, save_path):
                    threading.Thread(target=handle_excel_file_task, args=(chat_id, save_path, open_id)).start()
                else:
                    send_feishu_reply(chat_id, f"❌ 下载表格文件【{file_name}】失败，请检查机器人文件下载权限。", open_id=open_id)

            elif file_name.endswith((".txt", ".csv")):
                os.makedirs("./downloads", exist_ok=True)
                save_path = os.path.join("./downloads", file_name)
                send_feishu_reply(chat_id, f"📥 收到 SKU 文本文件【{file_name}】，正在下载并提取...", open_id=open_id)
                
                if download_message_resource(msg.message_id, file_key, save_path):
                    with open(save_path, "r", encoding="utf-8", errors="ignore") as tf:
                        content = tf.read()
                    skus = re.findall(r"(?<!\d)\d{7,12}(?!\d)", content)
                    unique_skus = list(dict.fromkeys(skus))
                    if unique_skus:
                        store_cfg = store_manager.get_store_for_chat(chat_id)
                        def_m = float(store_cfg.get("default_multiplier", 5.0))
                        def_d = int(store_cfg.get("default_discount", 50))
                        def_s = int(store_cfg.get("default_stock", 10))
                        m, d, s = parse_inline_params(file_name, def_m, def_d, def_s)

                        send_feishu_reply(chat_id, f"📄 从【{file_name}】成功提取出 {len(unique_skus)} 个有效商品 SKU，正在启动批量流水线！", open_id=open_id)
                        threading.Thread(target=batch_listing_worker, args=(
                            chat_id, 
                            unique_skus, 
                            m, 
                            d, 
                            s,
                            open_id
                        )).start()
                    else:
                        send_feishu_reply(chat_id, f"⚠️ 在文本文件【{file_name}】中未识别到有效数字 SKU。", open_id=open_id)
                else:
                    send_feishu_reply(chat_id, f"❌ 下载文本文件【{file_name}】失败。", open_id=open_id)

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
