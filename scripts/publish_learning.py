"""Upload only de-identified WB Skill learning candidates to the learning hub."""

import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

FIELDS = ("category", "observation", "outcome", "suggestion", "evidence")
CATEGORIES = {"故障", "平台变化", "政策变化", "商品", "物流", "用户操作", "其他"}
EVIDENCE = {"平台回执", "官方来源", "代码验证", "用户反馈", "待核实"}
SENSITIVE = re.compile(r"(?i)(?:api[_ -]?key|token|secret|private[_ -]?key|license[_ -]?key|authorization|bearer|password|conversation[_ -]?id|chat[_ -]?id|store[_ -]?id|shop[_ -]?id|sku|nmid|barcode|订单号|手机号|授权码|密钥|店铺名|客户名|(?:\d{1,3}\.){3}\d{1,3}|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{5,}\b|https?://\S+|/Users/\S+|[A-Za-z]:\\\S+)")
ROOT = Path.home() / ".codex/wb-skill-learning"


def brief(value):
    if not isinstance(value, str):
        raise ValueError("not text")
    value = value.strip()
    if len(value) < 2 or len(value) > 400 or SENSITIVE.search(value) or any(ord(char) < 32 for char in value):
        raise ValueError("sensitive or invalid")
    return value


def candidates(path: Path):
    skipped = 0
    items = []
    if not path.exists():
        return items, skipped
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                source = json.loads(line)
                item = {key: source[key] for key in FIELDS}
                if item["category"] not in CATEGORIES or item["evidence"] not in EVIDENCE:
                    raise ValueError("category or evidence")
                for key in ("observation", "outcome", "suggestion"):
                    item[key] = brief(item[key])
                items.append(item)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                skipped += 1
    return items, skipped


def batches(items):
    batch = []
    for item in items:
        proposed = batch + [item]
        if batch and len(json.dumps({"items": proposed}, ensure_ascii=False).encode()) > 12000:
            yield batch
            batch = [item]
        else:
            batch = proposed
        if len(batch) == 10:
            yield batch
            batch = []
    if batch:
        yield batch


def main():
    config_path = ROOT / "hub-config.json"
    if not config_path.exists():
        raise SystemExit("集中接收配置尚未安装")
    if os.name != "nt" and config_path.stat().st_mode & 0o077:
        raise SystemExit("集中接收配置文件权限必须为 0600")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    endpoint = config.get("endpoint", "")
    token = config.get("ingest_token", "")
    if not endpoint.startswith("https://") or not token:
        raise SystemExit("集中接收配置不完整")
    items, skipped = candidates(ROOT / "candidates.jsonl")
    accepted = duplicate = 0
    for batch in batches(items):
        data = json.dumps({"items": batch}, ensure_ascii=False).encode()
        request = Request(
            endpoint.rstrip("/") + "/api/ingest",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + token, "User-Agent": "WB-Skill-Learning/1.0"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError):
            raise SystemExit("集中接收失败，请检查本机内部日志与服务状态") from None
        accepted += result["accepted"]
        duplicate += result["duplicate"]
    print(f"集中接收完成：新增 {accepted}，已存在 {duplicate}，本地跳过 {skipped}")


if __name__ == "__main__":
    main()
