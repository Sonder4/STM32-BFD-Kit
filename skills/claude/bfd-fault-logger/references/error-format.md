# 错误数据格式

本文档定义了硬件错误记录的数据格式规范。

## 1. 错误记录结构

### 1.1 完整错误记录

```json
{
    "id": "ERR_20240120_0001",
    "timestamp": "2024-01-20T10:30:45.123456+08:00",
    "fault_type": "HardFault",
    "severity": "Critical",
    "source": "CPU",
    "description": "HardFault - FORCED: Escalated from configurable fault, PRECISERR: Precise data bus error",
    "registers": {
        "R0": "0x20001234",
        "R1": "0x00000001",
        "R2": "0x00000000",
        "R3": "0x00000000",
        "R4": "0x20002000",
        "R5": "0x00000010",
        "R6": "0x00000000",
        "R7": "0x00000000",
        "R8": "0x00000000",
        "R9": "0x00000000",
        "R10": "0x00000000",
        "R11": "0x00000000",
        "R12": "0x00000000",
        "SP": "0x2001FFF0",
        "LR": "0x08002345",
        "PC": "0x08004567",
        "xPSR": "0x61000000",
        "MSP": "0x2001FFF0",
        "PSP": "0x00000000"
    },
    "fault_status": {
        "CFSR": "0x00000200",
        "HFSR": "0x40000000",
        "DFSR": "0x00000000",
        "AFSR": "0x00000000",
        "MMFAR": "0x00000000",
        "BFAR": "0x00000000"
    },
    "stack_trace": [
        "0x08004567",
        "0x08002345",
        "0x08001234",
        "0x08000ABC"
    ],
    "context": {
        "interrupt_depth": 2,
        "current_task": "main_task",
        "system_state": "running",
        "peripheral_state": {
            "UART1": "active",
            "SPI1": "idle",
            "DMA1": "transferring"
        }
    },
    "raw_data": "484152444641554C540A..."
}
```

### 1.2 字段说明

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| id | string | 是 | 唯一错误标识符，格式: ERR_YYYYMMDD_NNNN |
| timestamp | string | 是 | ISO 8601格式时间戳 |
| fault_type | string | 是 | 错误类型（见错误类型定义） |
| severity | string | 是 | 严重程度: Critical/High/Medium/Low/Info |
| source | string | 是 | 错误源: CPU/Memory/Bus/DMA/Peripheral/Clock/Power/System |
| description | string | 是 | 错误描述信息 |
| registers | object | 是 | 寄存器状态 |
| fault_status | object | 是 | 故障状态寄存器 |
| stack_trace | array | 否 | 堆栈回溯地址列表 |
| context | object | 否 | 错误发生时的上下文信息 |
| raw_data | string | 否 | 原始数据（Base64编码） |

## 2. 寄存器数据格式

### 2.1 通用寄存器

```json
{
    "R0": "0x20001234",
    "R1": "0x00000001",
    "R2": "0x00000000",
    "R3": "0x00000000",
    "R4": "0x20002000",
    "R5": "0x00000010",
    "R6": "0x00000000",
    "R7": "0x00000000",
    "R8": "0x00000000",
    "R9": "0x00000000",
    "R10": "0x00000000",
    "R11": "0x00000000",
    "R12": "0x00000000",
    "SP": "0x2001FFF0",
    "LR": "0x08002345",
    "PC": "0x08004567",
    "xPSR": "0x61000000"
}
```

### 2.2 特殊寄存器

```json
{
    "MSP": "0x2001FFF0",
    "PSP": "0x00000000",
    "PRIMASK": "0x00",
    "FAULTMASK": "0x00",
    "BASEPRI": "0x00",
    "CONTROL": "0x00"
}
```

### 2.3 故障状态寄存器

```json
{
    "CFSR": "0x00000200",
    "HFSR": "0x40000000",
    "DFSR": "0x00000000",
    "AFSR": "0x00000000",
    "MMFAR": "0x00000000",
    "BFAR": "0x00000000"
}
```

## 3. 堆栈回溯格式

### 3.1 地址列表格式

```json
{
    "stack_trace": [
        "0x08004567",
        "0x08002345",
        "0x08001234",
        "0x08000ABC"
    ]
}
```

### 3.2 详细信息格式

```json
{
    "stack_trace_detailed": [
        {
            "address": "0x08004567",
            "symbol": "HardFault_Handler",
            "file": "stm32h7xx_it.c",
            "line": 125
        },
        {
            "address": "0x08002345",
            "symbol": "process_data",
            "file": "data_processor.c",
            "line": 89
        },
        {
            "address": "0x08001234",
            "symbol": "main_loop",
            "file": "main.c",
            "line": 156
        }
    ]
}
```

## 4. 上下文信息格式

### 4.1 系统上下文

```json
{
    "context": {
        "interrupt_depth": 2,
        "current_task": "main_task",
        "system_state": "running",
        "uptime_ms": 12345678,
        "cpu_load_percent": 45.5
    }
}
```

### 4.2 外设状态

```json
{
    "peripheral_state": {
        "UART1": {
            "status": "active",
            "tx_count": 1234,
            "rx_count": 5678,
            "error_count": 0
        },
        "SPI1": {
            "status": "idle",
            "transfer_count": 100
        },
        "DMA1": {
            "status": "transferring",
            "channel": 3,
            "remaining_bytes": 256
        }
    }
}
```

### 4.3 内存状态

```json
{
    "memory_state": {
        "heap_used": 8192,
        "heap_total": 32768,
        "stack_used": 512,
        "stack_total": 4096,
        "msp_current": "0x2001FFF0",
        "msp_limit": "0x2001F000"
    }
}
```

## 5. 导出格式

### 5.1 JSON导出格式

```json
{
    "export_time": "2024-01-20T10:30:00",
    "export_version": "1.0",
    "device_info": {
        "mcu": "STM32H723",
        "firmware_version": "1.2.3",
        "build_date": "2024-01-15"
    },
    "total_errors": 15,
    "summary": {
        "by_severity": {
            "Critical": 2,
            "High": 5,
            "Medium": 6,
            "Low": 2
        },
        "by_source": {
            "CPU": 3,
            "Bus": 4,
            "Peripheral": 8
        }
    },
    "errors": [
        { "...": "..." }
    ]
}
```

### 5.2 CSV导出格式

```csv
ID,Timestamp,Type,Severity,Source,Description,PC,LR,SP
ERR_20240120_0001,2024-01-20T10:30:45,HardFault,Critical,CPU,Precise data bus error,0x08004567,0x08002345,0x2001FFF0
ERR_20240120_0002,2024-01-20T10:31:12,BusFault,High,Bus,Instruction bus error,0x08005678,0x08003456,0x2001FFE0
```

## 6. 错误ID生成规则

### 6.1 格式定义

```
ERR_YYYYMMDD_NNNN
```

- `ERR`: 固定前缀
- `YYYYMMDD`: 日期（年月日）
- `NNNN`: 当日序号（0001-9999）

### 6.2 示例

```
ERR_20240120_0001
ERR_20240120_0002
ERR_20240120_0003
```

## 7. 时间戳格式

### 7.1 ISO 8601格式

```
YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM
```

### 7.2 示例

```
2024-01-20T10:30:45.123456+08:00
2024-01-20T10:30:45.123456Z
```

## 8. 原始数据编码

### 8.1 Base64编码

原始二进制数据使用Base64编码存储：

```json
{
    "raw_data": "SDRSREFSREZBVUxUCg=="
}
```

### 8.2 十六进制编码

可选的十六进制字符串格式：

```json
{
    "raw_data_hex": "484152444641554C540A"
}
```
