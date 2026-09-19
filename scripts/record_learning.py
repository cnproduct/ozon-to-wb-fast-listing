"""Save a short, de-identified WB/Ozon lesson for later human review."""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re


REJECT = re.compile(
    r"(?i)(?:api[_ -]?key|token|secret|private[_ -]?key|license[_ -]?key|"
    r"authorization|bearer|password|conversation[_ -]?id|chat[_ -]?id|"
    r"store[_ -]?id|shop[_ -]?id|sku|nmid|barcode|订单号|手机号|授权码|密钥|"
    r"(?:\d{1,3}\.){3}\d{1,3}|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"\b\d{8,}\b|https?://\S+|/Users/\S+|[A-Za-z]:\\\S+)"
)
CATEGORIES = ("故障", "平台变化", "政策变化", "商品", "物流", "用户操作", "其他")
EVIDENCE = ("平台回执", "官方来源", "代码验证", "用户反馈", "待核实")


def brief(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 600 or REJECT.search(value):
        raise ValueError("请使用不含身份、商品编号、凭据、原始日志和链接的简短概括")
    return value


def record(args, path: Path) -> bool:
    observation = brief(args.observation)
    outcome = brief(args.outcome)
    suggestion = brief(args.suggestion)
    entry = {
        "category": args.category,
        "observation": observation,
        "outcome": outcome,
        "suggestion": suggestion,
        "evidence": args.evidence,
        "status": "candidate",
    }
    key = hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.exists():
        with path.open(encoding="utf-8") as old:
            for line in old:
                if json.loads(line).get("fingerprint") == key:
                    return False
    entry["fingerprint"] = key
    entry["recorded_at"] = datetime.now(timezone.utc).isoformat()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except BaseException:
        # fdopen owns fd once successful; closing an already closed fd is harmless here.
        raise
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="记录去标识化的 Skill 改进候选，仅保存在本机")
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    parser.add_argument("--observation", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--suggestion", required=True)
    parser.add_argument("--evidence", choices=EVIDENCE, required=True)
    args = parser.parse_args()
    path = Path.home() / ".codex/wb-skill-learning/candidates.jsonl"
    try:
        added = record(args, path)
    except ValueError as exc:
        parser.error(str(exc))
    print("已保存本地候选" if added else "已有同一候选，未重复保存")


if __name__ == "__main__":
    main()
