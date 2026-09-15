# -*- coding: utf-8 -*-
"""
==============================================================================
Wildberries 极速搬家技能商业防复刻一键编译打包发布引擎 (Protected Release Builder)
==============================================================================
核心机制：
1. 使用 PyArmor 对核心业务代码执行不可逆深度混淆与原生 .pyd 运行时绑定；
2. 彻底剥离全部 Python 明文源码，生成只包含二进制加密实体的 release 目录；
3. 严格隔离管理员机密：严禁打包 admin_private_key.pem 与历史调试数据；
4. 自动复制必要合规资产（类目映射字典、模板、使用手册、Skill 定义）；
5. 自动在独立沙箱中验真已编译包的可用性，断言机器码提取与鉴权引擎 100% 运行正常；
6. 自动打包生成供交付客户的干净压缩包：dist/ozon-to-wb-fast-listing-v3.0-protected.zip。
==============================================================================
"""

import os
import sys
import shutil
import zipfile
import subprocess
from typing import List

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
DIST_DIR = os.path.join(PROJECT_ROOT, 'dist')
RELEASE_DIR = os.path.join(DIST_DIR, 'ozon-to-wb-fast-listing')

# 核心保护脚本名单 (全部经 PyArmor 深度混淆编译)
CORE_PROTECTED_SCRIPTS = [
    'machine_fingerprint.py',
    'license_crypto.py',
    'session_manager.py',
    'fast_list.py',
    'listing_engine.py',
    'wb_uploader.py',
    'ozon_crawler.py',
    'clean_descriptions.py',
    'clean_trash_cards.py',
    'repush_indexed_prices.py',
    'verify_backend_data.py',
    'update_weights_and_promos.py'
]

# 公开静态辅助目录与文件 (直接拷贝至 release)
STATIC_DIRS = ['references', 'templates']
STATIC_FILES = [
    'config.example.json',
    'requirements.txt',
    'LICENSE',
    'README.md',
    'USER_MANUAL.md',
    'AGENTS.md',
    'GEMINI.md',
    'SKILL.md'
]

def clean_old_build():
    """清理旧的构建输出"""
    print("[1/6] 🧹 正在清理历史构建输出目录...")
    if os.path.exists(RELEASE_DIR):
        shutil.rmtree(RELEASE_DIR, ignore_errors=True)
    os.makedirs(RELEASE_DIR, exist_ok=True)
    print(f"    ➔ 发布目录就绪: {RELEASE_DIR}")

def obfuscate_scripts():
    """使用 PyArmor 混淆编译核心 Python 脚本"""
    print("[2/6] 🛡️ 正在使用 PyArmor 对核心脚本执行深度混淆加密与二进制打包...")
    target_scripts_dir = os.path.join(RELEASE_DIR, 'scripts')
    os.makedirs(target_scripts_dir, exist_ok=True)

    input_paths = []
    for s in CORE_PROTECTED_SCRIPTS:
        full_p = os.path.join(SCRIPT_DIR, s)
        if os.path.exists(full_p):
            input_paths.append(full_p)
        else:
            print(f"    ⚠️ 警告: 未找到指定脚本 {s}，跳过")

    # 构建并执行 pyarmor gen
    cmd = [
        sys.executable, "-m", "pyarmor.cli", "gen",
        "-O", target_scripts_dir,
        "--platform", "windows.amd64"
    ] + input_paths

    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, encoding='utf-8')
    if res.returncode != 0:
        print(f"[-] PyArmor 混淆失败: {res.stderr}\n{res.stdout}")
        sys.exit(1)
    
    print(f"    ✅ 核心脚本编译混淆完成！已生成原生 C 扩展运行时与加密实体至 {target_scripts_dir}")

def copy_static_assets():
    """复制非敏感配置、文档及类目字典"""
    print("[3/6] 📦 正在复制静态合规类目字典、模板及说明文档...")
    
    # 拷贝静态目录
    for d in STATIC_DIRS:
        src = os.path.join(PROJECT_ROOT, d)
        dst = os.path.join(RELEASE_DIR, d)
        if os.path.exists(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
            print(f"    ➔ 已同步目录: {d}/")

    # 拷贝静态文件
    for f in STATIC_FILES:
        src = os.path.join(PROJECT_ROOT, f)
        dst = os.path.join(RELEASE_DIR, f)
        if os.path.exists(src):
            shutil.copyfile(src, dst)
            print(f"    ➔ 已复制文件: {f}")

    # 复制工作区技能定义 .agents/skills/
    agent_skills_src = os.path.join(PROJECT_ROOT, '.agents')
    agent_skills_dst = os.path.join(RELEASE_DIR, '.agents')
    if os.path.exists(agent_skills_src):
        shutil.copytree(agent_skills_src, agent_skills_dst, dirs_exist_ok=True)
        # 将技能目录下的 scripts 替换为混淆编译后的二进制版本，杜绝明文源码泄漏
        skill_scripts_dst = os.path.join(agent_skills_dst, 'skills', 'ozon-to-wb-fast-listing', 'scripts')
        if os.path.exists(skill_scripts_dst):
            shutil.rmtree(skill_scripts_dst, ignore_errors=True)
        shutil.copytree(os.path.join(RELEASE_DIR, 'scripts'), skill_scripts_dst)
        print("    ➔ 已同步 Agent Skill 定义目录 (已注入混淆二进制): .agents/")

def audit_security_leak():
    """严格安全审计：确保私钥与任何敏感测试数据绝对不泄露"""
    print("[4/6] 🔍 正在执行发布包机密泄漏严格安全审计...")
    leaks = []
    for root, dirs, files in os.walk(RELEASE_DIR):
        for f in files:
            # 严格禁止任何私钥
            if "private" in f.lower() or f.endswith(".pem") or f.endswith(".key"):
                leaks.append(os.path.join(root, f))
            # 检查是否有未混淆的敏感源码残留
            if f in CORE_PROTECTED_SCRIPTS:
                p = os.path.join(root, f)
                with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                    content = fp.read(200)
                    if "pyarmor" not in content.lower():
                        leaks.append(f"未混淆的明文源码: {p}")
            # 排除历史抓取调试大文件
            if "batch" in f.lower() or "extracted" in f.lower():
                leaks.append(os.path.join(root, f))

    if leaks:
        print("🚨【安全审计失败】检测到以下潜在机密泄漏：")
        for l in leaks:
            print(f"    ❌ {l}")
        print("构建已强行终止！")
        sys.exit(1)
    
    print("    ✅ 安全审计 100% 通过！绝无私钥及敏感源码泄露。")

def verify_release_runtime():
    """在发布包独立运行沙箱中验证可执行性"""
    print("[5/6] 🧪 正在沙箱环境中检验已编译加密包的实际执行能力...")
    test_script = os.path.join(RELEASE_DIR, 'scripts', 'session_manager.py')
    
    # 测试机器码提取
    cmd_mid = [sys.executable, test_script, "machine-id"]
    res_mid = subprocess.run(cmd_mid, cwd=RELEASE_DIR, capture_output=True, text=True, encoding='utf-8')
    if res_mid.returncode != 0 or "MID-" not in res_mid.stdout:
        print(f"[-] 沙箱测试 machine-id 失败: {res_mid.stderr}\n{res_mid.stdout}")
        sys.exit(1)
    print("    ➔ [1/2] 二进制机器码提取模块 (machine-id): 正常通过！")

    # 测试状态命令
    cmd_st = [sys.executable, test_script, "status"]
    res_st = subprocess.run(cmd_st, cwd=RELEASE_DIR, capture_output=True, text=True, encoding='utf-8')
    if res_st.returncode != 0:
        print(f"[-] 沙箱测试 status 失败: {res_st.stderr}\n{res_st.stdout}")
        sys.exit(1)
    print("    ➔ [2/2] 二进制鉴权路由与店铺管理器 (status): 正常通过！")
    print("    ✅ 发布包沙箱验证 100% 成功！")

def create_release_zip():
    """打包生成发布 ZIP 压缩包"""
    print("[6/6] 🗜️ 正在打包生成发布压缩包...")
    zip_path = os.path.join(DIST_DIR, 'ozon-to-wb-fast-listing-v3.0-protected.zip')
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(RELEASE_DIR):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, DIST_DIR)
                zf.write(abs_path, rel_path)

    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"    🎉 商业防护发布包构建大功告成！")
    print(f"    📦 压缩包路径 : {zip_path} ({zip_size_mb:.2f} MB)")
    print(f"    📁 解压目录   : {RELEASE_DIR}")

def main():
    print("=" * 80)
    print("🚀【Wildberries 搬家助手 - 商业防护发布包一键编译构建器】")
    print("=" * 80)
    clean_old_build()
    obfuscate_scripts()
    copy_static_assets()
    audit_security_leak()
    verify_release_runtime()
    create_release_zip()
    print("=" * 80)
    print("💡 提示：交付给客户时，直接发送该 zip 压缩包即可，对方无法阅读或修改任何源码！")
    print("=" * 80)

if __name__ == '__main__':
    main()
