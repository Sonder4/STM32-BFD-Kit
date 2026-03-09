#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="汇总调试活动结果")
    parser.add_argument("--session-dir", required=True, help="会话目录")
    parser.add_argument(
        "--output",
        default=".codex/debug/bfd-debug-orchestrator-campaign.md",
        help="汇总输出 Markdown",
    )
    args = parser.parse_args()

    session_dir = Path(args.session_dir)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    hardfault_jsons = sorted(session_dir.glob("hardfault_*.json"))
    step_logs = sorted(session_dir.glob("*.log"))

    faults = []
    for p in hardfault_jsons:
        data = read_json(p)
        if not data:
            continue
        faults.append(
            {
                "id": data.get("id", p.stem),
                "type": data.get("fault_type", "Unknown"),
                "pc": data.get("registers", {}).get("PC", "N/A"),
                "cfsr": data.get("fault_status", {}).get("CFSR", "N/A"),
                "path": str(p),
            }
        )

    lines = [
        "# BFD Debug Orchestrator Campaign",
        "",
        "## 结论",
        f"- 会话目录: {session_dir}",
        f"- 生成时间: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- HardFault 记录数: {len(faults)}",
        "",
        "## 关键证据路径",
    ]

    for p in step_logs[:20]:
        lines.append(f"- {p}")

    if faults:
        lines += ["", "## HardFault 关键摘要"]
        for f in faults:
            lines.append(
                f"- {f['id']} | {f['type']} | PC={f['pc']} | CFSR={f['cfsr']} | {f['path']}"
            )

    lines += [
        "",
        "## 下一步",
        "- 对重复 signature 优先复用 error-evolution 中已有修复手册。",
        "- 若场景 3/4 连续失败，先检查 J-Link 连接状态与目标运行状态。",
    ]

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"SUMMARY_OUT={out_path}")


if __name__ == "__main__":
    main()
