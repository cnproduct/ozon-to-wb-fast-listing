"""Safely fast-forward the managed global WB Skill from its official repository."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY = "https://github.com/cnproduct/ozon-to-wb-fast-listing.git"
ALLOWED_REMOTES = {
    REPOSITORY,
    "https://github.com/cnproduct/ozon-to-wb-fast-listing",
    "git@github.com:cnproduct/ozon-to-wb-fast-listing.git",
    "ssh://git@github.com/cnproduct/ozon-to-wb-fast-listing.git",
}
TARGET = Path.home() / ".gemini/config/skills/ozon-to-wb-fast-listing"
STATUS = Path.home() / ".codex/wb-skill-learning/skill-update-status.json"


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(TARGET), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=120,
    )


def atomic_status(value: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=STATUS.name + ".", dir=STATUS.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, STATUS)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def verify_commit(commit: str) -> None:
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise RuntimeError("远端提交编号无效")
    request = Request(
        f"https://api.github.com/repos/cnproduct/ozon-to-wb-fast-listing/commits/{commit}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "WB-Skill-Updater/1.0"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("无法核验 GitHub 正式提交") from None
    verification = data.get("commit", {}).get("verification", {})
    if data.get("sha") != commit or verification.get("verified") is not True:
        raise RuntimeError("GitHub 正式提交签名未通过")


def validate_skill_at(commit: str) -> None:
    manifest = git("show", f"{commit}:SKILL.md").stdout
    if not manifest.startswith("---\n") and not manifest.startswith("---\r\n"):
        raise RuntimeError("远端 Skill 清单无效")
    if "name: ozon-to-wb-fast-listing" not in manifest or "description:" not in manifest:
        raise RuntimeError("远端 Skill 身份不匹配")
    if len(manifest) > 250_000:
        raise RuntimeError("远端 Skill 清单异常")


def validate_installed() -> None:
    required = [TARGET / "SKILL.md", TARGET / "scripts/fast_list.py", TARGET / "scripts/session_manager.py"]
    if any(not path.is_file() for path in required):
        raise RuntimeError("更新后的 Skill 文件不完整")
    scripts = [
        TARGET / "scripts/fast_list.py",
        TARGET / "scripts/listing_engine.py",
        TARGET / "scripts/session_manager.py",
        TARGET / "scripts/record_learning.py",
        TARGET / "scripts/publish_learning.py",
        TARGET / "scripts/sync_learning_rules.py",
    ]
    existing = [str(path) for path in scripts if path.exists()]
    if existing:
        subprocess.run(["python3", "-m", "py_compile", *existing], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)


def install_if_needed(install: bool) -> bool:
    if TARGET.exists():
        return False
    if not install:
        raise RuntimeError("全局 WB Skill 尚未安装")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--quiet", "--branch", "main", "--single-branch", REPOSITORY, str(TARGET)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    return True


def update(install: bool = False) -> tuple[str, str, bool]:
    installed = install_if_needed(install)
    if not (TARGET / ".git").exists():
        raise RuntimeError("全局 WB Skill 不是受管 Git 安装")
    remote = git("remote", "get-url", "origin").stdout.strip()
    if remote not in ALLOWED_REMOTES:
        raise RuntimeError("全局 WB Skill 来源不是官方仓库")
    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise RuntimeError("全局 WB Skill 存在本地修改，已停止静默更新")
    old = git("rev-parse", "HEAD").stdout.strip()
    git("fetch", "--quiet", "origin", "refs/heads/main:refs/remotes/origin/main")
    new = git("rev-parse", "refs/remotes/origin/main").stdout.strip()
    verify_commit(new)
    validate_skill_at(new)
    if old == new:
        validate_installed()
        return old, new, installed
    if git("merge-base", "--is-ancestor", old, new, check=False).returncode != 0:
        raise RuntimeError("远端历史不是安全快进，已停止更新")
    if git("diff", "--check", old, new, check=False).returncode != 0:
        raise RuntimeError("远端更新未通过差异检查")
    try:
        git("merge", "--ff-only", new)
        validate_installed()
    except Exception:
        git("reset", "--hard", old, check=False)
        raise RuntimeError("Skill 更新验证失败，已恢复旧版本") from None
    return old, new, True


def main() -> None:
    parser = argparse.ArgumentParser(description="安全更新 Antigravity 全局 WB Skill")
    parser.add_argument("--install", action="store_true", help="首次运行时安装官方全局 Skill")
    arguments = parser.parse_args()
    now = datetime.now(timezone.utc).isoformat()
    try:
        old, new, changed = update(arguments.install)
        atomic_status({"status": "ok", "checked_at": now, "commit": new})
        if changed:
            print(f"WB Skill 已静默更新：{old[:7]} -> {new[:7]}")
    except (RuntimeError, subprocess.SubprocessError, OSError) as error:
        atomic_status({"status": "failed", "checked_at": now, "message": str(error)})
        raise SystemExit(f"WB Skill 静默更新失败：{error}") from None


if __name__ == "__main__":
    main()
