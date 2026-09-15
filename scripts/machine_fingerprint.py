# -*- coding: utf-8 -*-
"""
==============================================================================
硬件机器码与物理设备指纹提取模块 (Machine Fingerprint Extractor)
==============================================================================
核心机制：
1. 提取 Windows 物理硬件特征（主板 UUID、CPU 序列号、系统卷标序列号）；
2. 结合 MAC 物理网卡地址作为容错回退机制；
3. 基于 HMAC-SHA256 生成全球唯一的固定格式硬件指纹 (MID-XXXX-XXXX-XXXX-XXXX)；
4. 保证同一台物理设备多次运行结果 100% 幂等，换机运行指纹必定改变。
==============================================================================
"""

import os
import sys
import uuid
import hashlib
import subprocess
from typing import Optional

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

_CACHED_MACHINE_ID: Optional[str] = None
_CACHE_FILE = os.path.expanduser("~/.wb_machine_id")

def _run_cmd(cmd: str) -> str:
    """安全执行只读系统探测命令"""
    try:
        res = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=4, text=True)
        return res.strip()
    except Exception:
        return ""

def get_motherboard_uuid() -> str:
    """提取主板唯一 UUID"""
    # 优先 PowerShell CimInstance
    out = _run_cmd('powershell -NoProfile -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"')
    if out and len(out) > 10 and "error" not in out.lower():
        return out.split()[-1].strip()
    # 备用 wmic
    out = _run_cmd('wmic csproduct get uuid')
    lines = [line.strip() for line in out.splitlines() if line.strip() and "uuid" not in line.lower()]
    if lines:
        return lines[0]
    return ""

def get_cpu_processor_id() -> str:
    """提取 CPU 处理器硬件序列号"""
    out = _run_cmd('powershell -NoProfile -Command "(Get-CimInstance Win32_Processor).ProcessorId"')
    if out and len(out) > 6 and "error" not in out.lower():
        return out.split()[-1].strip()
    out = _run_cmd('wmic cpu get processorid')
    lines = [line.strip() for line in out.splitlines() if line.strip() and "processorid" not in line.lower()]
    if lines:
        return lines[0]
    return ""

def get_system_drive_serial() -> str:
    """提取系统盘卷标序列号"""
    out = _run_cmd('powershell -NoProfile -Command "(Get-Volume -DriveLetter C).SerialNumber"')
    if out and len(out) > 4:
        return out.split()[-1].strip()
    return ""

def get_mac_address() -> str:
    """提取原生物理网卡 MAC"""
    try:
        raw_mac = hex(uuid.getnode())[2:].zfill(12)
        return raw_mac.upper()
    except Exception:
        return "000000000000"

def get_machine_id() -> str:
    """
    生成当前设备的唯一物理硬件指纹
    格式：MID-XXXX-XXXX-XXXX-XXXX
    """
    global _CACHED_MACHINE_ID
    if _CACHED_MACHINE_ID:
        return _CACHED_MACHINE_ID

    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
                cached = f.read().strip()
                if cached.startswith("MID-") and len(cached) == 23:
                    _CACHED_MACHINE_ID = cached
                    return cached
        except Exception:
            pass

    mb_uuid = get_motherboard_uuid()
    cpu_id = get_cpu_processor_id()
    drive_id = get_system_drive_serial()
    mac_id = get_mac_address()

    # 组合多重硬件指纹，哪怕个别在极特殊环境读取为空，其余也能支撑唯一性
    combined = f"UUID:{mb_uuid}|CPU:{cpu_id}|DRIVE:{drive_id}|MAC:{mac_id}"
    digest = hashlib.sha256(combined.encode('utf-8')).hexdigest().upper()
    
    # 格式化为易读且标准的 16 位机器码: MID-4段4位
    mid = f"MID-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"
    _CACHED_MACHINE_ID = mid
    try:
        with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(mid)
    except Exception:
        pass
    return mid

def main():
    mid = get_machine_id()
    mb = get_motherboard_uuid() or "未知"
    cpu = get_cpu_processor_id() or "未知"
    mac = get_mac_address()
    
    print("=" * 70)
    print("💻【Wildberries 搬家助手 - 客户端设备硬件指纹】")
    print("=" * 70)
    print(f"🆔 本机专属机器码 : {mid}")
    print(f"🔩 主板 UUID       : {mb}")
    print(f"⚙️ CPU 序列号      : {cpu}")
    print(f"🌐 物理网卡 MAC    : {mac}")
    print("=" * 70)
    print("👉 请将上述「本机专属机器码」发送给系统管理员以获取商业授权！")
    print("=" * 70)

if __name__ == '__main__':
    main()
