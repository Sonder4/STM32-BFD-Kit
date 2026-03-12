#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="更新 HardFault 错误演进库")
    parser.add_argument("inputs", nargs="+", help="错误 JSON 文件路径")
    parser.add_argument(
        "--db",
        default=".codex/debug/error-evolution/hardfault-patterns.json",
        help="演进库 JSON 路径",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db = load_json(db_path)
    else:
        db = {"updated_at": None, "patterns": []}

    patterns = db.get("patterns", [])

    for p in args.inputs:
        src = Path(p)
        if not src.exists():
            continue
        data = load_json(src)

        regs = data.get("registers", {})
        fault_status = data.get("fault_status", {})
        signature = "|".join(
            [
                str(data.get("fault_type", "Unknown")),
                f"PC={regs.get('PC', 'N/A')}",
                f"CFSR={fault_status.get('CFSR', 'N/A')}",
            ]
        )

        matched = None
        for item in patterns:
            if item.get("signature") == signature:
                matched = item
                break

        ts = data.get("timestamp", datetime.now().astimezone().isoformat(timespec="seconds"))
        if matched is None:
            matched = {
                "signature": signature,
                "fault_type": data.get("fault_type", "Unknown"),
                "count": 0,
                "first_seen": ts,
                "last_seen": ts,
                "latest_fix_playbook": "pending",
                "evidence_paths": [],
            }
            patterns.append(matched)

        matched["count"] = int(matched.get("count", 0)) + 1
        matched["last_seen"] = ts

        evidence = str(src)
        if evidence not in matched["evidence_paths"]:
            matched["evidence_paths"].append(evidence)

        cfsr = fault_status.get("CFSR", "0x00000000")
        hfsr = fault_status.get("HFSR", "0x00000000")
        matched["latest_fix_playbook"] = (
            f"Check PC/LR mapping; decode CFSR={cfsr}, HFSR={hfsr}; verify stack and invalid pointers"
        )

    db["patterns"] = patterns
    db["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DB_UPDATED={db_path}")
    print(f"PATTERN_COUNT={len(patterns)}")


if __name__ == "__main__":
    main()
