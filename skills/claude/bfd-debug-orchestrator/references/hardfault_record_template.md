# HardFault 记录模板

## 记录目标

每次故障至少输出两份文件：
- `logs/hw_error/<date>/ERR_<id>.json`
- `logs/hw_error/<date>/ERR_<id>.md`

## 必填字段

- fault_type
- timestamp
- registers: R0-R12, SP, LR, PC, xPSR, MSP, PSP
- fault_status: CFSR, HFSR, DFSR, MMFAR, BFAR
- stack_trace
- addr2line
- scenario_id
- resolution_status
- evidence_paths

## 说明

优先引用寄存器实测值，禁止仅写推测结论。
