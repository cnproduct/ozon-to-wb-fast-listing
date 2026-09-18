# -*- coding: utf-8 -*-
"""
==============================================================================
云端鉴权客户端连接器与远程状态同步核心 (Cloud Auth Connector)
==============================================================================
核心机制：
1. 【实时在线验真与毫秒级远程封禁】：
   - 每次会话核验与上架前，向 Cloudflare Workers 网关发起 POST /api/verify；
   - 命中 BANNED 封禁状态时，瞬间锁定本地会话并清空授权，杜绝违规使用。
2. 【商业上架用量自动统计】：
   - 上架任务完成时自动向云端 POST /api/usage/record 上报成功 SKU 数量；
   - 实时聚合至管理员可视化 Web 看板。
3. 【高可用双模回退 (Offline Graceful Fallback)】：
   - 若遇到客户断网或云端 API 无法访问，自动平滑降级至本地 RSA-2048 硬件验签；
   - 兼顾管理员的绝对远程控制权与客户在弱网环境下的运行稳定性。
==============================================================================
"""

import os
import sys
import json
import requests
from typing import Dict, Any, Tuple, Optional

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

DEFAULT_TIMEOUT = 3.5
DEFAULT_ADMIN_SECRET = ""
DEFAULT_TRIAL_GATEWAY = "https://wb-auth-gateway.cnproduct.workers.dev"

def get_cloud_config() -> Tuple[str, str]:
    """获取云端网关配置 URL 与管理 Secret"""
    url = os.getenv("WB_CLOUD_AUTH_URL", "")
    secret = os.getenv("WB_ADMIN_SECRET", DEFAULT_ADMIN_SECRET)

    # 尝试从 config.json 读取
    config_paths = [
        os.path.join(os.getcwd(), 'config.json'),
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.json')),
        os.path.abspath(os.path.join(os.path.dirname(__file__), 'config.json'))
    ]
    for p in config_paths:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    if not url and cfg.get("cloud_auth_url"):
                        url = cfg.get("cloud_auth_url").strip()
                    if cfg.get("admin_secret"):
                        secret = cfg.get("admin_secret").strip()
                break
            except Exception:
                pass

    return url.rstrip('/'), secret

class CloudAuthClient:
    def __init__(self, base_url: Optional[str] = None, admin_secret: Optional[str] = None):
        cfg_url, cfg_secret = get_cloud_config()
        self.base_url = (base_url or cfg_url).rstrip('/')
        self.admin_secret = admin_secret or cfg_secret
        self.session = requests.Session()
        self.session.trust_env = False

    def is_cloud_enabled(self) -> bool:
        """检查是否配置了有效的云端网关"""
        return bool(self.base_url and self.base_url.startswith("http"))

    def request_trial(self, conversation_id: str, agent_id: str = "") -> Tuple[bool, Dict[str, Any]]:
        """由云端唯一签发试用码；客户端不持有签名私钥。"""
        gateway = self.base_url or DEFAULT_TRIAL_GATEWAY
        try:
            response = self.session.post(
                f"{gateway}/api/pay/create-order",
                json={"mid": conversation_id, "plan_id": "free_trial_2days", "agent_id": agent_id},
                timeout=DEFAULT_TIMEOUT,
            )
            data = response.json()
            if response.status_code == 200 and data.get("free") and data.get("license_key") and data.get("expires_at"):
                return True, {**data, "gateway": gateway}
            return False, {"error": data.get("error", "云端试用签发失败"), "already_claimed": data.get("already_claimed", False)}
        except (requests.RequestException, ValueError) as exc:
            return False, {"error": f"无法连接试用网关：{exc.__class__.__name__}"}

    def verify_trial_license(self, license_key: str, conversation_id: str, gateway: str) -> bool:
        """试用必须在线有效，网关不可达时不允许离线绕过时效。"""
        try:
            response = self.session.get(
                f"{gateway}/api/verify",
                params={"key": license_key, "mid": conversation_id},
                timeout=DEFAULT_TIMEOUT,
            )
            return response.status_code == 200 and response.json().get("valid") is True
        except (requests.RequestException, ValueError):
            return False

    def verify_cloud_license(self, license_key: str, machine_id: str, 
                             conversation_id: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        向云端 Worker 发起在线验真请求
        返回 (is_valid, status_code_or_reason, response_dict)
        """
        if not self.is_cloud_enabled():
            return True, "LOCAL_ONLY", {"message": "未配置云端网关，仅使用本地 RSA 保护"}

        url = f"{self.base_url}/api/verify"
        payload = {
            "license_key": license_key.strip(),
            "machine_id": machine_id.strip(),
            "conversation_id": conversation_id or "default"
        }

        try:
            r = self.session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "BANNED":
                    return False, "BANNED", data
                if data.get("valid") is True:
                    return True, "ACTIVE", data
                return False, data.get("reason", "INVALID"), data
            elif r.status_code == 400:
                data = r.json()
                return False, data.get("reason", "BAD_REQUEST"), data
            else:
                return True, "OFFLINE_FALLBACK", {"message": f"云端响应异常 (HTTP {r.status_code})，回退本地保护"}
        except requests.exceptions.RequestException as e:
            # 弱网或断网：平滑回退本地 RSA 验证，确保业务不中断
            return True, "OFFLINE_FALLBACK", {"message": f"云端网络连接超时，平滑回退本地验证: {e}"}

    def report_usage(self, license_key: str, items_count: int) -> bool:
        """上报本次成功搬家的商品总件数至云端看板"""
        if not self.is_cloud_enabled() or items_count <= 0:
            return False

        url = f"{self.base_url}/api/usage/record"
        payload = {
            "license_key": license_key.strip(),
            "items_count": int(items_count)
        }
        try:
            r = self.session.post(url, json=payload, timeout=2.5)
            return r.status_code == 200
        except Exception:
            return False

    def bind_session_agent(self, cid: str, agent_id: str, mid: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """向云端网关上报会话与代理商/渠道的归属绑定"""
        if not self.is_cloud_enabled():
            return True, {"local_only": True}

        url = f"{self.base_url}/api/session/bind-agent"
        payload = {
            "cid": cid,
            "agent_id": agent_id.strip(),
            "mid": mid or ""
        }
        try:
            r = self.session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
            if r.status_code == 200:
                return True, r.json()
            return False, {"status": r.status_code, "text": r.text}
        except Exception as e:
            return False, {"error": str(e)}

    def admin_ban(self, license_key: str, reason: str = "违规封禁") -> Tuple[bool, str]:
        """【管理员】远程在线封禁"""
        if not self.is_cloud_enabled():
            return False, "未配置云端网关 URL"

        url = f"{self.base_url}/api/admin/ban"
        headers = {
            "Authorization": f"Bearer {self.admin_secret}",
            "Content-Type": "application/json"
        }
        payload = {"license_key": license_key.strip(), "reason": reason.strip()}
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                return True, r.json().get("message", "封禁成功")
            return False, f"HTTP {r.status_code}: {r.text}"
        except Exception as e:
            return False, f"请求异常: {e}"

    def admin_unban(self, license_key: str) -> Tuple[bool, str]:
        """【管理员】远程解封"""
        if not self.is_cloud_enabled():
            return False, "未配置云端网关 URL"

        url = f"{self.base_url}/api/admin/unban"
        headers = {
            "Authorization": f"Bearer {self.admin_secret}",
            "Content-Type": "application/json"
        }
        payload = {"license_key": license_key.strip()}
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                return True, r.json().get("message", "解封成功")
            return False, f"HTTP {r.status_code}: {r.text}"
        except Exception as e:
            return False, f"请求异常: {e}"

    def admin_renew(self, license_key: str, add_days: int = 30) -> Tuple[bool, str]:
        """【管理员】远程充值续期"""
        if not self.is_cloud_enabled():
            return False, "未配置云端网关 URL"

        url = f"{self.base_url}/api/admin/renew"
        headers = {
            "Authorization": f"Bearer {self.admin_secret}",
            "Content-Type": "application/json"
        }
        payload = {"license_key": license_key.strip(), "add_days": int(add_days)}
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                return True, r.json().get("message", "续费成功")
            return False, f"HTTP {r.status_code}: {r.text}"
        except Exception as e:
            return False, f"请求异常: {e}"

    def admin_list_licenses(self) -> Tuple[bool, list]:
        """【管理员】获取云端所有商户记录"""
        if not self.is_cloud_enabled():
            return False, []

        url = f"{self.base_url}/api/admin/list"
        headers = {"Authorization": f"Bearer {self.admin_secret}"}
        try:
            r = self.session.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                return True, r.json().get("items", [])
            return False, []
        except Exception:
            return False, []
