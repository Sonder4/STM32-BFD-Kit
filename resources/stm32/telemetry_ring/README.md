# MCU Telemetry Ring

这组资源用于把 MCU 侧高速变量采样改成“MCU 先写环形缓冲，主机再成块读取”的模式，适合 `STM32F4` 和 `STM32H7` 两类工程。

## 什么时候用

- 需要稳定记录 `1 kHz` 甚至更高频的控制环数据。
- `PyOCD` / `CMSIS-DAP` 的 host 轮询已经成为短板。
- 你更关心“样本不丢、时间序列完整”，而不是每次 host poll 都必须拿到最新单点值。

## 资源内容

- `bfd_telemetry_ring.h`
- `bfd_telemetry_ring.c`
- `BFD-Kit/scripts/bfd_telemetry_ring.py`

## MCU 侧集成

### 1. 定义 payload

```c
typedef struct
{
    float pos_rad;
    float vel_rads;
    float torque_nm;
    uint32_t state;
} AppTelemetryPayload_t;
```

### 2. 分配 ring image

```c
#define APP_TELEMETRY_CAPACITY 128u

static BfdTelemetryRingHeader_t g_app_ring_header;
static uint8_t g_app_ring_storage[BfdTelemetryRing_ImageSizeBytes(
    BfdTelemetryRing_MinRecordStride(sizeof(AppTelemetryPayload_t)),
    APP_TELEMETRY_CAPACITY
) - sizeof(BfdTelemetryRingHeader_t)];
static BfdTelemetryRing_t g_app_ring;
```

对 `STM32H7` 这类同时有 `DTCM` 与 `AXI SRAM/RAM_D1` 的目标，大容量 ring 不建议默认留在 `.bss`：

- 若工程链接脚本已经把 `.rtt_cb*` 放到 `RAM_D1`，可把 ring header/storage 显式放到 `.rtt_cb.<your_tag>`。
- 这样既能避免把 `DTCMRAM` 顶满，也更适合被调试主机稳定读取。
- 若目标工程启用了数据 cache，还要先确认当前 RAM 区对 debugger 可见，避免把 cache 可见性问题误判成采样脚本问题。

示例：

```c
#define APP_TELEMETRY_RAM_D1 __attribute__((section(".rtt_cb.app_telemetry"), aligned(4)))

APP_TELEMETRY_RAM_D1 static BfdTelemetryRingHeader_t g_app_ring_header;
APP_TELEMETRY_RAM_D1 static uint8_t g_app_ring_storage[
    BfdTelemetryRing_ImageSizeBytes(
        BfdTelemetryRing_MinRecordStride(sizeof(AppTelemetryPayload_t)),
        APP_TELEMETRY_CAPACITY
    ) - sizeof(BfdTelemetryRingHeader_t)
];
```

### 3. 初始化

```c
BfdTelemetryRing_Init(
    &g_app_ring,
    &g_app_ring_header,
    g_app_ring_storage,
    BfdTelemetryRing_MinRecordStride(sizeof(AppTelemetryPayload_t)),
    APP_TELEMETRY_CAPACITY);
```

### 4. 发布样本

```c
AppTelemetryPayload_t payload;

payload.pos_rad = pos_rad;
payload.vel_rads = vel_rads;
payload.torque_nm = torque_nm;
payload.state = state;

BfdTelemetryRing_Publish(
    &g_app_ring,
    time_us,
    0u,
    &payload,
    sizeof(payload));
```

## 主机侧抓取

```bash
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_telemetry_ring.py --json capture-pyocd \
  --address 0x24020000 \
  --field pos_rad:f32 \
  --field vel_rads:f32 \
  --field torque_nm:f32 \
  --field state:u32 \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 1.0 \
  --poll-period-us 1000 \
  --output RSCF_h7/logs/data_acq/app_ring_capture.csv
```

如果 payload 里有大批量连续 float，也可以直接展开数组字段：

```bash
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_telemetry_ring.py --json capture-pyocd \
  --address 0x24020000 \
  --field-array bench:f32:64 \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 1.0 \
  --poll-period-us 50000 \
  --output RSCF_h7/logs/data_acq/bench_ring_capture.csv
```

## 设计边界

- 这不是 probe-side HSS。`PyOCD` 仍然是 host 发起读。
- 真正的提速点是：MCU 先把高频样本写入 RAM ring，host 每次读的是“整段已整理好的 record image”。
- 当前主机脚本优先走增量 record 读取；只有在 ring 发生 wrap、布局变化或抓取缺口时，才回退到整块 image 重读。
- 对 `DAPLink` 来说，这通常比逐字段 `read32` 更适合作系统辨识、控制器调参和闭环误差分析。
