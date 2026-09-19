"""Configure one WB learning client without exposing its device token in shell history."""

from __future__ import annotations

from getpass import getpass
import json
import os
from pathlib import Path
import re
import tempfile


DEFAULT_ENDPOINT = "https://wb-skill-learning-hub.cnproduct.workers.dev"
CONFIG = Path.home() / ".codex/wb-skill-learning/hub-config.json"
TOKEN = re.compile(r"^[A-Za-z0-9_-]{40,100}$")


def atomic_config(endpoint: str, token: str) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=CONFIG.name + ".", dir=CONFIG.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"endpoint": endpoint, "ingest_token": token}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, CONFIG)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> None:
    token = getpass("粘贴管理员签发的设备令牌（输入不会显示）：").strip()
    if not TOKEN.fullmatch(token):
        raise SystemExit("设备令牌格式无效")
    atomic_config(DEFAULT_ENDPOINT, token)
    print("设备令牌已保存到当前用户的私有配置目录。")


if __name__ == "__main__":
    main()
