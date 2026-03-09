# 错误演进库结构

```json
{
  "patterns": [
    {
      "signature": "HardFault|PC=0x08001234|CFSR=0x00000200",
      "fault_type": "HardFault",
      "count": 3,
      "first_seen": "2026-03-03T10:00:00+08:00",
      "last_seen": "2026-03-03T11:00:00+08:00",
      "latest_fix_playbook": "increase stack or fix invalid pointer",
      "evidence_paths": [
        "logs/hw_error/2026-03-03/ERR_20260303_0001.json"
      ]
    }
  ]
}
```
