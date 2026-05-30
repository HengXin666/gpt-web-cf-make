#!/usr/bin/env python3
"""
脱敏导出脚本 — 读取 data/error/*.json, 去除敏感字段后输出到 data/error/sanitized/

使用方法:
    uv run scripts/sanitize_errors.py

用户可通过修改下方 KEEP_FIELDS 列表来控制输出哪些字段。
"""

import json
from pathlib import Path

# ── 配置 ──
# 保留的字段(白名单)。修改此列表即可控制输出内容。
KEEP_FIELDS = [
    "id",
    "access_token",
    "refresh_token",
    "plan_type",
    "created_at",
    "last_refreshed_at",
]

# 输入/输出目录
ERROR_DIR = Path("data/error")
OUTPUT_DIR = ERROR_DIR / "sanitized"


def sanitize_record(record: dict) -> dict:
    """只保留白名单字段"""
    return {k: record[k] for k in KEEP_FIELDS if k in record}


def main():
    if not ERROR_DIR.exists():
        print(f"目录不存在: {ERROR_DIR}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_files = sorted(ERROR_DIR.glob("*.json"))
    if not json_files:
        print("data/error/ 下没有 JSON 文件")
        return

    total_in = 0
    total_out = 0

    for src in json_files:
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"跳过 {src.name}: {e}")
            continue

        if not isinstance(data, list):
            print(f"跳过 {src.name}: 不是数组格式")
            continue

        sanitized = [sanitize_record(r) for r in data]
        out_path = OUTPUT_DIR / src.name
        out_path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")

        total_in += len(data)
        total_out += len(sanitized)
        print(f"  {src.name}: {len(data)} 条 → {out_path}")

    print(f"\n完成: 共处理 {total_in} 条记录, 输出到 {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
