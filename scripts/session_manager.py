# -*- coding: utf-8 -*-
"""
==============================================================================
Antigravity 会话级商业授权门禁与 1:1 店铺隔离管理器 (Mode B: License Gatekeeper & Store Mutex)
==============================================================================
核心铁律：
1. 【零信任商业授权门禁 (Zero-Trust License Gatekeeper)】：
   - 任何新创建的 Antigravity 对话窗口默认处于未授权状态 (UNAUTHORIZED)。
   - 必须通过输入有效授权码 (License Key) 激活当前窗口后，方可启动极速上架引擎。
2. 【单窗口 1:1 店铺互斥锁定 (Store Mutex Lock)】：
   - 每一个 Antigravity 对话窗口只允许绑定一家 Wildberries 店铺。
   - 严禁在同一窗口内混绑 2 家及以上店铺，彻底消除商品串店与库存错乱隐患。
3. 【平滑更换店铺 (Store Switching)】：
   - 支持通过「切换店铺」或「解绑店铺」指令安全更换绑定的 WB 店铺，实时完成 API 验真与仓库更新。
==============================================================================
"""

import os
import sys
import re
import json
import uuid
import base64
import datetime
import argparse
import requests
from typing import Dict, Any, Tuple, List, Optional

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    from machine_fingerprint import get_machine_id
except ImportError:
    from scripts.machine_fingerprint import get_machine_id

try:
    from license_crypto import LicenseCrypto, LicenseCryptError, MachineMismatchError, LicenseSignatureError, LicenseExpiredError
except ImportError:
    from scripts.license_crypto import LicenseCrypto, LicenseCryptError, MachineMismatchError, LicenseSignatureError, LicenseExpiredError

try:
    from cloud_auth import CloudAuthClient
except ImportError:
    from scripts.cloud_auth import CloudAuthClient

REGISTRY_FILE = os.path.expanduser("~/.wb_session_registry.json")
MASTER_LICENSE_KEY = "LIC-MASTER-2026-VIP"

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

class SessionAuthorizationError(Exception):
    """会话未授权异常"""
    pass

class StoreMutexError(Exception):
    """店铺互斥冲突异常"""
    pass

class SessionManager:
    def __init__(self, registry_path: str = REGISTRY_FILE):
        self.registry_path = registry_path
        self._ensure_registry_init()

    def _ensure_registry_init(self):
        """确保会话注册表存在并初始化结构"""
        if not os.path.exists(self.registry_path):
            initial_data = {
                "master_key": MASTER_LICENSE_KEY,
                "licenses": {
                    MASTER_LICENSE_KEY: {
                        "name": "超级管理员永久授权 (Master VIP)",
                        "max_sessions": -1,
                        "expires_at": "2099-12-31 23:59:59",
                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "activated_sessions": []
                    }
                },
                "sessions": {}
            }
            # 如果存在本地默认 config.json，将其作为主窗口初始绑定
            workspace_config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.json'))
            active_conv = self.get_current_conversation_id()
            if os.path.exists(workspace_config_path) and active_conv:
                try:
                    with open(workspace_config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                    if cfg.get("wb_api_token"):
                        token = cfg.get("wb_api_token").strip()
                        initial_data["licenses"][MASTER_LICENSE_KEY]["activated_sessions"].append(active_conv)
                        initial_data["sessions"][active_conv] = {
                            "status": "AUTHORIZED",
                            "license_key": MASTER_LICENSE_KEY,
                            "activated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "bound_store": {
                                "store_name": cfg.get("store_name", "RR007"),
                                "wb_api_token": token,
                                "wb_warehouse_id": int(cfg.get("wb_warehouse_id", 2200658)),
                                "warehouse_name": cfg.get("warehouse_name", "莫斯科1仓"),
                                "default_multiplier": float(cfg.get("default_multiplier", 6.0)),
                                "default_discount": int(cfg.get("default_discount", 50)),
                                "default_stock": int(cfg.get("default_stock", 5)),
                                "store_currency": cfg.get("store_currency", "CNY"),
                                "token_expiry": decode_jwt_expiry(token),
                                "bound_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                        }
                except Exception:
                    pass
            self._save_registry(initial_data)

    def _load_registry(self) -> Dict[str, Any]:
        if not os.path.exists(self.registry_path):
            self._ensure_registry_init()
        try:
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] 读取注册表异常: {e}")
            return {"master_key": MASTER_LICENSE_KEY, "licenses": {}, "sessions": {}}

    def _save_registry(self, data: Dict[str, Any]) -> bool:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.registry_path)), exist_ok=True)
            with open(self.registry_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[-] 保存注册表异常: {e}")
            return False

    def get_current_conversation_id(self, override_id: Optional[str] = None) -> str:
        """获取当前 Antigravity 会话窗口 ID (支持环境变量、命令行、近期日志探测与 fallback)"""
        if override_id:
            return override_id.strip()
        env_cid = os.getenv("ANTIGRAVITY_CONVERSATION_ID") or os.getenv("CONVERSATION_ID")
        if env_cid:
            return env_cid.strip()
        
        # 尝试从 Antigravity brain 目录寻找最近更新的活跃 transcript
        brain_dir = os.path.expanduser("~/.gemini/antigravity/brain")
        if os.path.exists(brain_dir):
            try:
                candidates = []
                for entry in os.listdir(brain_dir):
                    t_path = os.path.join(brain_dir, entry, ".system_generated", "logs", "transcript.jsonl")
                    if os.path.exists(t_path):
                        mtime = os.path.getmtime(t_path)
                        candidates.append((mtime, entry))
                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    return candidates[0][1]
            except Exception:
                pass
        return "default-session"

    def probe_wb_token(self, token: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
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
            s = requests.Session()
            s.trust_env = False
            r = s.get(url, headers=headers, timeout=12)
            if r.status_code == 200:
                wh_list = r.json()
                if isinstance(wh_list, list):
                    return True, "验证通过", wh_list
                return True, "验证通过", []
            elif r.status_code == 401:
                return False, "WB 官方拒绝访问 (401 Unauthorized)，API Token 无效或已过期", []
            else:
                return False, f"WB 官方接口响应异常 (HTTP {r.status_code}): {r.text[:100]}", []
        except Exception as e:
            return False, f"网络请求异常: {e}", []

    def generate_license(self, name: str = "商业客户", max_sessions: int = 1, days: int = 365, machine_id: Optional[str] = None) -> Dict[str, Any]:
        """管理员使用 RSA-2048 签发商业防伪授权码 (支持绑定机器码一机一码)"""
        target_mid = machine_id.strip() if machine_id else get_machine_id()
        crypto = LicenseCrypto()
        lic_key = crypto.sign_license(machine_id=target_mid, customer_name=name, days=days, max_sessions=max_sessions)
        
        registry = self._load_registry()
        expires_at = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d 23:59:59") if days > 0 else "2099-12-31 23:59:59"
        lic_data = {
            "name": name,
            "machine_id": target_mid,
            "max_sessions": max_sessions,
            "expires_at": expires_at,
            "type": "RSA-PSS-SHA256",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "activated_sessions": []
        }
        registry.setdefault("licenses", {})[lic_key] = lic_data
        self._save_registry(registry)
        return {"license_key": lic_key, **lic_data}

    def activate_license(self, license_key: str, conversation_id: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """在当前会话窗口中激活商业授权 (支持 RSA 防伪验签与硬件机器码比对)"""
        cid = self.get_current_conversation_id(conversation_id)
        clean_key = license_key.strip()
        registry = self._load_registry()

        # 1. 优先走 RSA-2048 非对称数字验签与一机一码校验
        if clean_key.startswith("LIC-RSA-"):
            crypto = LicenseCrypto()
            try:
                payload = crypto.verify_license(clean_key)
            except LicenseCryptError as e:
                return False, f"❌ 商业授权激活失败：{e}", {}

            lic_info = {
                "name": payload.get("name", "商业客户"),
                "machine_id": payload.get("mid", "*"),
                "max_sessions": payload.get("max_s", 1),
                "expires_at": payload.get("exp", "unlimited"),
                "type": "RSA-HARDWARE-BOUND"
            }
        else:
            # 兼容管理员万能激活码或注册表旧码
            licenses = registry.get("licenses", {})
            if clean_key not in licenses and clean_key != MASTER_LICENSE_KEY:
                return False, f"❌ 授权码无效：未找到授权码【{clean_key}】，请核对或联系管理员。", {}
            lic_info = licenses.get(clean_key, {
                "name": "超级管理员主授权",
                "max_sessions": -1,
                "expires_at": "2099-12-31 23:59:59"
            })

        # 校验有效期
        expires_at = lic_info.get("expires_at", "")
        if expires_at and expires_at != "unlimited":
            try:
                exp_dt = datetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                if datetime.datetime.now() > exp_dt:
                    return False, f"❌ 授权码已过期：该授权已于 {expires_at} 到期，请续费或更换。", {}
            except Exception:
                pass

        # 校验并发窗口配额
        max_s = lic_info.get("max_sessions", 1)
        activated_list = lic_info.setdefault("activated_sessions", [])
        if cid not in activated_list:
            if max_s != -1 and len(activated_list) >= max_s:
                return False, f"❌ 激活窗口超限：该授权码最多仅允许激活 {max_s} 个窗口，已全部使用（当前使用中: {activated_list}）。", {}
            activated_list.append(cid)

        # 云端状态预检 (Cloudflare Workers 实时拦截已在线封禁的授权码)
        try:
            cloud_client = CloudAuthClient()
            if cloud_client.is_cloud_enabled():
                c_ok, c_status, c_data = cloud_client.verify_cloud_license(
                    license_key=clean_key,
                    machine_id=lic_info.get("machine_id", get_machine_id()),
                    conversation_id=cid
                )
                if not c_ok and c_status == "BANNED":
                    return False, f"❌ 授权码已被管理员远程在线封禁！\n封禁原因: {c_data.get('reason', '违规使用')}\n如有疑问请联系系统管理员。", {}
        except Exception:
            pass

        # 记录会话激活
        sessions = registry.setdefault("sessions", {})
        session_entry = sessions.get(cid, {})
        session_entry["status"] = "AUTHORIZED"
        session_entry["license_key"] = clean_key
        session_entry["license_name"] = lic_info.get("name", "商业授权")
        session_entry["machine_id"] = lic_info.get("machine_id", get_machine_id())
        session_entry["activated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sessions[cid] = session_entry

        self._save_registry(registry)
        succ_msg = (
            f"🎉 **商业授权激活成功！**\n\n"
            f"🔑 **授权类型**: `RSA-2048 非对称防伪硬件绑定`\n"
            f"👤 **授权对象**: `{lic_info.get('name')}`\n"
            f"💻 **绑定设备**: `{lic_info.get('machine_id', '当前设备')}`\n"
            f"⏳ **有效期至**: `{lic_info.get('expires_at')}`\n"
            f"🆔 **当前窗口**: `{cid}`\n\n"
            f"👉 下一步：请绑定当前窗口专属的 Wildberries 店铺：\n"
            f"`绑定店铺 店铺简称：我的店铺 API令牌：eyJ... 仓库ID：2200658 售价倍数：6.0`"
        )
        return True, succ_msg, session_entry

    def verify_session_authorized(self, conversation_id: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """校验当前会话是否具备有效授权，若为 RSA 硬件绑定码，穿透强校验硬件指纹防篡改与跨机白嫖"""
        cid = self.get_current_conversation_id(conversation_id)
        registry = self._load_registry()
        session_entry = registry.get("sessions", {}).get(cid)
        if not session_entry or session_entry.get("status") != "AUTHORIZED":
            cashier_url = f"https://wb-auth-gateway.cnproduct.workers.dev/pay?cid={cid}"
            unauth_msg = (
                f"\n"
                f"================================================================================\n"
                f"🛑【商业授权拦截】当前 Antigravity 聊天窗口未获得商业授权！\n"
                f"================================================================================\n"
                f"🆔 当前会话窗口 ID : {cid}\n"
                f"🔒 授权状态         : 未授权 (UNAUTHORIZED)\n\n"
                f"🚀 欢迎使用 Wildberries 极速智能搬家上架助手！\n\n"
                f"👉 **只需 1 步极简开通**：\n"
                f"   在当前对话框发送「获取授权码」，系统自动获取当前窗口 ID 并分发支付宝付款二维码！\n"
                f"   或直接点击在线收银台支付（¥600/店铺/年，支付当日起 365 天有效，一店一码 1:1 独立隔离）：\n"
                f"   🔗 {cashier_url}\n\n"
                f"⚡ **全自动智能流转闭环**：\n"
                f"   1️⃣ 支付宝扫码支付 600 元；\n"
                f"   2️⃣ 支付完成后系统秒级自动签发授权码并【自动激活当前窗口】；\n"
                f"   3️⃣ 激活后系统主动提示您绑定 Wildberries 目标店铺；\n"
                f"   4️⃣ 店铺绑定完成后，系统主动提示您提供 Ozon SKU，全自动全要素极速搬家上架！\n\n"
                f"💡 提示：多店铺卖家可在新窗口输入第 2 个授权码绑定第 2 家店铺，多窗多店并发独立运行！\n"
                f"📞 官方客服与授权咨询请联系管理员电话: 15959543210\n"
                f"================================================================================\n"
            )
            return False, unauth_msg, {}

        # 硬件指纹防伪复验：如果会话绑定的是 RSA 授权码，强制再次比对本机实际硬件指纹
        lic_key = session_entry.get("license_key", "")
        if lic_key.startswith("LIC-RSA-"):
            crypto = LicenseCrypto()
            try:
                crypto.verify_license(lic_key)
            except LicenseCryptError as e:
                # 授权被篡改或机器被更换
                session_entry["status"] = "UNAUTHORIZED"
                self._save_registry(registry)
                return False, f"🛑【硬件授权失效被阻断】{e}", {}

        # 云端在线验真与毫秒级封禁核验 (Cloudflare Workers 联动)
        try:
            c_client = CloudAuthClient()
            if c_client.is_cloud_enabled():
                c_ok, c_status, c_data = c_client.verify_cloud_license(
                    license_key=lic_key,
                    machine_id=session_entry.get("machine_id", get_machine_id()),
                    conversation_id=cid
                )
                if not c_ok and c_status == "BANNED":
                    session_entry["status"] = "UNAUTHORIZED"
                    session_entry["ban_reason"] = c_data.get("reason", "管理员云端远程封禁")
                    self._save_registry(registry)
                    ban_msg = (
                        f"\n"
                        f"================================================================================\n"
                        f"🚫【云端远程封禁阻断】此授权码已被管理员在线封禁！\n"
                        f"================================================================================\n"
                        f"🔑 授权码   : {lic_key}\n"
                        f"🛑 封禁原因 : {session_entry.get('ban_reason')}\n"
                        f"⏰ 拦截时间 : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"⚠️ 当前会话权限已被瞬间锁死。如有疑问，请联系系统管理员处理。\n"
                        f"================================================================================\n"
                    )
                    return False, ban_msg, {}
        except Exception:
            pass

        return True, "已授权", session_entry

    def bind_store(self, store_name: str, token: str, warehouse_id: Optional[int] = None,
                   multiplier: float = 6.0, discount: int = 50, stock: int = 5,
                   currency: str = "CNY", conversation_id: Optional[str] = None,
                   force: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        """
        为当前会话窗口绑定店铺 (严格保证 1 窗口 : 1 店铺)
        若已绑定店铺且 force=False，触发 StoreMutexError 阻断并提示切换方式
        """
        cid = self.get_current_conversation_id(conversation_id)
        
        # 1. 检查授权门禁
        auth_ok, auth_msg, session_entry = self.verify_session_authorized(cid)
        if not auth_ok:
            return False, auth_msg, {}

        registry = self._load_registry()
        sessions = registry.setdefault("sessions", {})
        curr_session = sessions.get(cid, {})
        existing_store = curr_session.get("bound_store")
        lic_key = curr_session.get("license_key", "")
        is_admin = (lic_key == MASTER_LICENSE_KEY)

        # 2. 单窗口换店次数上限检查 (商业客户最多允许换店 1 次，管理员不受限)
        is_store_change = bool((force and existing_store) or curr_session.get("had_bound_store", False))
        
        if is_store_change and not is_admin:
            current_switches = curr_session.get("switch_count", 0)
            if current_switches >= 1:
                locked_store_name = existing_store.get('store_name') if existing_store else curr_session.get('last_store_name', '已绑店铺')
                limit_msg = (
                    f"\n"
                    f"================================================================================\n"
                    f"🛑【换店配额已耗尽】当前会话窗口已达到店铺更换上限 (最多 1 次)！\n"
                    f"================================================================================\n"
                    f"🏢 当前锁定店铺 : {locked_store_name}\n"
                    f"🔒 换店配额状态 : 1 / 1 (已用尽，本窗口已永久锁定)\n\n"
                    f"⚠️ 安全与商业授权铁律：\n"
                    f"   为防止店铺数据混淆串店与保障商业授权合规，每个会话窗口仅提供 1 次更换店铺的容错机会。\n"
                    f"   当前会话窗口已永久锁定至店铺【{locked_store_name}】，禁止再次更换为【{store_name}】！\n\n"
                    f"👉 如需管理新店铺【{store_name}】，请在 Antigravity 中开启全新的聊天窗口并获取专属授权。\n"
                    f"================================================================================\n"
                )
                return False, limit_msg, existing_store or {}

        # 2.1 单窗口单店铺互斥检查 (Store Mutex Lock)
        if existing_store and not force:
            used_sw = curr_session.get('switch_count', 0)
            sw_tip = "无限制 (超级管理员)" if is_admin else f"{used_sw}/1 ({'已用尽，本窗口无法再换店' if used_sw >= 1 else '剩余 1 次更换机会'})"
            mutex_msg = (
                f"\n"
                f"================================================================================\n"
                f"⚠️【店铺互斥安全锁】当前窗口已绑定店铺【{existing_store.get('store_name')}】！\n"
                f"================================================================================\n"
                f"🏢 已绑店铺 : {existing_store.get('store_name')}\n"
                f"📦 履约仓库 : {existing_store.get('warehouse_name')} (ID: {existing_store.get('wb_warehouse_id')})\n"
                f"🔑 令牌到期 : {existing_store.get('token_expiry')}\n"
                f"🔒 换店配额 : {sw_tip}\n\n"
                f"🔒 互斥铁律：\n"
                f"   每一个 Antigravity 对话窗口只允许绑定一家 Wildberries 店铺，严禁在同一窗口\n"
                f"   混绑 2 家及以上店铺，以防商品串店误传或库存错乱！\n\n"
                f"👉 如需将当前窗口切换到新店铺【{store_name}】，请使用明确的切换指令：\n"
                f"   切换店铺 店铺简称：{store_name} API令牌：{token[:15]}... 仓库ID：{warehouse_id or existing_store.get('wb_warehouse_id')}\n"
                f"================================================================================\n"
            )
            return False, mutex_msg, existing_store

        # 3. 在线验真 WB API Token
        clean_token = token.strip()
        ok, msg, warehouses = self.probe_wb_token(clean_token)
        if not ok:
            return False, f"❌ 绑定失败：{msg}", {}

        # 智能匹配仓库
        target_wh_id = warehouse_id
        target_wh_name = "未命名仓库"
        if warehouses:
            if target_wh_id:
                matched = [w for w in warehouses if int(w.get("id", 0)) == int(target_wh_id)]
                if matched:
                    target_wh_name = matched[0].get("name", f"仓库 {target_wh_id}")
                else:
                    target_wh_name = f"指定仓库 ({target_wh_id})"
            else:
                moscow_wh = [w for w in warehouses if "москв" in w.get("name", "").lower() or "莫斯科" in w.get("name", "")]
                chosen = moscow_wh[0] if moscow_wh else warehouses[0]
                target_wh_id = int(chosen.get("id"))
                target_wh_name = chosen.get("name", "首选仓库")
        else:
            target_wh_id = target_wh_id or 2200658
            target_wh_name = "莫斯科1仓"

        exp_time = decode_jwt_expiry(clean_token)
        store_record = {
            "store_name": store_name.strip() or f"WB店铺-{target_wh_id}",
            "wb_api_token": clean_token,
            "wb_warehouse_id": target_wh_id,
            "warehouse_name": target_wh_name,
            "default_multiplier": float(multiplier),
            "default_discount": int(discount),
            "default_stock": int(stock),
            "store_currency": currency,
            "token_expiry": exp_time,
            "bound_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 更新换店计数与状态
        if is_store_change and not is_admin:
            curr_session["switch_count"] = curr_session.get("switch_count", 0) + 1
        curr_session["had_bound_store"] = True
        curr_session["last_store_name"] = store_record["store_name"]
        curr_session["bound_store"] = store_record
        sessions[cid] = curr_session
        self._save_registry(registry)

        action_desc = "切换重绑" if force and existing_store else "绑定"
        switch_quota_tip = ""
        if not is_admin:
            used_switches = curr_session.get("switch_count", 0)
            if used_switches >= 1:
                switch_quota_tip = "\n🔒 **换店配额状态**: `1/1 (换店配额已用尽，本窗口已永久锁定该店铺)`"
            else:
                switch_quota_tip = "\n💡 **换店配额状态**: `0/1 (为防串店，本窗口享有最多 1 次更换店铺的机会)`"
        else:
            switch_quota_tip = "\n👑 **换店配额状态**: `无限制 (超级管理员特权)`"

        succ_msg = (
            f"✅ **当前会话窗口已成功{action_desc}专属店铺【{store_record['store_name']}】！**\n\n"
            f"🏢 **店铺简称**: `{store_record['store_name']}`\n"
            f"📦 **履约仓库**: `{target_wh_name}` (ID: `{target_wh_id}`)\n"
            f"🔑 **Token 状态**: `有效 (到期: {exp_time})`\n"
            f"💰 **结算货币**: `{currency}`\n"
            f"📈 **默认策略**: `{multiplier}倍实售` | `{discount}%大促折` | `{stock}件现货`\n"
            f"🔒 **单店互斥保证**: 本会话窗口仅对接该店铺，所有极速上架任务均在此店铺安全执行！"
            f"{switch_quota_tip}\n\n"
            f"👉 **下一步**：店铺已就绪！请直接发送 Ozon SKU 列表或 .txt 文本，全自动全要素搬家上架！"
        )
        return True, succ_msg, store_record

    def switch_store(self, store_name: str, token: str, warehouse_id: Optional[int] = None,
                     multiplier: float = 6.0, discount: int = 50, stock: int = 5,
                     currency: str = "CNY", conversation_id: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """更换当前会话窗口绑定的店铺 (强制覆盖旧绑定)"""
        return self.bind_store(store_name=store_name, token=token, warehouse_id=warehouse_id,
                               multiplier=multiplier, discount=discount, stock=stock,
                               currency=currency, conversation_id=conversation_id, force=True)

    def unbind_store(self, conversation_id: Optional[str] = None) -> Tuple[bool, str]:
        """解绑当前会话窗口的店铺，恢复至未绑定店铺状态 (保留授权状态)"""
        cid = self.get_current_conversation_id(conversation_id)
        registry = self._load_registry()
        sessions = registry.get("sessions", {})
        if cid in sessions and sessions[cid].get("bound_store"):
            old = sessions[cid].get("bound_store")
            lic_key = sessions[cid].get("license_key", "")
            is_admin = (lic_key == MASTER_LICENSE_KEY)
            
            # 若非管理员且换店次数已用尽，禁止解绑绕过
            if not is_admin and sessions[cid].get("switch_count", 0) >= 1:
                return False, (
                    f"🛑【禁止解绑】当前会话窗口已使用过换店配额 (1/1)，已永久锁定为店铺【{old.get('store_name')}】。\n"
                    f"如需绑定新店铺，请在 Antigravity 中开启全新的聊天窗口并获取授权。"
                )

            sessions[cid].pop("bound_store")
            if not is_admin:
                sessions[cid]["switch_count"] = sessions[cid].get("switch_count", 0) + 1
            self._save_registry(registry)
            tip = "本窗口换店配额已使用 (1/1)，下一次绑定新店铺后将永久锁定，无法再次更改。" if not is_admin else "管理员不受换店次数限制。"
            return True, f"✅ 已成功解绑当前窗口绑定的店铺【{old.get('store_name')}】！当前窗口仍处于授权状态，注意：{tip}"
        return False, "ℹ️ 当前会话窗口尚未绑定任何店铺。"

    def get_active_session_credentials(self, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取当前会话可用于上架的有效店铺凭据
        若未授权或未绑定店铺，直接抛出异常强行阻断
        """
        cid = self.get_current_conversation_id(conversation_id)
        auth_ok, auth_msg, session_entry = self.verify_session_authorized(cid)
        if not auth_ok:
            raise SessionAuthorizationError(auth_msg)

        store = session_entry.get("bound_store")
        if not store or not store.get("wb_api_token"):
            raise ValueError(
                f"❌【未绑定店铺】当前会话窗口 ({cid}) 已获得商业授权，但尚未绑定 Wildberries 目标店铺！\n"
                f"请在窗口中输入绑定指令：\n"
                f"绑定店铺 店铺简称：我的店铺 API令牌：eyJ... 仓库ID：2200658 售价倍数：6.0"
            )

        return store

    def parse_command(self, raw_text: str, conversation_id: Optional[str] = None) -> Optional[str]:
        """解析对话中的控制指令"""
        text = raw_text.strip()
        cid = self.get_current_conversation_id(conversation_id)

        # 0. 获取授权码 / 商业收银台 / 会话ID / wb上架激活码 (自动获取会话ID并分发支付宝支付二维码与极简指引)
        trigger_keywords = [
            "wb上架激活码", "wb激活码", "wb上架授权码", "wb授权码", "wb上架", "激活码", "获取激活码", "购买激活码", "申请激活码",
            "获取授权码", "获取授权", "授权码", "申请授权", "申请授权码", "购买授权", "开通授权", 
            "开通", "购买", "购买套餐", "收费标准", "收费", "价格", "收银台", "cashier", "pay", 
            "获取会话id", "查看会话id", "会话id", "conversation_id", "cid", "获取id", "id"
        ]
        if text.lower() in [k.lower() for k in trigger_keywords] or (
            ("激活码" in text or "授权码" in text or "收银台" in text or "购买" in text) 
            and not text.startswith("LIC-") and not text.startswith("激活授权") and not text.startswith("激活")
        ):
            cashier_url = f"https://wb-auth-gateway.cnproduct.workers.dev/pay?cid={cid}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=https%3A%2F%2Fwb-auth-gateway.cnproduct.workers.dev%2Fpay%3Fcid%3D{cid}"
            return (
                f"🛒 **Wildberries 极速智能上架助手 · 商业授权专属开通**\n\n"
                f"🆔 **当前窗口专属 ID (Conversation ID)**:\n"
                f"`{cid}`\n\n"
                f"💰 **商业收费法则**：**每家 Wildberries 店铺收费 600 元人民币（¥600/店铺/年，自支付当日起 365 天有效，一店一码 1:1 独立互斥隔离）**。\n\n"
                f"👉 **[点击打开支付宝在线收银台支付]({cashier_url})**\n\n"
                f"![支付宝扫码支付]({qr_url})\n\n"
                f"--- \n"
                f"⚡ **全自动智能流转闭环**：\n"
                f"1️⃣ **扫码支付**：手机支付宝扫码支付 600 元；\n"
                f"2️⃣ **自动激活**：支付成功后系统秒级自动签发授权码并【自动激活当前窗口】（无需手动输入！）；\n"
                f"3️⃣ **绑定店铺**：激活完成后系统自动提示您绑定目标店铺（发送：`绑定店铺 店铺简称：... API令牌：... 仓库ID：...`）；\n"
                f"4️⃣ **智能上架**：店铺绑定成功后，直接发送 Ozon SKU 列表或 .txt 文档，全自动全要素搬家上架！\n\n"
                f"💡 提示：若已完成扫码支付，可直接输入「已支付」或「激活授权 <授权码>」进行核验。"
            )

        # 0.1 支付状态核验与自动激活
        if text in ["已支付", "支付完成", "我已付款", "已付款", "检查支付", "check_pay", "check_payment"]:
            client = CloudAuthClient()
            if client.is_cloud_enabled():
                try:
                    r = client.session.get(f"{client.base_url}/api/license/lookup?cid={cid}", timeout=3.0)
                    if r.status_code == 200:
                        data = r.json()
                        lic = data.get("license_key")
                        if lic:
                            ok, msg, _ = self.activate_license(lic, cid)
                            return f"🎉 **核验到支付成功！**\n\n" + msg
                except Exception:
                    pass
            return (
                f"⏳ 正在核验支付状态中...\n"
                f"若您已完成扫码支付，系统将在 1~3 秒内自动对账。\n"
                f"您也可以直接在当前对话框输入：`激活授权 <您收到的授权码>` 立即激活当前窗口！"
            )

        # 0.2 获取硬件机器码 (可选保留)
        if text in ["获取机器码", "查看机器码", "机器码", "machine_id", "machine-id", "硬件指纹", "mid"]:
            mid = get_machine_id()
            return (
                f"💻 **当前电脑硬件指纹 (Machine ID)**: `{mid}`\n"
                f"🆔 **当前窗口会话 ID (Conversation ID)**: `{cid}`\n\n"
                f"💡 提示：本系统默认按窗口会话 ID (Conversation ID) 实现 1 窗口 1 店铺隔离，无需强绑硬件机器码！"
            )

        # 1. 激活授权
        act_match = re.search(r'(?:激活授权|激活|license)[:：\s]+([^\s\n]+)', text, re.IGNORECASE)
        if act_match or (text.startswith("LIC-") and len(text) > 10):
            key = act_match.group(1).strip() if act_match else text.strip()
            ok, msg, _ = self.activate_license(key, cid)
            return msg

        # 2. 解绑店铺
        if text in ["解绑店铺", "解绑", "解除绑定", "unbind"]:
            ok, msg = self.unbind_store(cid)
            return msg

        # 3. 查看状态
        if text in ["店铺状态", "授权状态", "查看店铺", "状态", "status"]:
            registry = self._load_registry()
            sess = registry.get("sessions", {}).get(cid)
            if not sess or sess.get("status") != "AUTHORIZED":
                return (
                    f"🔒 **当前会话窗口状态**: `未授权 (UNAUTHORIZED)`\n"
                    f"🆔 **窗口 ID**: `{cid}`\n\n"
                    f"👉 请输入 `激活授权 <License_Key>` 进行激活。"
                )
            store = sess.get("bound_store")
            if not store:
                return (
                    f"✅ **当前会话窗口状态**: `已获商业授权`\n"
                    f"🔑 **授权码**: `{sess.get('license_key')}` ({sess.get('license_name')})\n"
                    f"🏢 **店铺绑定**: `尚未绑定店铺`\n\n"
                    f"👉 请输入 `绑定店铺 店铺简称：... API令牌：... 仓库ID：...` 进行绑定。"
                )
            is_adm = (sess.get('license_key') == MASTER_LICENSE_KEY)
            sw_count = sess.get('switch_count', 0)
            if is_adm:
                quota_str = "无限制 (超级管理员)"
            elif sw_count >= 1:
                quota_str = f"{sw_count}/1 (已用尽，本窗口已永久锁定)"
            else:
                quota_str = f"{sw_count}/1 (剩余 1 次更换机会)"

            return (
                f"🏢 **当前会话窗口专属店铺档案**:\n\n"
                f"• **窗口 ID**: `{cid}`\n"
                f"• **授权码**: `{sess.get('license_key')}` ({sess.get('license_name')})\n"
                f"• **店铺简称**: `{store.get('store_name')}`\n"
                f"• **履约仓库**: `{store.get('warehouse_name')}` (ID: `{store.get('wb_warehouse_id')}`)\n"
                f"• **结算货币**: `{store.get('store_currency', 'CNY')}`\n"
                f"• **默认策略**: `{store.get('default_multiplier', 6.0)}倍实售` | `{store.get('default_discount', 50)}%大促折` | `{store.get('default_stock', 5)}件库存`\n"
                f"• **Token 到期**: `{store.get('token_expiry')}`\n"
                f"• **换店配额**: `{quota_str}`\n"
                f"• **绑定时间**: `{store.get('bound_at')}`\n\n"
                f"🔒 本窗口仅对接该店铺，严禁串店。"
            )

        # 4. 绑定或切换店铺
        is_switch = "切换店铺" in text or "换店" in text or "switch" in text
        is_bind = "绑定店铺" in text or text.startswith("+店铺") or (text.startswith("绑定") and not act_match)

        if is_switch or is_bind:
            body = re.sub(r'^(?:切换店铺|换店|绑定店铺|[\+]店铺|绑定|switch)[:：\s]*', '', text).strip()
            # 提取 token
            jwt_match = re.search(r'(eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]+)', body)
            token = jwt_match.group(1).strip() if jwt_match else ""
            body_rem = body.replace(token, " ") if token else body

            # 提取店铺名称
            name_match = re.search(r'(?:店铺|简称|名称|store)[:：\s]+([^\s,，\n]+)', body_rem, re.IGNORECASE)
            store_name = name_match.group(1).strip() if name_match else ""
            if not store_name:
                parts = [p.strip() for p in body_rem.split() if p.strip()]
                for p in parts:
                    if not re.match(r'^\d+$', p) and '倍' not in p and '折' not in p and '库存' not in p:
                        store_name = p
                        break

            # 提取仓库 ID
            wh_match = re.search(r'(?:仓库|warehouse|仓|wh)[:：\s]*(\d{5,8})', body_rem, re.IGNORECASE)
            wh_id = int(wh_match.group(1)) if wh_match else None

            # 提取倍数
            m_match = re.search(r'(\d+(?:\.\d+)?)\s*倍', body_rem)
            multiplier = float(m_match.group(1)) if m_match else 6.0

            # 提取折扣
            d_match = re.search(r'(\d+)\s*(?:折|%)', body_rem)
            discount = int(d_match.group(1)) if d_match else 50
            if discount <= 9: discount *= 10

            # 提取库存
            s_match = re.search(r'(?:库存|现货)[:：\s]*(\d+)|(\d+)\s*(?:件|个|库存)', body_rem)
            stock = 5
            if s_match:
                s_val = s_match.group(1) or s_match.group(2)
                if s_val: stock = int(s_val)

            if not token:
                return "❌ 指令中未检测到有效的 Wildberries API 令牌 (JWT 格式)。格式示例：`绑定店铺 店铺简称：RR008 API令牌：eyJ... 仓库ID：2200658 6倍 50折 5库存`"

            if is_switch:
                ok, msg, _ = self.switch_store(store_name or "WB新店铺", token, wh_id, multiplier, discount, stock, conversation_id=cid)
                return msg
            else:
                ok, msg, _ = self.bind_store(store_name or "WB专属店铺", token, wh_id, multiplier, discount, stock, conversation_id=cid)
                return msg

        # 5. 云端看板与远程管理指令
        if text in ["云端看板", "用量看板", "商业看板", "云端控制台", "dashboard"]:
            client = CloudAuthClient()
            if not client.is_cloud_enabled():
                return (
                    f"☁️ **云端授权网关未配置**\n\n"
                    f"当前系统处于【纯本地 RSA-2048 离线硬件绑定模式】。\n"
                    f"如需接入云端鉴权与 Web 可视化用量看板，请在 `config.json` 中配置 `cloud_auth_url`，\n"
                    f"详情参考 [`cloud/DEPLOY_GUIDE.md`](./cloud/DEPLOY_GUIDE.md)。"
                )
            dash_url = f"{client.base_url}/admin?key={client.admin_secret}"
            return (
                f"☁️ **Wildberries 商业授权与用量追踪云端看板**:\n\n"
                f"🔗 **Web 看板直达**: [{dash_url}]({dash_url})\n"
                f"🌐 **网关服务节点**: `{client.base_url}`\n"
                f"📊 **核心功能**: 实时查看全网设备在线状态、累计上架用量、一键秒级封禁与充值续期。"
            )

        # 远程在线封禁指令 (仅管理员)
        ban_match = re.search(r'(?:封禁授权|在线封禁|远程封禁|ban)[:：\s]+([^\s\n]+)(?:\s+(.+))?', text, re.IGNORECASE)
        if ban_match:
            lic_target = ban_match.group(1).strip()
            reason = ban_match.group(2).strip() if ban_match.group(2) else "违规封禁"
            client = CloudAuthClient()
            ok, msg = client.admin_ban(lic_target, reason)
            if ok:
                return f"🚫 **远程在线封禁成功！**\n授权码 `{lic_target}` 已被云端网关瞬时拦截，该客户所有会话将即刻锁死。\n原因: {reason}"
            return f"❌ 远程封禁请求失败: {msg}"

        # 远程在线解封指令 (仅管理员)
        unban_match = re.search(r'(?:解封授权|在线解封|远程解封|unban)[:：\s]+([^\s\n]+)', text, re.IGNORECASE)
        if unban_match:
            lic_target = unban_match.group(1).strip()
            client = CloudAuthClient()
            ok, msg = client.admin_unban(lic_target)
            if ok:
                return f"✅ **远程在线解封成功！**\n授权码 `{lic_target}` 已恢复正常使用状态。"
            return f"❌ 远程解封请求失败: {msg}"

        # 远程充值续期指令 (仅管理员)
        renew_match = re.search(r'(?:充值授权|在线充值|远程充值|续期授权|renew)[:：\s]+([^\s\n]+)(?:\s+(\d+))?', text, re.IGNORECASE)
        if renew_match:
            lic_target = renew_match.group(1).strip()
            days = int(renew_match.group(2)) if renew_match.group(2) else 30
            client = CloudAuthClient()
            ok, msg = client.admin_renew(lic_target, days)
            if ok:
                return f"🎉 **远程充值续期成功！**\n授权码 `{lic_target}` 已成功追加有效期 {days} 天。"
            return f"❌ 远程充值请求失败: {msg}"

        return None

def main():
    parser = argparse.ArgumentParser(description="Antigravity Mode B 会话级商业授权与单窗口单店铺隔离管理器")
    subparsers = parser.add_subparsers(dest="action", help="执行操作")

    # 1. status
    p_status = subparsers.add_parser("status", help="查询当前会话授权与店铺状态")
    p_status.add_argument("--conversation-id", default=None, help="会话窗口 ID")

    # 2. generate-license
    p_gen = subparsers.add_parser("generate-license", help="管理员生成商业授权码")
    p_gen.add_argument("--name", default="商业客户", help="授权对象名称")
    p_gen.add_argument("--mid", default=None, help="绑定的目标机器码 (默认本机, 或 '*' 通配)")
    p_gen.add_argument("--max-sessions", type=int, default=1, help="允许激活的会话窗口数 (-1 表示无限)")
    p_gen.add_argument("--days", type=int, default=365, help="有效天数")

    # 2.1 machine-id
    p_mid = subparsers.add_parser("machine-id", help="查看当前设备的硬件机器码")

    # 3. activate
    p_act = subparsers.add_parser("activate", help="在当前会话激活授权")
    p_act.add_argument("--license", required=True, help="商业授权码")
    p_act.add_argument("--conversation-id", default=None, help="会话窗口 ID")

    # 4. bind
    p_bind = subparsers.add_parser("bind", help="绑定当前会话的唯一店铺")
    p_bind.add_argument("--store", required=True, help="店铺简称")
    p_bind.add_argument("--token", required=True, help="Wildberries API 令牌")
    p_bind.add_argument("--warehouse", type=int, default=None, help="仓库 ID")
    p_bind.add_argument("--multiplier", type=float, default=6.0, help="实售倍数")
    p_bind.add_argument("--discount", type=int, default=50, help="大促折扣率")
    p_bind.add_argument("--stock", type=int, default=5, help="现货库存")
    p_bind.add_argument("--currency", default="CNY", help="店铺结算货币")
    p_bind.add_argument("--conversation-id", default=None, help="会话窗口 ID")

    # 5. switch
    p_switch = subparsers.add_parser("switch", help="切换更换当前会话的店铺")
    p_switch.add_argument("--store", required=True, help="新店铺简称")
    p_switch.add_argument("--token", required=True, help="新 Wildberries API 令牌")
    p_switch.add_argument("--warehouse", type=int, default=None, help="新仓库 ID")
    p_switch.add_argument("--multiplier", type=float, default=6.0, help="实售倍数")
    p_switch.add_argument("--discount", type=int, default=50, help="大促折扣率")
    p_switch.add_argument("--stock", type=int, default=5, help="现货库存")
    p_switch.add_argument("--currency", default="CNY", help="店铺结算货币")
    p_switch.add_argument("--conversation-id", default=None, help="会话窗口 ID")

    # 6. unbind
    p_unbind = subparsers.add_parser("unbind", help="解绑当前会话的店铺")
    p_unbind.add_argument("--conversation-id", default=None, help="会话窗口 ID")

    # 7. list-sessions
    p_list = subparsers.add_parser("list-sessions", help="管理员列出所有会话与店铺绑定记录")

    # 8. cloud-dashboard
    p_cdash = subparsers.add_parser("cloud-dashboard", help="查看云端可视化看板地址")

    # 9. cloud-ban
    p_cban = subparsers.add_parser("cloud-ban", help="管理员远程封禁指定授权码")
    p_cban.add_argument("--license", required=True, help="要封禁的授权码")
    p_cban.add_argument("--reason", default="管理员远程封禁", help="封禁原因")

    # 10. cloud-unban
    p_cunban = subparsers.add_parser("cloud-unban", help="管理员远程解封指定授权码")
    p_cunban.add_argument("--license", required=True, help="要解封的授权码")

    # 11. cloud-renew
    p_crenew = subparsers.add_parser("cloud-renew", help="管理员远程续费指定授权码")
    p_crenew.add_argument("--license", required=True, help="要续费的授权码")
    p_crenew.add_argument("--days", type=int, default=30, help="追加天数")

    # 12. cloud-list
    p_clist = subparsers.add_parser("cloud-list", help="管理员获取云端所有授权与用量记录")

    args = parser.parse_args()
    mgr = SessionManager()

    if args.action == "status" or not args.action:
        msg = mgr.parse_command("店铺状态", getattr(args, 'conversation_id', None))
        print(msg)
    elif args.action == "machine-id":
        msg = mgr.parse_command("获取机器码")
        print(msg)
    elif args.action == "generate-license":
        res = mgr.generate_license(args.name, args.max_sessions, args.days, getattr(args, 'mid', None))
        print(f"✅ 成功生成商业授权码: {res['license_key']}")
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.action == "activate":
        ok, msg, _ = mgr.activate_license(args.license, args.conversation_id)
        print(msg)
    elif args.action == "bind":
        ok, msg, _ = mgr.bind_store(args.store, args.token, args.warehouse, args.multiplier, args.discount, args.stock, args.currency, args.conversation_id)
        print(msg)
    elif args.action == "switch":
        ok, msg, _ = mgr.switch_store(args.store, args.token, args.warehouse, args.multiplier, args.discount, args.stock, args.currency, args.conversation_id)
        print(msg)
    elif args.action == "unbind":
        ok, msg = mgr.unbind_store(args.conversation_id)
        print(msg)
    elif args.action == "list-sessions":
        reg = mgr._load_registry()
        print(json.dumps(reg.get("sessions", {}), ensure_ascii=False, indent=2))
    elif args.action == "cloud-dashboard":
        msg = mgr.parse_command("云端看板")
        print(msg)
    elif args.action == "cloud-ban":
        client = CloudAuthClient()
        ok, msg = client.admin_ban(args.license, args.reason)
        print(f"[{'SUCCESS' if ok else 'FAILED'}] {msg}")
    elif args.action == "cloud-unban":
        client = CloudAuthClient()
        ok, msg = client.admin_unban(args.license)
        print(f"[{'SUCCESS' if ok else 'FAILED'}] {msg}")
    elif args.action == "cloud-renew":
        client = CloudAuthClient()
        ok, msg = client.admin_renew(args.license, args.days)
        print(f"[{'SUCCESS' if ok else 'FAILED'}] {msg}")
    elif args.action == "cloud-list":
        client = CloudAuthClient()
        ok, items = client.admin_list_licenses()
        if ok:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            print("[-] 获取云端授权列表失败")

if __name__ == "__main__":
    main()
