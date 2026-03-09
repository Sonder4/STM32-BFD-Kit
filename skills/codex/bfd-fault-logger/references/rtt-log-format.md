# RTT日志格式

本文档定义了RTT（Real-Time Transfer）日志的格式规范。

## 1. RTT概述

RTT（Real-Time Transfer）是SEGGER提供的一种高效调试日志传输机制，允许目标设备通过调试探针实时传输日志数据到主机。

## 2. 缓冲区配置

### 2.1 默认缓冲区配置

| 缓冲区索引 | 名称 | 大小 | 用途 |
|-----------|------|------|------|
| 0 | error | 1024字节 | 错误日志 |
| 1 | warn | 2048字节 | 警告日志 |
| 2 | info | 4096字节 | 信息日志 |
| 3 | debug | 2048字节 | 调试日志 |

### 2.2 缓冲区方向

```
┌─────────────────────────────────────────────────────────┐
│                      Target Device                       │
│  ┌─────────────────────────────────────────────────┐    │
│  │              RTT Control Block                   │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐│    │
│  │  │Buffer 0 │ │Buffer 1 │ │Buffer 2 │ │Buffer 3││    │
│  │  │ (error) │ │ (warn)  │ │ (info)  │ │(debug) ││    │
│  │  │  UP     │ │  UP     │ │  UP     │ │  UP    ││    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └───┬────┘│    │
│  └───────┼───────────┼───────────┼──────────┼─────┘    │
│          │           │           │          │           │
└──────────┼───────────┼───────────┼──────────┼───────────┘
           │           │           │          │
           ▼           ▼           ▼          ▼
    ┌─────────────────────────────────────────────┐
    │              Debug Probe (J-Link)           │
    └─────────────────────┬───────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────┐
    │                  Host PC                     │
    │  ┌─────────────────────────────────────┐   │
    │  │         RTT Logger Application       │   │
    │  └─────────────────────────────────────┘   │
    └─────────────────────────────────────────────┘
```

## 3. 日志级别定义

### 3.1 级别枚举

| 级别 | 值 | 宏定义 | 描述 |
|------|---|--------|------|
| ERROR | 0 | LOGERROR | 严重错误，需要立即处理 |
| WARN | 1 | LOGWARN | 警告信息，潜在问题 |
| INFO | 2 | LOGINFO | 一般信息，调试辅助 |
| DEBUG | 3 | LOGDEBUG | 详细调试信息 |
| TRACE | 4 | LOGTRACE | 最详细的跟踪信息 |

### 3.2 级别过滤

```c
#define RTT_LOG_LEVEL_ERROR  0
#define RTT_LOG_LEVEL_WARN   1
#define RTT_LOG_LEVEL_INFO   2
#define RTT_LOG_LEVEL_DEBUG  3
#define RTT_LOG_LEVEL_TRACE  4

#ifndef RTT_LOG_LEVEL
#define RTT_LOG_LEVEL RTT_LOG_LEVEL_INFO
#endif
```

## 4. 日志消息格式

### 4.1 标准格式

```
[TIMESTAMP] [LEVEL] [MODULE] Message
```

### 4.2 格式示例

```
[10:30:45.123] [ERROR] [UART] DMA transfer failed, error code: 0x05
[10:30:45.456] [WARN] [SPI] Buffer nearly full, 90% used
[10:30:46.000] [INFO] [MAIN] System initialized successfully
[10:30:46.500] [DEBUG] [ADC] Sample value: 2048, voltage: 1.65V
```

### 4.3 紧凑格式

```
[E] UART: DMA error 0x05
[W] SPI: Buffer 90%
[I] MAIN: Init OK
[D] ADC: val=2048
```

## 5. 日志消息结构

### 5.1 JSON格式

```json
{
    "timestamp": "2024-01-20T10:30:45.123",
    "level": "ERROR",
    "module": "UART",
    "message": "DMA transfer failed, error code: 0x05",
    "buffer_index": 0,
    "raw_data": "[10:30:45.123] [ERROR] [UART] DMA transfer failed, error code: 0x05"
}
```

### 5.2 字段说明

| 字段 | 类型 | 描述 |
|------|------|------|
| timestamp | string | 日志时间戳 |
| level | string | 日志级别 |
| module | string | 模块名称 |
| message | string | 日志消息内容 |
| buffer_index | integer | RTT缓冲区索引 |
| raw_data | string | 原始日志数据 |

## 6. 特殊日志格式

### 6.1 错误日志格式

```
[ERROR] [MODULE] ErrorType: Description
        └─ Address: 0xXXXXXXXX
        └─ Code: 0xXX
        └─ Context: ...
```

示例：
```
[ERROR] [DMA] TransferError: Channel 3
        └─ Address: 0x20001234
        └─ Code: 0x05
        └─ ISR: 0x0000000A
```

### 6.2 堆栈跟踪格式

```
[ERROR] [SYSTEM] Stack Trace:
        #0  0x08004567 in HardFault_Handler()
        #1  0x08002345 in process_data()
        #2  0x08001234 in main_loop()
        #3  0x08000ABC in main()
```

### 6.3 寄存器转储格式

```
[ERROR] [SYSTEM] Register Dump:
        R0  = 0x20001234  R1  = 0x00000001  R2  = 0x00000000  R3  = 0x00000000
        R4  = 0x20002000  R5  = 0x00000010  R6  = 0x00000000  R7  = 0x00000000
        R8  = 0x00000000  R9  = 0x00000000  R10 = 0x00000000  R11 = 0x00000000
        R12 = 0x00000000  SP  = 0x2001FFF0  LR  = 0x08002345  PC  = 0x08004567
        xPSR = 0x61000000
```

## 7. 模块命名规范

### 7.1 标准模块名称

| 模块 | 名称 | 描述 |
|------|------|------|
| MAIN | 主程序 | 主循环和初始化 |
| INIT | 初始化 | 系统初始化代码 |
| UART | 串口 | UART外设 |
| SPI | SPI | SPI外设 |
| I2C | I2C | I2C外设 |
| DMA | DMA | DMA控制器 |
| ADC | ADC | ADC外设 |
| TIM | 定时器 | 定时器外设 |
| GPIO | GPIO | GPIO端口 |
| FLASH | Flash | Flash存储 |
| SYSTEM | 系统 | 系统级错误 |
| RTOS | RTOS | 实时操作系统 |
| NET | 网络 | 网络协议栈 |
| FS | 文件系统 | 文件系统 |

### 7.2 自定义模块命名

自定义模块名称应遵循以下规则：
- 全大写字母
- 最长8个字符
- 不包含特殊字符
- 具有描述性

## 8. 时间戳格式

### 8.1 完整时间戳

```
HH:MM:SS.mmm
```

示例：
```
10:30:45.123
```

### 8.2 相对时间戳

```
+MMMMM.mmm
```

示例：
```
+00123.456  (相对于系统启动)
```

### 8.3 Unix时间戳

```
UNIX:1705735845
```

## 9. 日志输出宏定义

### 9.1 标准宏

```c
#define LOGERROR(fmt, ...) SEGGER_RTT_printf(0, "[ERROR] " fmt "\n", ##__VA_ARGS__)
#define LOGWARN(fmt, ...)  SEGGER_RTT_printf(1, "[WARN] " fmt "\n", ##__VA_ARGS__)
#define LOGINFO(fmt, ...)  SEGGER_RTT_printf(2, "[INFO] " fmt "\n", ##__VA_ARGS__)
#define LOGDEBUG(fmt, ...) SEGGER_RTT_printf(3, "[DEBUG] " fmt "\n", ##__VA_ARGS__)
```

### 9.2 带模块的宏

```c
#define LOG_ERROR(module, fmt, ...) \
    SEGGER_RTT_printf(0, "[%s] [ERROR] " fmt "\n", module, ##__VA_ARGS__)
#define LOG_WARN(module, fmt, ...) \
    SEGGER_RTT_printf(1, "[%s] [WARN] " fmt "\n", module, ##__VA_ARGS__)
#define LOG_INFO(module, fmt, ...) \
    SEGGER_RTT_printf(2, "[%s] [INFO] " fmt "\n", module, ##__VA_ARGS__)
#define LOG_DEBUG(module, fmt, ...) \
    SEGGER_RTT_printf(3, "[%s] [DEBUG] " fmt "\n", module, ##__VA_ARGS__)
```

### 9.3 带时间戳的宏

```c
#define LOG_TS_ERROR(module, fmt, ...) \
    SEGGER_RTT_printf(0, "[%08lu] [%s] [ERROR] " fmt "\n", \
                      HAL_GetTick(), module, ##__VA_ARGS__)
```

## 10. 性能考虑

### 10.1 缓冲区大小建议

| 日志类型 | 建议大小 | 原因 |
|----------|----------|------|
| ERROR | 512-1024字节 | 错误较少，但信息重要 |
| WARN | 1024-2048字节 | 警告可能较多 |
| INFO | 2048-4096字节 | 信息日志量大 |
| DEBUG | 1024-2048字节 | 调试时使用 |

### 10.2 日志频率控制

```c
#define LOG_THROTTLE(interval_ms, log_call) \
    do { \
        static uint32_t last_log_time = 0; \
        uint32_t now = HAL_GetTick(); \
        if (now - last_log_time >= interval_ms) { \
            last_log_time = now; \
            log_call; \
        } \
    } while(0)

// 使用示例
LOG_THROTTLE(1000, LOG_INFO("ADC", "Value: %d", adc_value));
```

## 11. RTT控制块结构

### 11.1 控制块定义

```c
typedef struct {
    char        acID[16];           // "SEGGER RTT"
    int32_t     MaxNumUpBuffers;    // 上行缓冲区数量
    int32_t     MaxNumDownBuffers;  // 下行缓冲区数量
    SEGGER_RTT_BUFFER_UP   aUp[BUFFER_COUNT_UP];   // 上行缓冲区
    SEGGER_RTT_BUFFER_DOWN aDown[BUFFER_COUNT_DOWN]; // 下行缓冲区
} SEGGER_RTT_CB;
```

### 11.2 缓冲区结构

```c
typedef struct {
    char*    pBuffer;       // 缓冲区指针
    int32_t  SizeOfBuffer;  // 缓冲区大小
    int32_t  WrOff;         // 写偏移
    int32_t  RdOff;         // 读偏移
    int32_t  Flags;         // 标志位
} SEGGER_RTT_BUFFER_UP;
```
