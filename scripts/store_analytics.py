# -*- coding: utf-8 -*-
"""
==============================================================================
Wildberries 跨境电商智能运营问答与数据中台 (Store Operations & Analytics Copilot)
==============================================================================
涵盖跨境卖家 5 大核心运营域：
1. 业绩与销售大盘 (今日销量/销售额/出单统计/近7天爆款)
2. 订单履约与物流 (FBS 待发货紧急订单/发货截止倒计时/退货情况)
3. 现货库存与断货预警 (各仓在库盘点/低库存预警/补货清单)
4. 卡片健康与上架排查 (商品在售总数/审核被拒原因/单个 SKU 前台诊断)
5. 跨境策略与利润核算 (单品净利润秒测/类目佣金/罚款规避/防封必读)
==============================================================================
"""

import os
import re
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)

class StoreAnalytics:
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False

    def _headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": token.strip(),
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    # ================= 1. 销售大盘与出单统计 =================
    def get_sales_report(self, token: str, days: int = 1) -> Dict[str, Any]:
        """查询店铺指定天数内的销售流水与订单趋势 (今日/近7天/近30天)"""
        if not token:
            return {"error": "未配置有效的 API 密钥"}

        date_from = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        headers = self._headers(token)

        sales_url = f"https://statistics-api.wildberries.ru/api/v1/supplier/sales?dateFrom={date_from}"
        orders_url = f"https://statistics-api.wildberries.ru/api/v1/supplier/orders?dateFrom={date_from}"

        res = {
            "days": days,
            "order_count": 0,
            "order_amount": 0.0,
            "sale_count": 0,
            "sale_amount": 0.0,
            "cancel_count": 0,
            "top_products": []
        }

        try:
            # 抓取订单数据
            r_ord = self.session.get(orders_url, headers=headers, timeout=12)
            if r_ord.status_code == 200:
                orders = r_ord.json()
                if isinstance(orders, list):
                    res["order_count"] = len(orders)
                    for o in orders:
                        price = float(o.get("priceWithDisc", 0) or o.get("totalPrice", 0))
                        res["order_amount"] += price
                        if o.get("isCancel"):
                            res["cancel_count"] += 1
            
            # 抓取真实确认的销售流水
            r_sale = self.session.get(sales_url, headers=headers, timeout=12)
            if r_sale.status_code == 200:
                sales = r_sale.json()
                if isinstance(sales, list):
                    res["sale_count"] = len(sales)
                    product_counter = {}
                    for s in sales:
                        res["sale_amount"] += float(s.get("forPay", 0) or s.get("priceWithDisc", 0))
                        nm = str(s.get("nmId", "未知"))
                        title = s.get("subject", nm)
                        product_counter[nm] = product_counter.get(nm, {"title": title, "count": 0, "amount": 0.0})
                        product_counter[nm]["count"] += 1
                        product_counter[nm]["amount"] += float(s.get("forPay", 0))

                    sorted_p = sorted(product_counter.values(), key=lambda x: x["count"], reverse=True)
                    res["top_products"] = sorted_p[:5]

        except Exception as e:
            res["error"] = str(e)

        return res

    # ================= 2. FBS 待发货订单与履约紧急预警 =================
    def get_pending_orders(self, token: str) -> Dict[str, Any]:
        """查询 FBS 模式下待发货新订单 (严防超时被 WB 处以 50% 罚款)"""
        if not token:
            return {"error": "未配置有效的 API 密钥"}

        url = "https://marketplace-api.wildberries.ru/api/v3/orders/new"
        headers = self._headers(token)
        try:
            r = self.session.get(url, headers=headers, timeout=12)
            if r.status_code == 200:
                data = r.json()
                orders = data.get("orders", [])
                return {
                    "count": len(orders),
                    "orders": orders[:10]
                }
            return {"error": f"接口返回错误 (HTTP {r.status_code}): {r.text[:100]}"}
        except Exception as e:
            return {"error": str(e)}

    # ================= 3. 在售卡片健康度与审核驳回检查 =================
    def get_cards_health(self, token: str) -> Dict[str, Any]:
        """查询商品卡片总量、在线售卖数与审核异常列表"""
        if not token:
            return {"error": "未配置有效的 API 密钥"}

        headers = self._headers(token)
        res = {
            "total_cards": 0,
            "with_photo_count": 0,
            "error_cards": []
        }

        # 1. 统计卡片列表
        try:
            list_url = "https://content-api.wildberries.ru/content/v2/get/cards/list"
            payload = {"settings": {"cursor": {"limit": 100}, "filter": {"withPhoto": -1}}}
            r = self.session.post(list_url, headers=headers, json=payload, timeout=12)
            if r.status_code == 200:
                data = r.json()
                cards = data.get("cards", [])
                res["total_cards"] = len(cards)
                res["with_photo_count"] = sum(1 for c in cards if c.get("photos"))
        except Exception:
            pass

        # 2. 查询卡片创建失败/被拒列表
        try:
            err_url = "https://content-api.wildberries.ru/content/v2/cards/error/list"
            r_err = self.session.get(err_url, headers=headers, timeout=12)
            if r_err.status_code == 200:
                errors = r_err.json().get("data", [])
                for it in errors[:5]:
                    res["error_cards"].append({
                        "vendorCode": it.get("vendorCode", "未知"),
                        "errors": it.get("errors", ["未知异常"])
                    })
        except Exception:
            pass

        return res

    # ================= 4. 本地与云端在库库存盘点 =================
    def get_inventory_summary(self, token: str, warehouse_id: int) -> Dict[str, Any]:
        """统计在库商品总数、备货总量及低库存 (<5件) 预警商品"""
        json_path = os.path.join(WORKSPACE_DIR, 'products.json')
        items = []
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    items = json.load(f)
            except Exception:
                pass

        total_skus = len(items)
        total_units = sum(int(it.get('stock') or 0) for it in items)
        low_stock_items = [it for it in items if int(it.get('stock') or 0) < 5 and it.get('nmID')]

        return {
            "total_skus": total_skus,
            "total_units": total_units,
            "low_stock_count": len(low_stock_items),
            "low_stock_list": [
                f"{it.get('title', '')[:20]}... (SKU: {it.get('sku')}, 仅剩 {it.get('stock') if it.get('stock') is not None else 0} 件)"
                for it in low_stock_items[:5]
            ]
        }

    # ================= 5. 跨单品前台健康度即时诊断 =================
    def lookup_sku(self, sku_or_nmid: str) -> Optional[Dict[str, Any]]:
        """在本地已上架知识库与 WB 平台中检索指定 SKU / nmID 的详细档案"""
        json_path = os.path.join(WORKSPACE_DIR, 'products.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    items = json.load(f)
                    for it in items:
                        if str(it.get('sku')) == str(sku_or_nmid) or str(it.get('nmID')) == str(sku_or_nmid):
                            return it
            except Exception:
                pass
        return None

    # ================= 6. 跨境利润测算器 =================
    def calculate_profit(self, ozon_price: float, multiplier: float = 4.5, 
                         commission_rate: float = 0.20, logistics_rub: float = 350.0) -> Dict[str, Any]:
        """
        精确测算单品到手净利润：
        售价 = Ozon进货成本 × 乘数
        官方佣金 = 实售价 × 平台佣金率 (通常服装 19%~21%)
        跨境干线+落地配运费 = 预估 350 卢布/单
        """
        target_sell = round(ozon_price * multiplier)
        commission = round(target_sell * commission_rate)
        cogs = round(ozon_price)
        net_rub = round(target_sell - cogs - commission - logistics_rub)
        margin = round((net_rub / target_sell) * 100, 1) if target_sell > 0 else 0
        net_cny = round(net_rub * 0.078, 1)  # 汇率参考约 1 RUB ≈ 0.078 CNY

        return {
            "ozon_cost_rub": cogs,
            "target_sell_rub": target_sell,
            "commission_rub": commission,
            "logistics_rub": logistics_rub,
            "net_profit_rub": net_rub,
            "net_profit_cny": net_cny,
            "margin_percent": margin
        }

    # ================= 7. 智能运营意图理解与问答中枢 =================
    def handle_operations_query(self, raw_text: str, store_cfg: Dict[str, Any]) -> Optional[Tuple[str, List[str], str]]:
        """
        理解用户意图并返回 (标题, 结构化内容行, 卡片颜色)
        如果命中运营意图则返回，未命中返回 None
        """
        text = raw_text.strip().lower()
        token = store_cfg.get("wb_api_token", "")
        wh_id = store_cfg.get("wb_warehouse_id", 2200658)
        store_name = store_cfg.get("store_name", "默认店铺")

        # 如果包含明显的“上架”操作意图（且不是问“上架了多少/上架总数”），直接放行给上架引擎，绝不拦截！
        if "上架" in text and not any(q in text for q in ["上架了多少", "上架总数", "上架数量", "上架进度"]):
            return None

        # ---------------- 场景 A: 销量与业绩统计 ----------------
        if any(w in text for w in ["销量", "销售额", "出单", "卖了多少", "今天卖了", "业绩", "今日数据"]):
            days = 7 if any(w in text for w in ["周", "7天", "近七天"]) else (30 if any(w in text for w in ["月", "30天"]) else 1)
            time_label = "今日" if days == 1 else (f"近 {days} 天")
            
            rep = self.get_sales_report(token, days=days)
            if "error" in rep:
                return "📊 销量与业绩查询受阻", [f"⚠️ 无法获取店铺【{store_name}】的销售数据：", f"`{rep['error']}`"], "red"

            lines = [
                f"**统计周期**: `{time_label}` | **目标店铺**: `{store_name}`",
                f"---",
                f"📦 **买家下单单数**: **{rep['order_count']} 单**",
                f"💰 **下单预估总额**: **{rep['order_amount']:.2f} ₽**",
                f"✅ **已结算销售额**: **{rep['sale_amount']:.2f} ₽** (实售 {rep['sale_count']} 件)",
                f"⚠️ **买家取消单数**: `{rep['cancel_count']} 单`"
            ]
            if rep["top_products"]:
                lines.append("---")
                lines.append("🔥 **热销爆款排行**:")
                for idx, p in enumerate(rep["top_products"], 1):
                    lines.append(f"{idx}. {p['title']} (销量: `{p['count']}件` / `{p['amount']:.0f}₽`)")
            else:
                lines.append("---")
                lines.append("💡 *提示：近期暂无新出单成交记录，可增加主推高性价比货盘上架！*")

            return f"📈 店铺销售业绩报告 ({time_label})", lines, "green" if rep['order_count'] > 0 else "blue"

        # ---------------- 场景 B: 待发货与物流履约 ----------------
        if any(w in text for w in ["待发货", "新订单", "有订单吗", "发货截止", "物流时效"]):
            orders_res = self.get_pending_orders(token)
            if "error" in orders_res:
                return "🚚 待发货订单查询", [f"⚠️ 获取店铺【{store_name}】待发货订单失败：", f"`{orders_res['error']}`"], "red"

            cnt = orders_res.get("count", 0)
            if cnt == 0:
                lines = [
                    f"**目标店铺**: `{store_name}` (FBS 销售模式)",
                    "---",
                    "🎉 **目前没有任何待发货订单！** 所有履约均已清零，运营状态极佳！",
                    "💡 *当有新买家下单时，机器人会自动收到提醒，请保持关注。*"
                ]
                return "🚚 FBS 待发货实时监控", lines, "green"
            else:
                lines = [
                    f"**目标店铺**: `{store_name}`",
                    f"⚠️ **加急提醒**: 目前共有 **{cnt} 个待发货订单** 需尽快履约！",
                    "---",
                    "⚡ **履约合规红线**：Wildberries FBS 模式要求在 **56 小时内** 完成交运扫码，超时将被处以 **50% 货值违约罚款**！",
                    "---",
                    "📋 **待处理订单列表**:"
                ]
                for o in orders_res.get("orders", []):
                    lines.append(f"• 订单号: `{o.get('id')}` | 下单时间: `{o.get('createdAt', '')[:16]}` | 货号: `{o.get('article', '')}`")
                lines.append("---")
                lines.append("👉 请登录 WB 卖家后台【Маркетплейс -> Сборочные задания】打印配货贴条面单。")
                return f"🚨 待发货紧急提醒 ({cnt} 单待处理)", lines, "orange"

        # ---------------- 场景 C: 库存盘点与缺货预警 ----------------
        is_stock_query = (
            any(w in text for w in ["查库存", "查看库存", "剩余库存", "看库存", "库存盘点", "缺货预警", "补货清单", "断货", "缺货", "有多少库存"])
            or text in ["库存", "店铺库存", "现货库存", "剩余", "在库库存"]
        )
        if is_stock_query and not any(op in text for op in ["设置", "改", "改为", "修改", "倍", "折", "*", "售价"]):
            inv = self.get_inventory_summary(token, wh_id)
            lines = [
                f"**目标店铺**: `{store_name}` | **履约仓 ID**: `{wh_id}`",
                "---",
                f"📊 **在库有效商品总数**: **{inv['total_skus']} 款**",
                f"📦 **莫斯科仓在售总件数**: **{inv['total_units']} 件**",
                f"⚠️ **低库存预警商品 (<5件)**: **{inv['low_stock_count']} 款**"
            ]
            if inv["low_stock_list"]:
                lines.append("---")
                lines.append("🔻 **紧缺需补货清单**:")
                for item_str in inv["low_stock_list"]:
                    lines.append(f"• {item_str}")
                lines.append("💡 *提示：可直接在群内发送商品新库存，例如发送 `724574142 库存设置50` 一键更新！*")
            else:
                lines.append("---")
                lines.append("✅ **全量商品库存健康**，暂无断货风险！")

            return "📦 店铺现货库存盘点", lines, "blue"

        # ---------------- 场景 D: 商品上架总数与卡片审核 ----------------
        if any(w in text for w in ["在售", "上架总数", "卡片", "审核", "被拒", "下架", "上架了多少", "商品数"]):
            health = self.get_cards_health(token)
            lines = [
                f"**目标店铺**: `{store_name}`",
                "---",
                f"🗂️ **店铺卡片总数**: **{health['total_cards']} 款**",
                f"🖼️ **高清画廊合规商品**: **{health['with_photo_count']} 款**",
                f"❌ **审核异常/驳回商品**: **{len(health['error_cards'])} 款**"
            ]
            if health["error_cards"]:
                lines.append("---")
                lines.append("⚠️ **被驳回商品排查**:")
                for err in health["error_cards"]:
                    err_msg = ", ".join(err["errors"]) if isinstance(err["errors"], list) else str(err["errors"])
                    lines.append(f"• 货号 `{err['vendorCode']}`: {err_msg[:60]}")
                lines.append("💡 *常见被拒原因：标题超 60 字符、主图分辨率低于 700x900、或未通过白牌脱敏。*")
            else:
                lines.append("---")
                lines.append("✅ **全部已创建卡片状态健康，无驳回记录！**")

            return "🛡️ 商品上架与卡片健康审计", lines, "blue"

        # ---------------- 场景 E: 查特定 SKU / nmID ----------------
        sku_query_match = re.search(r'(?:查|搜|查询|sku|nmid)[:：\s]*(\d{7,12})', text)
        if sku_query_match or (text.isdigit() and len(text) in [7, 8, 9, 10, 11, 12] and "上架" not in text):
            target_sku = sku_query_match.group(1) if sku_query_match else text
            found = self.lookup_sku(target_sku)
            if found:
                lines = [
                    f"**商品俄文标题**: {found.get('title')}",
                    f"**Ozon 原 SKU**: `{found.get('sku')}`",
                    f"**商家内部货号**: `{found.get('vendorCode')}`",
                    f"**WB 官方 nmID**: [{found.get('nmID')}](https://www.wildberries.ru/catalog/{found.get('nmID')}/detail.aspx)",
                    f"**官方条形码**: `{found.get('barcode')}`",
                    f"---",
                    f"💰 **实售价格**: **{found.get('sell_price', '未配置')} ₽** (划线标价 {found.get('strike_price', '未配置')} ₽)",
                    f"📦 **在库现货**: **{found.get('stock', '0')} 件** (莫斯科1仓)",
                    f"📐 **规格重量**: {found.get('length_cm', 10)}×{found.get('width_cm', 10)}×{found.get('height_cm', 5)} cm | 毛重 {found.get('weight_g', 500)}g",
                    f"---",
                    f"🔗 [点击直接在 Wildberries 官网查看前台在售详情](https://www.wildberries.ru/catalog/{found.get('nmID')}/detail.aspx)"
                ]
                return f"🔍 商品档案查询 (SKU: {target_sku})", lines, "green"
            else:
                lines = [
                    f"⚠️ 在当前知识库中未找到 SKU 或 nmID 为 `{target_sku}` 的已上架记录。",
                    "---",
                    "💡 如需立即将该商品上架到当前店铺，直接在群内发送：",
                    f"`{target_sku} 上架，价格按售价*4.5倍，库存设置12`"
                ]
                return f"🔍 商品查询 (SKU: {target_sku})", lines, "orange"

        # ---------------- 场景 F: 单品利润测算器 ----------------
        profit_match = re.search(r'(?:利润|测算|算利润|利润计算|核算)[:：\s]*(\d+(?:\.\d+)?)', text)
        if profit_match:
            cost = float(profit_match.group(1))
            m = float(store_cfg.get("default_multiplier", 4.5))
            m_in = re.search(r'(\d+(?:\.\d+)?)\s*倍', text)
            if m_in:
                m = float(m_in.group(1))
            
            p = self.calculate_profit(cost, multiplier=m)
            lines = [
                f"**Ozon 进货成本**: `{p['ozon_cost_rub']} ₽` (约 ¥{p['ozon_cost_rub']*0.078:.1f})",
                f"**设定实售倍数**: `{m} 倍`",
                f"---",
                f"🏷️ **WB 买家实付价**: **{p['target_sell_rub']} ₽**",
                f"📉 **平台抽成 (约20%)**: -{p['commission_rub']} ₽",
                f"🚚 **跨境+尾程运费 (估)**: -{p['logistics_rub']} ₽",
                f"---",
                f"💰 **单品净到手利润**: **+{p['net_profit_rub']} ₽** (折合人民币 **¥{p['net_profit_cny']} 元**)",
                f"📈 **单品净利润率**: **{p['margin_percent']}%**",
                "---",
                "💡 *注：汇率参考 1 RUB ≈ 0.078 RMB；服装类目平均佣金在 19%~21% 浮动。*"
            ]
            return f"🧮 跨境电商单品利润测算 (进价: {cost}₽)", lines, "green"

        # ---------------- 场景 G: 跨境卖家常见运营问答知识库 ----------------
        # 1. 佣金与费率
        if any(w in text for w in ["佣金", "费率", "平台抽成", "扣点"]):
            lines = [
                "📊 **Wildberries 核心品类佣金参考表**：",
                "• **服装与鞋类 (Одежда / Обувь)**: **19% ~ 23%**",
                "• **儿童玩具与母婴 (Игрушки / Товары для детей)**: **15% ~ 18%**",
                "• **美妆与个护 (Красота)**: **14% ~ 17%**",
                "• **3C数码配件 (Электроника / Аксессуары)**: **12% ~ 15%**",
                "• **家居与日用品 (Товары для дома)**: **15% ~ 19%**",
                "---",
                "💡 *注：加入官方大促或使用官方仓储物流通常可享受 3%~5% 的官方佣金减免折优惠！*"
            ]
            return "💡 Wildberries 类目佣金费率指南", lines, "blue"

        # 2. 发货与罚款规则
        if any(w in text for w in ["罚款", "超时", "违约金", "封店", "处罚"]):
            lines = [
                "⚠️ **Wildberries 跨境卖家 4 大必须严防的违规红线**：",
                "1️⃣ **FBS 超时发货罚款**：未在 **56 小时内** 交付中转物流并扫描入库，平台处以 **该单货值 50% 的违约金**（最低 100 卢布）！",
                "2️⃣ **虚假发货/缺货取消**：卖家主动取消订单或填入虚假单号，处以 **商品价值 50% 罚款** 并降低店铺曝光权重！",
                "3️⃣ **知识产权侵权（《要约》第 9.2.3 条）**：无授权上架 Nike/Adidas/Disney 等国际品牌，单款罚款 **25,000 卢布** 并下架关店！",
                "4️⃣ **包裹尺寸虚报**：实际尺寸超过申报尺寸 20% 以上，平台加收 **双倍阶梯物流附加费**。",
                "---",
                "🛡️ *我们的机器人默认开启了【白牌自动脱敏】与【包装尺寸安全向下取整】，为您守住安全底线！*"
            ]
            return "🛡️ WB 跨境运营风控与罚款避坑规则", lines, "orange"

        # 3. 尺码选型建议
        if any(w in text for w in ["尺码", "服装尺码", "俄罗斯尺码"]):
            lines = [
                "👗 **俄罗斯服装鞋帽尺码对照与选品建议**：",
                "• **身材特征**：俄罗斯买家普遍体型高大、骨架大、手臂和下肢较长。",
                "• **选码习惯**：中国尺码 (CN) 偏小，通常需要比国内 **偏大 1~2 码** 进行标定！",
                "• **对应表**：",
                "  - 国内 S 码 ➔ 对应俄罗斯 40~42 (适合极瘦/青年)",
                "  - 国内 M 码 ➔ 对应俄罗斯 44",
                "  - 国内 L 码 ➔ 对应俄罗斯 46~48 (主力销量码)",
                "  - 国内 XL/2XL 码 ➔ 对应俄罗斯 50~52 (大促转化极高)",
                "---",
                "💡 *机器人在上架 T 恤时，默认自动为您匹配了俄罗斯标准俄码 (Российский размер: 50 / L)，转化率更高！*"
            ]
            return "📏 俄罗斯买家尺码与版型建议", lines, "blue"

        return None

store_analytics = StoreAnalytics()
