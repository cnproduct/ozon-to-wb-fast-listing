# -*- coding: utf-8 -*-
"""
==============================================================================
Wildberries 多群多租户店铺路由管理器 (Store Routing & Binding Manager)
==============================================================================
核心职责：
1. 维护各飞书群聊 (chat_id) 与 Wildberries 目标店铺的独立映射档案 (chat_stores.json)
2. 依据当前消息的 chat_id 毫秒级路由至对应的 WB Token、履约仓库与定价库存策略
3. 支持自然语言指令在飞书群/私聊内秒级绑定、状态查询、仓库动态验真与解绑重置
4. 严格隔离各群数据与店铺资产，确保客户A与客户B互不串店、互不可见
==============================================================================
"""

import os
import re
import json
import base64
import datetime
from typing import Dict, Any, Tuple, List, Optional
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
BINDINGS_FILE = os.path.join(WORKSPACE_DIR, 'chat_stores.json')

def decode_jwt_expiry(token: str) -> str:
    """解析 WB JWT 令牌中的到期时间与组织信息 (免第三方依赖)"""
    try:
        parts = token.strip().split('.')
        if len(parts) >= 2:
            payload = parts[1]
            payload += '=' * (-len(payload) % 4)
            data = json.loads(base64.b64decode(payload).decode('utf-8'))
            if 'exp' in data:
                dt = datetime.datetime.fromtimestamp(data['exp'])
                return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
    return "未知"

class StoreManager:
    def __init__(self):
        self.bindings_path = BINDINGS_FILE

    def get_default_config(self) -> Dict[str, Any]:
        """获取全局默认兜底店铺配置 (来自 config.json)"""
        candidates = [
            os.path.join(WORKSPACE_DIR, 'config.json'),
            os.path.join(SCRIPT_DIR, 'config.json'),
            os.path.join(os.getcwd(), 'config.json')
        ]
        cfg = {}
        for c in candidates:
            if os.path.exists(c):
                try:
                    with open(c, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                        break
                except Exception:
                    pass
        return {
            "store_name": cfg.get("store_name", "RR007 (默认全局店铺)"),
            "wb_api_token": (cfg.get("wb_api_token") or os.getenv("WB_API_TOKEN") or "").strip(),
            "wb_warehouse_id": int(cfg.get("wb_warehouse_id") or os.getenv("WB_WAREHOUSE_ID") or 2200658),
            "warehouse_name": cfg.get("warehouse_name", "莫斯科1仓"),
            "default_multiplier": float(cfg.get("default_multiplier", 5.0)),
            "default_discount": int(cfg.get("default_discount", 50)),
            "default_stock": int(cfg.get("default_stock", 10)),
            "operator": cfg.get("operator", "程智鹏"),
            "owner": cfg.get("owner", "许惹人"),
            "is_custom_binding": False
        }

    def load_bindings(self) -> Dict[str, Dict[str, Any]]:
        """加载所有群聊专属绑定字典 {chat_id: store_config}"""
        if not os.path.exists(self.bindings_path):
            return {}
        try:
            with open(self.bindings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] 读取 chat_stores.json 异常: {e}")
            return {}

    def save_bindings(self, bindings: Dict[str, Dict[str, Any]]) -> bool:
        """持久化保存群绑定信息"""
        try:
            with open(self.bindings_path, 'w', encoding='utf-8') as f:
                json.dump(bindings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[-] 保存 chat_stores.json 异常: {e}")
            return False

    def get_store_for_chat(self, chat_id: str) -> Dict[str, Any]:
        """根据当前消息的 chat_id 智能检索绑定的店铺信息，未绑定则无缝回退到默认全局店铺"""
        if not chat_id:
            return self.get_default_config()

        bindings = self.load_bindings()
        if chat_id in bindings:
            store = dict(bindings[chat_id])
            store["is_custom_binding"] = True
            return store

        return self.get_default_config()

    def verify_wb_token(self, token: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """在线验真 WB Token 合法性，并获取可用履约仓库列表"""
        clean_token = token.strip()
        if not clean_token:
            return False, "API 令牌为空", []

        url = "https://marketplace-api.wildberries.ru/api/v3/warehouses"
        headers = {
            "Authorization": clean_token,
            "Content-Type": "application/json"
        }
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200:
                wh_list = r.json()
                if isinstance(wh_list, list):
                    return True, "验证通过", wh_list
                return True, "验证通过", []
            elif r.status_code == 401:
                return False, "WB 官方拒绝访问 (401 Unauthorized)，API Token 无效或已过期", []
            else:
                return False, f"WB 官方接口响应异常 (HTTP {r.status_code}): {r.text[:100]}", []
        except requests.exceptions.RequestException as e:
            return False, f"网络请求超时或异常: {e}", []

    def bind_store(self, chat_id: str, store_name: str, token: str, 
                   warehouse_id: Optional[int] = None, multiplier: float = 5.0, 
                   discount: int = 50, stock: int = 10, bound_by: str = "") -> Tuple[bool, str, Dict[str, Any]]:
        """执行群绑定操作，自动包含验真、智能选仓与数据持久化"""
        if not chat_id:
            return False, "缺少有效的 chat_id", {}

        clean_token = token.strip()
        ok, msg, warehouses = self.verify_wb_token(clean_token)
        if not ok:
            return False, f"❌ 绑定失败：{msg}", {}

        # 智能解析或校验仓库
        target_wh_id = warehouse_id
        target_wh_name = "未命名仓库"

        if warehouses:
            if target_wh_id:
                # 检查指定的 warehouse_id 是否存在
                matched = [w for w in warehouses if int(w.get("id", 0)) == int(target_wh_id)]
                if matched:
                    target_wh_name = matched[0].get("name", f"仓库 {target_wh_id}")
                else:
                    target_wh_name = f"指定仓库 ({target_wh_id})"
            else:
                # 优先挑选含有 '莫斯科' 的仓库，否则选首个有效仓库
                moscow_wh = [w for w in warehouses if "москв" in w.get("name", "").lower() or "莫斯科" in w.get("name", "")]
                chosen = moscow_wh[0] if moscow_wh else warehouses[0]
                target_wh_id = int(chosen.get("id"))
                target_wh_name = chosen.get("name", "首选仓库")
        else:
            target_wh_id = target_wh_id or 2200658
            target_wh_name = "默认仓库"

        exp_time = decode_jwt_expiry(clean_token)

        store_record = {
            "chat_id": chat_id,
            "store_name": store_name.strip() or f"WB店铺-{target_wh_id}",
            "wb_api_token": clean_token,
            "wb_warehouse_id": target_wh_id,
            "warehouse_name": target_wh_name,
            "default_multiplier": float(multiplier),
            "default_discount": int(discount),
            "default_stock": int(stock),
            "token_expiry": exp_time,
            "bound_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bound_by": bound_by
        }

        bindings = self.load_bindings()
        bindings[chat_id] = store_record
        if self.save_bindings(bindings):
            succ_msg = (
                f"✅ **本群已成功绑定专属店铺【{store_record['store_name']}】！**\n\n"
                f"🏢 **店铺简称**: `{store_record['store_name']}`\n"
                f"📦 **履约仓库**: `{target_wh_name}` (ID: `{target_wh_id}`)\n"
                f"🔑 **Token 状态**: `有效 (到期: {exp_time})`\n"
                f"📈 **默认策略**: `{multiplier}倍售价` | `{discount}%大促折` | `{stock}件现货`\n"
                f"🔒 **安全隔离**: 本群成员发送的所有 SKU 均自动上架至该专属店铺，与其他群 100% 物理隔离！"
            )
            return True, succ_msg, store_record
        else:
            return False, "❌ 保存绑定配置失败，请检查文件系统写权限。", {}

    def unbind_store(self, chat_id: str) -> Tuple[bool, str]:
        """解绑当前群的专属店铺，回退到全局默认配置"""
        bindings = self.load_bindings()
        if chat_id in bindings:
            removed = bindings.pop(chat_id)
            if self.save_bindings(bindings):
                return True, f"✅ 已成功解绑当前群的专属店铺【{removed.get('store_name')}】！后续上架将使用全局默认配置。"
            return False, "❌ 解绑失败：无法更新存储文件。"
        return False, "ℹ️ 当前群尚未绑定专属店铺，目前使用的是系统默认店铺配置。"

    def parse_binding_command(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        灵活解析用户输入的绑定店铺文本指令
        支持格式：
        1. 键值对式：
           绑定店铺 店铺简称：RR008 API令牌：eyJ... 仓库ID：2200658 售价倍数：4.5
        2. 快捷简短式：
           绑定店铺 RR008 eyJhbGciOi... 2200658 4.5倍 50折 10库存
        """
        text = raw_text.strip()
        if not (text.startswith("绑定店铺") or text.startswith("+店铺") or text.startswith("绑定")):
            return None

        # 剥离前缀
        body = re.sub(r"^(?:绑定店铺|[\+]店铺|绑定)[:：\s]*", "", text).strip()
        if not body:
            return {}  # 用户仅发送了 "绑定店铺"，用于触发向导

        result = {
            "store_name": "",
            "token": "",
            "warehouse_id": None,
            "multiplier": 5.0,
            "discount": 50,
            "stock": 10
        }

        # 1. 提取 JWT 令牌 (以 eyJ 开头的高强度特征串)
        jwt_match = re.search(r'(eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]+)', body)
        if jwt_match:
            result["token"] = jwt_match.group(1).strip()
            # 在剩余文本中移除 token 以免干扰其他字段匹配
            body_without_token = body.replace(jwt_match.group(1), " ")
        else:
            # 兼容非标准 token
            token_match = re.search(r'(?:token|令牌|密钥|key)[:：\s]+([^\s\n]+)', body, re.IGNORECASE)
            if token_match:
                result["token"] = token_match.group(1).strip()
                body_without_token = body.replace(token_match.group(0), " ")
            else:
                body_without_token = body

        # 2. 提取店铺名称
        name_match = re.search(r'(?:店铺|简称|名称|store)[:：\s]+([^\s,，\n]+)', body_without_token, re.IGNORECASE)
        if name_match:
            result["store_name"] = name_match.group(1).strip()
        else:
            # 取第一段非数字作为名称
            parts = [p.strip() for p in body_without_token.split() if p.strip()]
            for p in parts:
                if not re.match(r'^\d+$', p) and '倍' not in p and '折' not in p and '库存' not in p:
                    result["store_name"] = p
                    break

        # 3. 提取仓库 ID (6~8 位纯数字)
        wh_match = re.search(r'(?:仓库|warehouse|仓|wh)[:：\s]*(\d{5,8})', body_without_token, re.IGNORECASE)
        if wh_match:
            result["warehouse_id"] = int(wh_match.group(1))
        else:
            pure_numbers = re.findall(r'(?<!\d)\d{5,8}(?!\d)', body_without_token)
            if pure_numbers:
                result["warehouse_id"] = int(pure_numbers[0])

        # 4. 提取倍数、折扣、库存
        m_match = re.search(r'(\d+(?:\.\d+)?)\s*倍', body_without_token)
        if m_match:
            result["multiplier"] = float(m_match.group(1))

        d_match = re.search(r'(\d+)\s*(?:折|%)', body_without_token)
        if d_match:
            v = int(d_match.group(1))
            result["discount"] = v * 10 if v <= 9 else v

        s_match = re.search(r'(?:库存|现货)[:：\s]*(\d+)|(\d+)\s*(?:件|个|库存)', body_without_token)
        if s_match:
            s_val = s_match.group(1) or s_match.group(2)
            if s_val:
                result["stock"] = int(s_val)

        return result

store_manager = StoreManager()
