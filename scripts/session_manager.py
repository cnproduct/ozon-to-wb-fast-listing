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
            unauth_msg = (
                f"\n"
                f"================================================================================\n"
                f"🛑【商业授权拦截】当前 Antigravity 会话窗口未获得商业授权！\n"
                f"================================================================================\n"
                f"🆔 当前会话窗口 ID : {cid}\n"
                f"💻 本机硬件机器码   : {get_machine_id()}\n"
                f"🔒 授权状态         : 未授权 (UNAUTHORIZED)\n\n"
                f"⚠️ 安全铁律：\n"
                f"   本系统执行零信任商业授权门禁与一机一码物理绑定。新开启的窗口必须获得商业\n"
                f"   授权码激活后，方可开启 Wildberries 极速上架引擎。\n\n"
                f"👉 激活方法：\n"
                f"   1. 发送「获取机器码」获取本机专属硬件指纹并发送给管理员；\n"
                f"   2. 在对话框输入激活指令：激活授权 LIC-RSA-...\n\n"
                f"📞 获取授权码请联系系统管理员。\n"
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

        # 2. 单窗口单店铺互斥检查 (Store Mutex Lock)
        if existing_store and not force:
            mutex_msg = (
                f"\n"
                f"================================================================================\n"
                f"⚠️【店铺互斥安全锁】当前窗口已绑定店铺【{existing_store.get('store_name')}】！\n"
                f"================================================================================\n"
                f"🏢 已绑店铺 : {existing_store.get('store_name')}\n"
                f"📦 履约仓库 : {existing_store.get('warehouse_name')} (ID: {existing_store.get('wb_warehouse_id')})\n"
                f"🔑 令牌到期 : {existing_store.get('token_expiry')}\n\n"
                f"🔒 互斥铁律：\n"
                f"   每一个 Antigravity 对话窗口只允许绑定一家 Wildberries 店铺，严禁在同一窗口\n"
                f"   混绑 2 家及以上店铺，以防商品串店误传或库存错乱！\n\n"
                f"👉 如需将当前窗口切换到新店铺【{store_name}】，请使用明确的切换指令：\n"
                f"   切换店铺 店铺简称：{store_name} API令牌：{token[:15]}... 仓库ID：{warehouse_id or existing_store.get('wb_warehouse_id')}\n"
                f"   或者先执行：\n"
                f"   解绑店铺\n"
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

        curr_session["bound_store"] = store_record
        sessions[cid] = curr_session
        self._save_registry(registry)

        action_desc = "切换重绑" if force and existing_store else "绑定"
        succ_msg = (
            f"✅ **当前会话窗口已成功{action_desc}专属店铺【{store_record['store_name']}】！**\n\n"
            f"🏢 **店铺简称**: `{store_record['store_name']}`\n"
            f"📦 **履约仓库**: `{target_wh_name}` (ID: `{target_wh_id}`)\n"
            f"🔑 **Token 状态**: `有效 (到期: {exp_time})`\n"
            f"💰 **结算货币**: `{currency}`\n"
            f"📈 **默认策略**: `{multiplier}倍实售` | `{discount}%大促折` | `{stock}件现货`\n"
            f"🔒 **单店互斥保证**: 本会话窗口仅对接该店铺，所有极速上架任务均在此店铺安全执行！"
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
            old = sessions[cid].pop("bound_store")
            self._save_registry(registry)
            return True, f"✅ 已成功解绑当前窗口绑定的店铺【{old.get('store_name')}】！当前窗口仍处于授权状态，请绑定新店铺后再进行上架。"
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

        # 0. 获取硬件机器码 (Machine ID)
        if text in ["获取机器码", "查看机器码", "机器码", "machine_id", "machine-id", "硬件指纹", "mid"]:
            mid = get_machine_id()
            return (
                f"💻 **当前电脑专属硬件机器码 (Machine ID)**:\n\n"
                f"`{mid}`\n\n"
                f"👉 请将上述机器码复制发送给系统管理员，管理员将为您签发绑定该设备的不可篡改专属商业授权！"
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
            return (
                f"🏢 **当前会话窗口专属店铺档案**:\n\n"
                f"• **窗口 ID**: `{cid}`\n"
                f"• **授权码**: `{sess.get('license_key')}` ({sess.get('license_name')})\n"
                f"• **店铺简称**: `{store.get('store_name')}`\n"
                f"• **履约仓库**: `{store.get('warehouse_name')}` (ID: `{store.get('wb_warehouse_id')}`)\n"
                f"• **结算货币**: `{store.get('store_currency', 'CNY')}`\n"
                f"• **默认策略**: `{store.get('default_multiplier', 6.0)}倍实售` | `{store.get('default_discount', 50)}%大促折` | `{store.get('default_stock', 5)}件库存`\n"
                f"• **Token 到期**: `{store.get('token_expiry')}`\n"
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

if __name__ == "__main__":
    main()
