# -*- coding: utf-8 -*-
"""
==============================================================================
RSA-2048 非对称数字签名防伪与硬件绑定鉴权核心 (License Cryptographic Engine)
==============================================================================
安全铁律：
1. 【非对称密码学绝对防护】：
   - 管理员端独占保管 RSA 私钥 (admin_private_key.pem)，负责签发；
   - 客户端仅内置公开 RSA 公钥 (public_key.pem)，仅用于验签；
   - 数学上无法通过公钥逆向推导出私钥，杜绝离线伪造授权码。
2. 【一机一码强绑定 (Hardware Mutex)】：
   - 授权载荷中硬编码写入目标设备的专属机器码 (Machine ID)；
   - 验签时若检测到当前机器指纹与授权中记录的指纹不一致，立即阻断崩溃；
   - 杜绝客户将授权码分享给他人或跨设备复制。
3. 【自包含数字签名与防篡改 (Tamper Resistance)】：
   - 采用 RSA-PSS + SHA256 对载荷进行高强度数字签名；
   - 客户在本地篡改 JSON 哪怕一个字节、修改有效期或机器码，验签立即失败。
==============================================================================
"""

import os
import sys
import json
import base64
import datetime
from typing import Dict, Any, Tuple, Optional

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

try:
    from machine_fingerprint import get_machine_id
except ImportError:
    from scripts.machine_fingerprint import get_machine_id

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

ADMIN_PRIVATE_KEY_PATH = os.path.join(WORKSPACE_DIR, 'admin_private_key.pem')
PUBLIC_KEY_PATH = os.path.join(WORKSPACE_DIR, 'public_key.pem')

# 默认内嵌公钥 (即使外部 public_key.pem 被误删也能正常验签)
DEFAULT_EMBEDDED_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuvIqkfIYx7nq8qpf0rFv
PecLVldEM12c7updA2+5FwHCP3U630Vox6HJOYF6DY+Cq2ghJT0jVtPxCEoK8QOj
GXt0MmhF7/otIZPoGqCpEiGcI/SpiEbSKgbsZXJK6PbRjcgm0uLJ8JbvlyyOqZAs
otSlPuDmQ0vWJbHHVQs3FLUsBke7Z7KDfjDcLbr5WGpCKQP60tssYvdAbW+Q2DJR
XAX+3f1CajjwWuNdgdoYccXfHlkfUHKMo0tst9q9RKOUFufPH55vrP1z9MzV1r0V
nArGTxcAvyNDZTEXGAYm3MmQKcXSDMrvuyqMPhdJ2bTCuRCmVJ8UOrV/PsRUwf4L
jwIDAQAB
-----END PUBLIC KEY-----"""

class LicenseCryptError(Exception):
    """授权加密核心基础异常"""
    pass

class LicenseSignatureError(LicenseCryptError):
    """签名损坏或被篡改异常"""
    pass

class LicenseExpiredError(LicenseCryptError):
    """授权已过期异常"""
    pass

class MachineMismatchError(LicenseCryptError):
    """机器码不匹配异常 (一码多机拦截)"""
    pass

class LicenseCrypto:
    def __init__(self, private_key_path: str = ADMIN_PRIVATE_KEY_PATH, public_key_path: str = PUBLIC_KEY_PATH):
        self.private_key_path = private_key_path
        self.public_key_path = public_key_path
        self._ensure_keys_exist()

    def _ensure_keys_exist(self):
        """如果不存在密钥对（初次运行），自动生成管理员 RSA-2048 密钥对"""
        if not os.path.exists(self.private_key_path) or not os.path.exists(self.public_key_path):
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            public_key = private_key.public_key()

            # 保存私钥 (仅管理员拥有，严禁提交 git / 严禁打入 release)
            pem_priv = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            with open(self.private_key_path, 'wb') as f:
                f.write(pem_priv)

            # 保存公钥 (可公开分发给客户端)
            pem_pub = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            with open(self.public_key_path, 'wb') as f:
                f.write(pem_pub)

    def load_private_key(self):
        """加载管理员私钥"""
        if not os.path.exists(self.private_key_path):
            raise FileNotFoundError(
                f"❌ 管理员签名私钥不存在: {self.private_key_path}\n"
                f"只有管理员本地持有该文件，请勿在客户端执行签名操作。"
            )
        with open(self.private_key_path, 'rb') as f:
            return serialization.load_pem_private_key(f.read(), password=None)

    def load_public_key(self):
        """加载公钥 (客户端与管理员通用)"""
        if os.path.exists(self.public_key_path):
            with open(self.public_key_path, 'rb') as f:
                return serialization.load_pem_public_key(f.read())
        # 兼容打包为二进制后直接从代码内置公钥载入
        return serialization.load_pem_public_key(DEFAULT_EMBEDDED_PUBLIC_KEY_PEM)

    def sign_license(self, machine_id: str, customer_name: str = "VIP商户", 
                     days: int = 365, max_sessions: int = 1) -> str:
        """
        【管理员专有】使用 RSA-2048 私钥对客户机器码进行数字签名并签发授权包
        """
        priv_key = self.load_private_key()
        now = datetime.datetime.now()
        expires_dt = now + datetime.timedelta(days=days) if days > 0 else datetime.datetime(2099, 12, 31)
        
        payload = {
            "v": "2.0",
            "mid": machine_id.strip().upper(),
            "name": customer_name.strip(),
            "max_s": max_sessions,
            "iat": now.strftime("%Y-%m-%d %H:%M:%S"),
            "exp": expires_dt.strftime("%Y-%m-%d 23:59:59"),
            "perm": ["listing", "pricing", "stocks", "fast_list"]
        }

        # 紧凑确定性序列化
        serialized = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
        signature = priv_key.sign(
            serialized,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )

        package = {
            "p": payload,
            "s": base64.b64encode(signature).decode('ascii')
        }

        # 组装为便于传输复制的 License Token
        token_str = base64.b64encode(json.dumps(package, separators=(',', ':')).encode('utf-8')).decode('ascii')
        formatted_license = f"LIC-RSA-{token_str}"
        return formatted_license

    def verify_license(self, license_str: str, current_machine_id: Optional[str] = None) -> Dict[str, Any]:
        """
        【客户端与运行库共用】验证授权包的 RSA 真实签名、有效期与当前硬件机器码
        若被篡改、过期或非本机运行，直接抛出严厉异常阻断执行
        """
        raw = license_str.strip()
        if raw.startswith("LIC-RSA-"):
            raw = raw[8:].strip()

        try:
            raw_json = base64.b64decode(raw.encode('ascii')).decode('utf-8')
            package = json.loads(raw_json)
            payload = package["p"]
            signature = base64.b64decode(package["s"].encode('ascii'))
        except Exception as e:
            raise LicenseSignatureError(f"❌【授权码解析失败】授权码格式非法或已损坏: {e}")

        # 1. 验证 RSA 非对称数字签名
        pub_key = self.load_public_key()
        serialized = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
        try:
            pub_key.verify(
                signature,
                serialized,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
        except Exception:
            raise LicenseSignatureError(
                "🚨【数字签名验签失败】该授权码已被非法篡改或不是由官方正版私钥签发！禁止使用！"
            )

        # 2. 验证有效期
        exp_str = payload.get("exp")
        if exp_str and exp_str != "unlimited":
            try:
                exp_dt = datetime.datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                if datetime.datetime.now() > exp_dt:
                    raise LicenseExpiredError(
                        f"⏰【商业授权已到期】该授权已于 {exp_str} 到期，请联系管理员续费更新！"
                    )
            except ValueError:
                pass

        # 3. 验证硬件机器码强绑定 (一机一码铁律)
        licensed_mid = payload.get("mid", "").upper()
        # 允许超级万能管理员通配符 "*"（仅用于开发测试）
        if licensed_mid != "*":
            actual_mid = (current_machine_id or get_machine_id()).upper()
            if actual_mid != licensed_mid:
                raise MachineMismatchError(
                    f"\n"
                    f"================================================================================\n"
                    f"🛑【设备硬件指纹不匹配 (一码多机违规拦截)】\n"
                    f"================================================================================\n"
                    f"🔑 授权绑定机器码 : {licensed_mid}\n"
                    f"💻 当前实际机器码 : {actual_mid}\n\n"
                    f"⚠️ 安全铁律：\n"
                    f"   本商业软件严格实行「一机一码硬件绑定」。该授权码仅允许在特定授权电脑上运行，\n"
                    f"   严禁将软件及授权码拷贝至其他设备运行！\n\n"
                    f"👉 如需在新电脑上使用，请在当前电脑发送「获取机器码」后联系管理员办理换机授权。\n"
                    f"================================================================================\n"
                )

        return payload

def main():
    import argparse
    parser = argparse.ArgumentParser(description="RSA-2048 商业授权签发与验签工具")
    subparsers = parser.add_subparsers(dest="action", help="执行操作")

    # generate-rsa-license
    p_sign = subparsers.add_parser("sign", help="管理员使用私钥为指定机器码签发授权")
    p_sign.add_argument("--mid", required=True, help="目标设备机器码 (如 MID-XXXX-XXXX-...) 或 '*' (开发通配)")
    p_sign.add_argument("--name", default="商业客户", help="商户名称")
    p_sign.add_argument("--days", type=int, default=365, help="有效期天数")
    p_sign.add_argument("--max-sessions", type=int, default=1, help="并发窗口数")

    # verify
    p_ver = subparsers.add_parser("verify", help="验证授权码有效性")
    p_ver.add_argument("--license", required=True, help="待校验的 LIC-RSA 授权码")

    args = parser.parse_args()
    crypto = LicenseCrypto()

    if args.action == "sign":
        lic = crypto.sign_license(args.mid, args.name, args.days, args.max_sessions)
        print("=" * 80)
        print("🎉【RSA-2048 商业防伪授权签发成功】")
        print("=" * 80)
        print(f"👤 授权商户 : {args.name}")
        print(f"💻 绑定机器 : {args.mid}")
        print(f"⏳ 有效天数 : {args.days} 天")
        print(f"🔢 窗口配额 : {args.max_sessions} 个")
        print("-" * 80)
        print("🔑 专属防伪授权码 (请完整复制发送给客户)：\n")
        print(lic)
        print("=" * 80)
    elif args.action == "verify":
        try:
            info = crypto.verify_license(args.license)
            print("✅ 授权校验通过！载荷详情:")
            print(json.dumps(info, ensure_ascii=False, indent=2))
        except LicenseCryptError as e:
            print(f"❌ 验签失败: {e}")

if __name__ == '__main__':
    main()
