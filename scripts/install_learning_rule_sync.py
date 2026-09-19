"""Install the signed WB rule updater as a global Antigravity sidecar."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile


HOME = Path.home()
HUB_CONFIG = HOME / ".codex/wb-skill-learning/hub-config.json"
SIDECAR_DIR = HOME / ".gemini/config/sidecars/wb-skill-rules-sync"
SIDECAR_CONFIG = SIDECAR_DIR / "sidecar.json"
ANTIGRAVITY_CONFIG = HOME / ".gemini/config/config.json"


def atomic_json(path: Path, value: object, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode if mode is not None else (path.stat().st_mode & 0o777 if path.exists() else 0o600))
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> None:
    if not HUB_CONFIG.exists() or HUB_CONFIG.stat().st_mode & 0o077:
        raise SystemExit("请先由运营超级管理员安装权限为 0600 的 hub-config.json")
    source = Path(__file__).with_name("sync_learning_rules.py")
    if not source.exists():
        raise SystemExit("缺少规则同步脚本")
    SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
    target = SIDECAR_DIR / "sync_learning_rules.py"
    shutil.copyfile(source, target)
    os.chmod(target, 0o700)
    atomic_json(
        SIDECAR_CONFIG,
        {
            "display_name": "WB Skill 规则自动更新",
            "description": "每 15 分钟验证并安装管理员发布的签名规则版本",
            "builtin": "schedule",
            "args": ["*/15 * * * *", "python3", str(target)],
            "restart_policy": "always",
        },
    )
    try:
        config = json.loads(ANTIGRAVITY_CONFIG.read_text(encoding="utf-8")) if ANTIGRAVITY_CONFIG.exists() else {}
    except json.JSONDecodeError:
        raise SystemExit("Antigravity config.json 格式无效") from None
    if not isinstance(config, dict):
        raise SystemExit("Antigravity config.json 结构无效")
    sidecars = config.setdefault("sidecars", {})
    if not isinstance(sidecars, dict):
        raise SystemExit("Antigravity sidecars 配置无效")
    sidecars["wb-skill-rules-sync"] = {"enabled": True}
    atomic_json(ANTIGRAVITY_CONFIG, config)
    print("WB Skill 规则自动更新已安装：每 15 分钟检查一次。")


if __name__ == "__main__":
    main()
