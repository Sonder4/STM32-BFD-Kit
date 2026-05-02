# STM32 Matlab / Simulink / MCD 标准工作流

## 1. 目标

本规范用于把 `Matlab`、`Simulink`、`System Identification Toolbox`、`BFD-Kit` 与 `STM32 MCU` 的协同开发流程收敛成一套可复用范式，适用于：

- 任意电机
- 任意传感器
- 任意控制器或观测器
- `PID` / `LQR` / `MPC` / `Kalman` / 自定义控制算法

核心要求不是“先写 C 再补图”，而是：

1. 先在 `Simulink` 中模块化建模。
2. 通过 `MCU` 把真实输入输出接入模型。
3. 完成 `HIL` 与数据回采。
4. 再做代码生成、集成、编译、烧录和复验。

## 2. 硬规则

- 算法设计阶段默认先走 `Simulink -> HIL -> 数据集 -> Matlab 分析 -> 代码生成`。
- `MCU` 侧真实 I/O 优先通过 `USB CDC`、`DAPLink/PyOCD`、`J-Link HSS`、`telemetry ring` 或 `ST-Link RTT` 接入，不允许只用 synthetic host 假数据就宣称闭环完成。
- 高频采样优先读 `SRAM` 全局变量、`telemetry ring` 或 `USB` 二进制流，不把带副作用的 `MMIO` 寄存器当长期高频观测面。
- 生成出的 `C/C++` 代码只能进入业务层包装，如 `USER/Modules`、`USER/APP` 或项目自有算法目录，不得直接写入 `Core/`、`Drivers/`、`USB_DEVICE/` 等 `CubeMX` 生成目录。
- `elf/hex/bin` 三件套不一致时，不允许直接进入烧录与实验结论阶段。

## 3. 标准流程

### 3.1 建模

在 `Simulink` 中至少拆出以下模块边界：

- stimulus / command
- sensor input
- plant or identified model
- controller / observer
- MCU bridge I/O
- logging / scope / dataset export

每个输入输出都要固定：

- 单位
- 采样周期
- 数据类型
- 饱和范围
- 丢样或故障标志

### 3.2 接入真实 MCU

根据目标频率和链路要求选一条主采样路径：

- 低到中频、少量变量：`DAPLink/PyOCD` 连续块读
- 无目标插桩、固定地址标量：`J-Link HSS`
- 中高频、强时间基一致性：`MCU telemetry ring + block dump`
- 更高吞吐或系统辨识主数据流：`USB CDC/bulk + DMA`

采样记录必须至少带上：

- `timestamp_us` 或等价时间基
- `seq`
- 输入列
- 输出列
- 关键状态列
- 丢样或错误标记

### 3.3 HIL 验证

HIL 至少分两步：

1. 短时 smoke，确认链路、变量命名、数据方向和异常处理可跑通。
2. 长时 run，确认丢样率、延迟、误差、稳定性和可重复性。

如果 host 轮询已经成为瓶颈，就停止继续拉高 host polling，改走：

- `telemetry ring`
- `USB CDC/bulk`
- 或 probe-side sampling

### 3.4 Matlab 分析与整定

数据集进入 `Matlab` 后，至少要完成下列其中一项：

- `system-id`
- `control`
- `kalman`
- `mcd-check`

推荐直接复用：

- `skills/codex/bfd-matlab-mcd/SKILL.md`
- `resources/matlab/templates/run_mcd_codegen_check.m`

Matlab 结论只能视为候选值，必须回到固件侧再验证。

### 3.5 代码生成与 MCU 集成

`Simulink` 代码生成后，集成策略统一为：

1. 生成代码进入独立算法目录或临时导出目录。
2. 在业务层写最薄适配器，把模型输入输出映射到工程数据结构。
3. 明确参数入口、状态存储、初始化入口和周期调度入口。
4. 用 `STM32CubeCLT + CMake/Ninja` 完成构建。

统一验证命令优先使用：

```bash
python3 BFD-Kit/scripts/bfd_cubeclt_build.py --json inspect --workspace .
python3 BFD-Kit/scripts/bfd_cubeclt_build.py --json build --workspace . --preset Debug --configure-if-needed --require-triplet
```

### 3.6 烧录与回采复验

烧录后至少验证：

- 构建产物与烧录文件一致
- 关键代码区 readback 一致
- 运行态日志或采样数据符合预期
- 与 Matlab 候选参数相比，无明显失稳、发散或异常饱和

如果参数失效，回到：

- `Simulink` 模型结构
- 数据分类
- 采样链路
- 控制器约束

不要直接在 MCU 代码里盲调。

## 4. 推荐工具入口

- 工程画像与构建预检：
  - `scripts/bfd_project_detect.py`
  - `scripts/bfd_cubeclt_build.py`
- 数据采集：
  - `skills/codex/bfd-data-acquisition`
  - `scripts/bfd_pyocd_hss.py`
  - `scripts/bfd_telemetry_ring.py`
- Matlab / Simulink / MCD：
  - `skills/codex/bfd-matlab-mcd`
- 烧录与复验：
  - `skills/codex/bfd-flash-programmer`
  - `scripts/bfd_repo_validate.py`

## 5. 交付判据

当一个新电机、传感器或算法满足下面条件时，才算进入了本规范的“闭环完成”状态：

- 已有 `Simulink` 模型或模板化模块图
- 已接入真实 `MCU` I/O
- 已完成至少一次短时与一次长时 `HIL`
- 已产出可归档数据集与 Matlab 结果
- 已完成 `C/C++` 生成集成
- 已完成 `STM32CubeCLT` 构建与烧录复验
- 已有回采证据证明参数或算法在真实板端成立
