# -*- coding: utf-8 -*-
"""
==============================================================================
Wildberries 极速智能上架助手 - 飞书 (Feishu / Lark) 官方长连接交互机器人 (v5.0)
https://github.com/cnproduct/ozon-to-wb-fast-listing
==============================================================================
架构模式：官方 WebSocket 长连接模式 (免公网 IP、免内网穿透、免自建 Webhook)
集成最新核心技能规范与执行铁律：
1. 【零信任商业授权门禁与收银台 (Alipay Cashier Mode B)】:
   - 商业授权核验、一机一码硬件绑定 (MID-XXXX-XXXX-XXXX-XXXX)
   - 支持扫码购买单店商业授权 (¥600/店铺) 与 在线发码激活
2. 【先问后干】第一响应铁律:
   - 收到 SKU 列表第一步呈报有效 SKU，询问售价策略 (默认 6 倍实售, 12 倍划线, 50% 官方大促, 5件现货)
   - 允许并响应动态倍数调整 (如 "3倍", "5倍 10库存")
3. 【跨境店铺人民币统一价格核算法则】:
   - 以人民币 (CNY) 为核算基准，提取 Ozon 绿标价换算人民币
   - 实售倍数 M，划线标价 2M，50% 官方大促折扣，API 整型约束化
4. 【真实物理形态包装尺寸与毛重三层推导】:
   - 穿透 Ozon 真实外包装与毛重，缺失时按物理形态精准推导，杜绝假模板与 isValid=False
5. 【详情页 100% 剥离 Ozon 编码与竞对平台痕迹 & 白牌 100% 脱敏】
6. 【平台封禁卡片自动隔离容错 & 莫斯科1仓现货秒级注入】
==============================================================================
"""

import os
import sys
import re
import json
import time
import math
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

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
from morphology_engine import PhysicalMorphologyEngine
from category_matcher import match_subject_and_specs, clean_title_and_text
from machine_fingerprint import get_machine_id

try:
    from license_crypto import LicenseCrypto
except ImportError:
    LicenseCrypto = None

try:
    from cloud_auth import CloudAuthClient
except ImportError:
    CloudAuthClient = None

# 全局待确认任务缓存队列 (先问后干机制)
PENDING_CONFIRMATIONS: Dict[str, Dict[str, Any]] = {}

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
    lark_client = lark.Client.builder() \
        .app_id(FEISHU_APP_ID) \
        .app_secret(FEISHU_APP_SECRET) \
        .log_level(lark.LogLevel.INFO) \
        .build()

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

def parse_inline_params(text: str, default_m: float = 6.0, default_d: int = 50, default_s: int = 5) -> Tuple[float, int, int, bool]:
    """
    解析文本中的动态定价与库存参数 (支持 '6倍', '售价*6倍', '库存5', '50折' 等格式)
    返回: (multiplier, discount, stock, has_explicit_params)
    """
    m = default_m
    d = default_d
    s = default_s
    has_explicit = False

    # 倍数匹配: 支持 3倍、5倍、6倍、*6倍、x6、6.0倍、乘6倍、售价*6倍、按3倍上架
    m_match = re.search(r'(?:售价|价格|按)?(?:\*|x|乘)?\s*(\d+(?:\.\d+)?)\s*倍', text, re.IGNORECASE)
    if m_match:
        try:
            m = float(m_match.group(1))
            has_explicit = True
        except Exception:
            pass

    # 折扣匹配: 5折 -> 50, 50折/50% -> 50, 4折 -> 40
    d_match = re.search(r'(\d+)\s*(?:折|%)', text)
    if d_match:
        try:
            val = int(d_match.group(1))
            d = val * 10 if val <= 9 else val
            has_explicit = True
        except Exception:
            pass

    # 库存匹配: 支持前缀式 (库存5, 库存设置5, 现货5) 与后缀式 (5件, 5个, 5库存)
    s_match = re.search(r'(?:库存(?:设置|为)?|现货)[:：\s]*(\d+)|(\d+)\s*(?:件|个|库存)', text)
    if s_match:
        try:
            val_str = s_match.group(1) or s_match.group(2)
            if val_str:
                s = int(val_str)
                has_explicit = True
        except Exception:
            pass

    return m, d, s, has_explicit

def execute_single_listing_task(
    chat_id: str,
    sku: str,
    multiplier: float = 6.0,
    discount: int = 50,
    stock: int = 5,
    custom_dims: Dict = None,
    task_progress: str = "",
    open_id: Optional[str] = None,
    store_cfg: Optional[Dict] = None
) -> bool:
    """后台执行单个 SKU 极速上架流水线 (融入人民币核算、形态推导与全要素闭环)"""
    prefix = f"{task_progress} " if task_progress else ""
    try:
        if not store_cfg:
            store_cfg = store_manager.get_store_for_chat(chat_id)

        target_token = store_cfg.get("wb_api_token", "").strip()
        target_wh_id = int(store_cfg.get("wb_warehouse_id") or 2200658)
        target_store_name = store_cfg.get("store_name", "默认店铺")
        target_wh_name = store_cfg.get("warehouse_name", "莫斯科1仓")

        if not target_token or target_token == "YOUR_WB_API_TOKEN_HERE":
            send_feishu_reply(chat_id, f"❌ 上架失败 (SKU: {sku}): 本群尚未绑定有效 WB API 密钥！\n👉 请在群内发送：`绑定店铺 店铺名 密钥:eyJ... 仓库:ID` 进行配置。", open_id=open_id)
            return False

        wb_client = WildberriesAPIClient(api_token=target_token, warehouse_id=target_wh_id)

        # 1. 优先从本地 products.json 档案获取 (秒级命中)
        product_data = None
        ozon_price_rub = 500.0
        json_path = os.path.join(WORKSPACE_DIR, 'products.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as pf:
                    cached_list = json.load(pf)
                    for cp in cached_list:
                        if str(cp.get('sku')) == str(sku):
                            product_data = dict(cp)
                            ozon_price_rub = float(cp.get('ozon_price') or cp.get('price') or 500.0)
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
                ozon_price_rub = float(fetched.get("ozon_price") or fetched.get("price") or 500.0)
                print(f"[+] SKU [{sku}] 从 Ozon 成功提取真实商品数据: {product_data.get('title')[:30]}...")

        # 3. 严格真实性校验：读取不到真实标题或相册，安全阻断，绝不盲目跨品类兜底
        if not product_data or not product_data.get("photos"):
            send_feishu_reply(chat_id, f"⚠️ {prefix}SKU [{sku}] 未能从 Ozon 提取到真实标题或高清相册（可能触发了防爬验证或商品已下架）。\n💡 建议：可直接将包含该 SKU 的 Excel 货盘表发送给机器人一键导入！", open_id=open_id)
            return False

        # 4. 人民币统一核算法则 (Rule 3)
        ozon_cny_rate = float(BOT_CONFIG.get('ozon_cny_rate', 12.535))
        if product_data.get('ozon_price_cny'):
            ozon_price_cny = float(product_data['ozon_price_cny'])
        else:
            ozon_price_cny = round(ozon_price_rub / ozon_cny_rate, 2)

        # 动态价格计算: 实售倍数 M, 划线价 2M, 50% 官方大促
        strike_price_cny = round(ozon_price_cny * (2 * multiplier))
        sell_price_cny = round(strike_price_cny * (1 - discount / 100.0))
        strike_price_rub = round(strike_price_cny * ozon_cny_rate)
        sell_price_rub = round(sell_price_cny * ozon_cny_rate)

        # 5. 真实物理形态包装尺寸与毛重推导 (Rule 4)
        if custom_dims:
            product_data.update(custom_dims)
        else:
            deduced = PhysicalMorphologyEngine.deduce_dimensions_and_weight(
                title=product_data.get('title', ''),
                raw_props=product_data.get('properties') or {},
                sku=str(sku)
            )
            product_data['length_cm'] = deduced['length_cm']
            product_data['width_cm'] = deduced['width_cm']
            product_data['height_cm'] = deduced['height_cm']
            product_data['weight_g'] = deduced['weight_g']

        # 6. 详情页 100% 剥离竞对痕迹与白牌脱敏 (Rule 5 & 6)
        clean_desc = clean_title_and_text(product_data.get('description', ''), sku=str(sku))
        product_data['description'] = clean_desc
        product_data['brand'] = ""  # 白牌脱敏

        send_feishu_reply(
            chat_id,
            f"🚀 {prefix}正在为 SKU [{sku}]《{product_data['title'][:25]}...》上架至【{target_store_name}】\n💰 人民币实售: ¥{sell_price_cny} (划线价 ¥{strike_price_cny}, {discount}%折, 约 {sell_price_rub} ₽) | 现货: {stock} 件",
            open_id=open_id
        )

        # 7. 调用 WB 核心客户端建卡、直传相册、设置折扣与现货库存
        res = wb_client.upload_single_product(
            product=product_data,
            ozon_price=ozon_price_cny if BOT_CONFIG.get('store_currency') == 'CNY' else ozon_price_rub,
            multiplier=multiplier,
            discount=discount,
            stock=stock
        )

        # 8. 回写更新本地 products.json 档案
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
                        item['sell_price_cny'] = sell_price_cny
                        item['strike_price_cny'] = strike_price_cny
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

        # 9. 组装全要素交付飞书高亮卡片 (Rule 11)
        card_lines = [
            f"**目标店铺**: `{target_store_name}` ({target_wh_name} `ID:{target_wh_id}`)",
            f"**商品标题**: {product_data['title']}",
            f"**商家货号**: `{res['vendorCode']}`",
            f"**WB 官方 nmID**: [{res['nmID']}](https://www.wildberries.ru/catalog/{res['nmID']}/detail.aspx)",
            f"**官方条形码**: `{res['barcode']}`",
            f"---",
            f"💰 **核算价格**: **¥{sell_price_cny} 元** (划线标价 ¥{strike_price_cny} 元，立享 {discount}% 官方大促折，折合约 **{sell_price_rub} ₽**)",
            f"📦 **现货库存**: **{stock} 件** ({target_wh_name} 现货秒级注入生效)",
            f"📐 **包装规格**: {product_data.get('length_cm', 10)}×{product_data.get('width_cm', 10)}×{product_data.get('height_cm', 10)} cm | 毛重 {round(product_data.get('weight_g', 500)/1000.0, 2)} kg",
            f"🛡️ **合规状态**: 白牌安全脱敏 · 描述剥离竞对痕迹 · 参数 100% 丰富注入",
            f"---",
            f"✅ [点击直接在 WB 官网查看商品前台详情](https://www.wildberries.ru/catalog/{res['nmID']}/detail.aspx)"
        ]
        send_feishu_card(chat_id, f"🎉 {prefix}商品上架成功 (SKU: {sku})", card_lines, color="green", open_id=open_id)
        return True

    except Exception as e:
        send_feishu_reply(chat_id, f"❌ {prefix}上架失败 (SKU: {sku}):\n{str(e)}", open_id=open_id)
        return False

def batch_listing_worker(chat_id: str, skus: List[str], multiplier: float = 6.0, discount: int = 50, stock: int = 5, open_id: Optional[str] = None):
    """批量上架任务工作线程 (支持列表文本与 TXT 文件)"""
    store_cfg = store_manager.get_store_for_chat(chat_id)
    target_store_name = store_cfg.get("store_name", "默认店铺")
    target_wh_name = store_cfg.get("warehouse_name", "莫斯科1仓")
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
        f"**实售定价**: **{multiplier} 倍实售** (划线标价 {multiplier*2} 倍，立享 {discount}% 官方大促折)",
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
        "💡 所有成功上架的商品均已实时配置售价、50%促销大促折与现货库存，买家端立即可搜！"
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
                multiplier=float(row.get("售价倍数(默认6)", store_cfg.get("default_multiplier", 6.0))),
                discount=int(row.get("折扣百分比(默认50)", store_cfg.get("default_discount", 50))),
                stock=int(row.get("现货库存(默认5)", store_cfg.get("default_stock", 5))),
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
    p1 = os.path.join(WORKSPACE_DIR, 'references', 'sensitive_brands.txt')
    if os.path.exists(os.path.dirname(p1)):
        return p1
    return os.path.join(SCRIPT_DIR, '..', 'references', 'sensitive_brands.txt')

def handle_text_commands(chat_id: str, raw_text: str, open_id: Optional[str] = None) -> bool:
    """处理避坑词库、机器码、收银台、授权激活、店铺绑定等指令"""
    text_lower = raw_text.lower().strip()

    # 1. 商业授权 - 获取机器码
    if text_lower in ["获取机器码", "机器码", "mid", "查看机器码", "获取mid"]:
        mid = get_machine_id()
        lines = [
            f"**当前设备专属机器码 (MID)**:",
            f"`{mid}`",
            "---",
            "🛡️ **一机一码物理绑定说明**：",
            "• 该指纹为当前服务器/电脑的专属硬件标识；",
            "• 请将此机器码复制并填入收银台，或发送给管理员签发专属不可篡改商业授权码；",
            "• 扫码购买单店商业授权：发送 `收银台` 或 `购买授权`。"
        ]
        send_feishu_card(chat_id, "💻 本机专属硬件机器码", lines, color="blue", open_id=open_id)
        return True

    # 2. 商业授权 - 购买授权 / 收银台
    if text_lower in ["购买授权", "收银台", "开通", "收费标准", "价格", "购买", "收费", "购买套餐"]:
        cashier_url = "https://wb-auth-gateway.cnproduct.workers.dev/pay"
        lines = [
            "⚡ **Wildberries 极速智能上架助手 · 官方商业授权收银台**",
            "---",
            "💰 **计费标准与收费模式**：",
            "• **¥600.00 元人民币 / 店铺** (按 Wildberries 店铺计费，1店1码)；",
            "• **单窗口 1:1 店铺互斥锁定**，从物理根源彻底杜绝商品串店误传与库存错乱；",
            "• 永久商业授权，含 1 次平滑安全换店配额；",
            "---",
            f"🛒 **[👉 点击此处立即打开官方收银台自助开通]({cashier_url})**",
            f"• 收银台地址: `{cashier_url}`",
            "---",
            "🚀 **自动发码流程**：",
            "1. 打开上方收银台，输入您的电脑机器码（发送 `获取机器码` 可查）与店铺名称；",
            "2. 使用支付宝扫码支付 ¥600 元，系统秒级自动签发专属授权码；",
            "3. 在本群发送 `激活授权 <授权码>` 即可立即解锁极速搬家上架！"
        ]
        send_feishu_card(chat_id, "🛒 商业授权自助收银台", lines, color="green", open_id=open_id)
        return True

    # 3. 商业授权 - 激活授权
    if raw_text.startswith("激活授权") or raw_text.startswith("激活") or raw_text.startswith("授权"):
        key_match = re.search(r'(?:激活授权|激活|授权)[:：\s]+(LIC-[A-Za-z0-9_\-\+\/=]+)', raw_text)
        if not key_match:
            send_feishu_reply(chat_id, "⚠️ 请提供有效的授权码，格式例如：`激活授权 LIC-RSA-eyJwIjp7...`", open_id=open_id)
            return True
        license_key = key_match.group(1).strip()
        
        # 执行验签与激活
        mid = get_machine_id()
        valid = False
        lic_info = {}
        error_msg = ""
        
        if LicenseCrypto:
            try:
                crypto = LicenseCrypto()
                payload = crypto.verify_license(license_key, current_mid=mid)
                valid = True
                lic_info = payload
            except Exception as e:
                error_msg = str(e)

        if valid:
            # 记录到群绑定与会话管理器
            store_cfg = store_manager.get_store_for_chat(chat_id)
            store_cfg["license_key"] = license_key
            store_cfg["license_name"] = lic_info.get("name", "商业客户")
            store_cfg["license_expires"] = lic_info.get("exp", "永久")
            store_manager.save_bindings({**store_manager.load_bindings(), chat_id: store_cfg})

            lines = [
                f"**授权客户**: `{lic_info.get('name', '商业客户')}`",
                f"**绑定店铺**: `{lic_info.get('store', store_cfg.get('store_name', 'WB专属店铺'))}`",
                f"**绑定机器码**: `{mid}`",
                f"**授权有效期**: `{lic_info.get('exp', '永久')}`",
                f"**授权状态**: 🟢 **已成功激活并锁定当前群会话**",
                "---",
                "🎉 **恭喜！您已成功开通 WB 极速智能上架助手商业授权！**",
                "👉 接下来可直接发送 Ozon SKU 列表或将货盘表格拖入本群启动极速上架。"
            ]
            send_feishu_card(chat_id, "🎉 商业授权激活成功", lines, color="green", open_id=open_id)
        else:
            send_feishu_reply(chat_id, f"❌ 授权码验证失败: {error_msg}\n💡 请检查授权码是否正确复制，或前往收银台重新签发。", open_id=open_id)
        return True

    # 4. 查看避坑品牌
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

    # 5. 添加避坑品牌
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

    # 6. 店铺与系统状态 (支持群级别独立显示)
    if text_lower in ["状态", "配置", "查看配置", "wb状态", "店铺状态", "查看店铺"]:
        store_cfg = store_manager.get_store_for_chat(chat_id)
        is_custom = store_cfg.get("is_custom_binding", False)
        token_set = bool(store_cfg.get("wb_api_token") and "YOUR_WB_API_TOKEN" not in store_cfg.get("wb_api_token"))
        wh_id = store_cfg.get("wb_warehouse_id", 2200658)
        wh_name = store_cfg.get("warehouse_name", "莫斯科1仓")
        store_name = store_cfg.get("store_name", "RR007")
        exp = store_cfg.get("token_expiry") or decode_jwt_expiry(store_cfg.get("wb_api_token", ""))
        bound_at = store_cfg.get("bound_at", "初始系统预置")
        lic_name = store_cfg.get("license_name", "商业授权")
        
        lines = [
            f"**当前会话 ID**: `{chat_id}`",
            f"**商业授权状态**: 🟢 `{lic_name}` (机器码: `{get_machine_id()[:14]}...`)",
            f"**店铺绑定状态**: {'🟢 **专属店铺绑定** (1:1 独立互斥隔离)' if is_custom else '⚪ **全局默认店铺** (兜底共享)'}",
            f"**当前目标店铺**: `{store_name}`",
            f"**履约仓库信息**: `{wh_name}` (ID: `{wh_id}`)",
            f"**Wildberries 密钥**: {'✅ 已配置有效密钥' if token_set else '❌ 未配置'} (有效期至: `{exp}`)",
            f"**默认售价策略**: `{store_cfg.get('default_multiplier', 6.0)} 倍实售` (划线标价 12 倍，立享 50% 官方大促折)",
            f"**默认现货库存**: `{store_cfg.get('default_stock', 5)} 件` (莫斯科1仓现货)",
            f"**配置绑定时间**: `{bound_at}`",
            "---",
            "💡 **快捷指令**：",
            "👉 绑定/切换本群店铺：`切换店铺 店铺名 密钥:eyJ... 仓库:ID`",
            "👉 解绑恢复全局默认：`解绑店铺`",
            "👉 扫码开通店铺授权：`收银台`"
        ]
        send_feishu_card(chat_id, "⚙️ 系统与店铺配置状态", lines, color="blue", open_id=open_id)
        return True

    # 7. 绑定 / 切换专属店铺 (支持自然语言多字段提取与官方 API 实时验真)
    if raw_text.startswith("绑定店铺") or raw_text.startswith("切换店铺") or raw_text.startswith("+店铺") or raw_text.startswith("绑定"):
        parsed = store_manager.parse_binding_command(raw_text)
        if parsed and parsed.get("token"):
            send_feishu_reply(chat_id, "⏳ 正在通过 Wildberries 官方 API 验真您的店铺密钥与可用仓库列表，请稍候...", open_id=open_id)
            ok, msg, store = store_manager.bind_store(
                chat_id=chat_id,
                store_name=parsed.get("store_name", ""),
                token=parsed["token"],
                warehouse_id=parsed.get("warehouse_id"),
                multiplier=parsed.get("multiplier", 6.0),
                discount=parsed.get("discount", 50),
                stock=parsed.get("stock", 5),
                bound_by=str(open_id or chat_id)
            )
            send_feishu_reply(chat_id, msg, open_id=open_id)
            return True
        else:
            curr_store = store_manager.get_store_for_chat(chat_id)
            guide_lines = [
                "🏢 **Wildberries 单店 1:1 专属店铺绑定指南**",
                f"当前群绑定状态: **{'【专属店铺】' if curr_store.get('is_custom_binding') else '【全局默认店铺】'}** `{curr_store.get('store_name')}`",
                f"当前履约仓: `{curr_store.get('warehouse_name', '仓库')}` (ID: `{curr_store.get('wb_warehouse_id')}`)",
                "---",
                "👉 **在本群直接发送绑定指令（任选一种格式即可）：**",
                "",
                "1️⃣ **自然语言式（最灵活）**：",
                "`切换店铺 店铺简称:我的WB一店 密钥:eyJ... 仓库:2200658 6倍 50折 5库存`",
                "",
                "2️⃣ **快捷简短式（最快速）**：",
                "`切换店铺 我的WB一店 eyJhbGciOi... 2200658`",
                "---",
                "🔒 **安全与隔离保障**：",
                "• 机器人自动通过 WB 官方 API 验真 Token 有效性与仓库可用性。",
                "• 单窗口 1:1 店铺互斥锁定，彻底杜绝商品串店误传与库存错乱！"
            ]
            send_feishu_card(chat_id, "📋 店铺绑定操作向导", guide_lines, color="blue", open_id=open_id)
            return True

    # 8. 解绑专属店铺
    if text_lower in ["解绑店铺", "解绑", "重置店铺", "清除店铺"]:
        ok, msg = store_manager.unbind_store(chat_id)
        send_feishu_reply(chat_id, msg, open_id=open_id)
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

            # 优先级 1：系统级管理指令 (机器码、收银台、授权激活、避坑词库、状态、店铺绑定/解绑)
            if handle_text_commands(chat_id, raw_text, open_id=open_id):
                return

            # 优先级 2：【先问后干】用户确认已呈报的任务 (回复 "确认" / "上架" / "ok" / "6倍" 等)
            text_strip = raw_text.strip().lower()
            if chat_id in PENDING_CONFIRMATIONS:
                pending_info = PENDING_CONFIRMATIONS[chat_id]
                # 检查是否在 10 分钟有效期内
                if time.time() - pending_info.get("timestamp", 0) < 600:
                    is_confirm = any(text_strip.startswith(w) for w in ["确认", "直接上架", "上架", "开始", "执行", "ok", "好的", "1", "yes", "go"])
                    # 或者用户直接回复了新的倍数/库存 (如 "3倍", "6倍", "5倍 10库存")
                    m_val, d_val, s_val, has_exp = parse_inline_params(raw_text)
                    
                    if is_confirm or has_exp:
                        skus = pending_info["skus"]
                        del PENDING_CONFIRMATIONS[chat_id]
                        store_cfg = store_manager.get_store_for_chat(chat_id)
                        def_m = float(store_cfg.get("default_multiplier", 6.0))
                        def_d = int(store_cfg.get("default_discount", 50))
                        def_s = int(store_cfg.get("default_stock", 5))
                        m, d, s, _ = parse_inline_params(raw_text, def_m, def_d, def_s)
                        
                        send_feishu_reply(chat_id, f"✅ 已收到您的确认！按 **{m} 倍实售**（50%大促折，{s}件库存）立即启动批量上架流水线！", open_id=open_id)
                        threading.Thread(target=batch_listing_worker, args=(chat_id, skus, m, d, s, open_id)).start()
                        return

            # 匹配 SKU 数字列表 (7~12 位数字)
            found_skus = re.findall(r"(?<!\d)\d{7,12}(?!\d)", raw_text)
            unique_skus = list(dict.fromkeys(found_skus))

            # 判断是否为单一 SKU 诊断查询 (例如: "查 1873753217"、"搜 1871835158")
            is_sku_query = any(raw_text.startswith(p) for p in ["查 ", "搜 ", "查询 ", "查:", "搜:", "查询:", "查：", "搜：", "查询："]) and len(unique_skus) == 1

            # 优先级 3：识别到数字 SKU 列表的处理
            if unique_skus and not is_sku_query:
                store_cfg = store_manager.get_store_for_chat(chat_id)
                def_m = float(store_cfg.get("default_multiplier", 6.0))
                def_d = int(store_cfg.get("default_discount", 50))
                def_s = int(store_cfg.get("default_stock", 5))
                m, d, s, has_explicit = parse_inline_params(raw_text, def_m, def_d, def_s)

                # 【先问后干铁律】：如果用户输入了明确参数（如 3倍、6倍、5件），直接全速执行；
                # 如果是未指定倍数的纯 SKU，第一步立即呈报并询问策略！
                if has_explicit:
                    threading.Thread(target=batch_listing_worker, args=(chat_id, unique_skus, m, d, s, open_id)).start()
                    return
                else:
                    # 记录待确认
                    PENDING_CONFIRMATIONS[chat_id] = {
                        "skus": unique_skus,
                        "timestamp": time.time(),
                        "source": "text"
                    }
                    target_store_name = store_cfg.get("store_name", "专属店铺")
                    target_wh_name = store_cfg.get("warehouse_name", "莫斯科1仓")
                    
                    ask_lines = [
                        f"**目标店铺**: `{target_store_name}` ({target_wh_name})",
                        f"**已识别有效商品 SKU**: 共 **{len(unique_skus)}** 款",
                        f"**SKU 列表**: `{', '.join(unique_skus[:10])}{'...' if len(unique_skus)>10 else ''}`",
                        "---",
                        "📊 **【先问后干】默认推荐上架策略**：",
                        f"• **实售价格**: **{def_m} 倍实售**（划线标价 {def_m*2} 倍，立享 50% 官方大促折）",
                        f"• **现货库存**: **{def_s} 件**（莫斯科1仓现货秒级注入）",
                        f"• **商品规格**: 真实物理外包装推导 · 描述剥离竞对痕迹 · 白牌合规脱敏",
                        "---",
                        "👉 **请回复确认或指定自定义策略**：",
                        "1. 发送「**确认**」或「**直接上架**」：按默认 6 倍实售/5件现货立即执行；",
                        "2. 或发送「**3倍**」、「**5倍 10库存**」：按您指定的策略立即上架！"
                    ]
                    send_feishu_card(chat_id, f"📋 已识别 {len(unique_skus)} 款待上架商品，请确认策略", ask_lines, color="blue", open_id=open_id)
                    return

            # 优先级 4：跨境运营问答与实时数据中枢 (销量/出单/待发货/库存盘点/单品诊断/利润测算/避坑法规)
            store_cfg = store_manager.get_store_for_chat(chat_id)
            op_res = store_analytics.handle_operations_query(raw_text, store_cfg)
            if op_res:
                title, lines, color = op_res
                send_feishu_card(chat_id, title, lines, color=color, open_id=open_id)
                return

            # 优先级 5：兜底帮助卡片
            curr_store = store_manager.get_store_for_chat(chat_id)
            help_card = [
                "👋 **我是 Wildberries 全自动极速上架与智能运营管家！**",
                f"🏢 **当前群绑定店铺**: `{curr_store.get('store_name')}` ({curr_store.get('warehouse_name')} `{curr_store.get('wb_warehouse_id')}`)",
                "",
                "你可以随时在群内直接向我发送指令或提问：",
                "🚀 **极速搬家**：直接发送 Ozon SKU 列表、自然语言带参数（如 `2780098271 6倍 5库存`），或拖入 TXT/Excel 文件！",
                "🛒 **商业授权**：发送 `收银台` 或 `购买授权`（¥600/店铺，扫码秒级发码），发送 `获取机器码` 查看专属指纹",
                "📈 **销售大盘**：发送 `今日销量`、`近7天销售额`、`出单`、`爆款排行`",
                "🚚 **履约发货**：发送 `待发货`、`新订单`、`发货截止时间` (严防 50% 违约罚款)",
                "📦 **现货库存**：发送 `查库存`、`剩余库存`、`缺货预警`",
                "🗂️ **商品诊断**：发送 `卡片总数`、`审核状态` 或直接发送 `查 1873753217`",
                "🧮 **利润测算**：发送 `测算利润 990 6倍` 实时核算到手卢布与折合人民币净利",
                "🛡️ **运营合规**：发送 `罚款规则`、`俄罗斯尺码`、`查看避坑`",
                "⚙️ **店铺切换**：发送 `状态` 或 `切换店铺 店铺名 密钥:eyJ... 仓库:ID`"
            ]
            send_feishu_card(chat_id, "💡 WB 极速上架助手使用指南", help_card, color="blue", open_id=open_id)
            return

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
                        def_m = float(store_cfg.get("default_multiplier", 6.0))
                        def_d = int(store_cfg.get("default_discount", 50))
                        def_s = int(store_cfg.get("default_stock", 5))
                        m, d, s, has_explicit = parse_inline_params(file_name, def_m, def_d, def_s)

                        if has_explicit:
                            send_feishu_reply(chat_id, f"📄 从【{file_name}】成功提取出 {len(unique_skus)} 个有效商品 SKU，正在按指定策略启动批量流水线！", open_id=open_id)
                            threading.Thread(target=batch_listing_worker, args=(chat_id, unique_skus, m, d, s, open_id)).start()
                        else:
                            PENDING_CONFIRMATIONS[chat_id] = {
                                "skus": unique_skus,
                                "timestamp": time.time(),
                                "source": "file",
                                "file_name": file_name
                            }
                            ask_lines = [
                                f"**来源文件**: `{file_name}`",
                                f"**已识别有效商品 SKU**: 共 **{len(unique_skus)}** 款",
                                f"**SKU 列表**: `{', '.join(unique_skus[:10])}{'...' if len(unique_skus)>10 else ''}`",
                                "---",
                                "📊 **【先问后干】默认推荐上架策略**：",
                                f"• **实售价格**: **{def_m} 倍实售**（划线标价 {def_m*2} 倍，立享 50% 官方大促折）",
                                f"• **现货库存**: **{def_s} 件**（莫斯科1仓现货秒级注入）",
                                "---",
                                "👉 **请回复确认或指定自定义策略**：",
                                "1. 发送「**确认**」或「**直接上架**」：按默认 6 倍实售/5件现货立即执行；",
                                "2. 或发送「**3倍**」、「**5倍 10库存**」：按您指定的策略立即上架！"
                            ]
                            send_feishu_card(chat_id, f"📄 从表格提取到 {len(unique_skus)} 款待上架商品，请确认策略", ask_lines, color="blue", open_id=open_id)
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
    print(" 启动飞书 WebSocket 长连接客户端 (无需公网 IP / 免穿透) [v5.0] ")
    print(f" App ID: {FEISHU_APP_ID}")
    print(" 核心技能同步: 6倍实售/50%大促/5件库存/形态推导/一机一码/收银台(¥600/店)")
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
