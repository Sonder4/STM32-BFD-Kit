# BFD-Kit / embed-ai-tool 融合与跨平台扩展计划

## 1. 目标

本轮任务分为两条主线，同时推进：

1. 在当前 `BFD-Kit` 基础上，把 `MCU telemetry ring + DAPLink/PyOCD` 方案真正闭环到“可复用、可基准、可文档化”状态。
2. 参考 `https://github.com/LeoKemp223/embed-ai-tool`，吸收其高价值基础设施能力，补强 `BFD-Kit` 的安装、配置、项目探测、跨平台兼容和仓库发布体验。

## 2. 已知现状

### 2.1 已有能力

- `BFD-Kit/scripts/bfd_pyocd_hss.py`
  - 已支持 `sample`
  - 已支持 `benchmark-float`
  - 已支持 `--address-spec`
  - 已支持 `--project-file`
- `BFD-Kit/scripts/bfd_telemetry_ring.py`
  - 已支持 `layout`
  - 已支持 `capture-pyocd`
- `BFD-Kit/resources/stm32/telemetry_ring/`
  - 已有 `bfd_telemetry_ring.c`
  - 已有 `bfd_telemetry_ring.h`
  - 已有基础 README
- `README.md / README-en.md / README-zh.md`
  - 已经提到 `telemetry ring`
  - 已经提到 `benchmark-float`
  - 已经给出 `PyOCD` 基准参考值

### 2.2 当前缺口

- telemetry ring 仍主要停留在“模板 + 主机脚本”层，缺少一套面向 `H7/F4` 的通用集成范式。
- 当前 README 虽已提及 telemetry ring，但尚未形成更完整的跨平台安装/配置入口。
- `BFD-Kit` 还缺少类似 `embed-ai-tool` 的统一安装器、工具路径配置 CLI、项目探测模块和平台兼容文档入口。
- Windows / Linux 之间的 `STM32CubeCLT` 工具路径、命令差异、常见迁移问题还没有被统一抽象到 `BFD-Kit` 的基础设施层。
- GitHub 发布流程还没有完成“排除 `.learnings/*` 后再提交/推送”的显式整理。

## 3. 融合原则

### 3.1 吸收的部分

只吸收 `embed-ai-tool` 中真正适合 `BFD-Kit` 风格的基础设施能力：

- 安装 / 更新 / 状态检查脚本思路
- 工具路径配置 CLI 思路
- 共享的宿主平台兼容约定
- 统一项目探测与 profile 初始化思路
- 仓库结构校验与发布前自检思路

### 3.2 不吸收的部分

- 不把 `embed-ai-tool` 原样搬入 `BFD-Kit`
- 不引入 `IAR`
- 不把 `BFD-Kit` 改造成“泛嵌入式工具集合”
- 不破坏当前 `BFD-Kit` 的 `STM32 + 调试/采集/MCD` 主定位

### 3.3 保留的部分

- 保留 `Keil` 相关内容
- 保留当前 `J-Link / ST-Link / DAPLink / PyOCD / Matlab/MCD` 方向
- 保留当前 `BFD-Kit` 的脚本优先、技能辅助、日志可归档风格

## 4. 目标架构

### Phase A. 基础设施层

新增或补强以下公共能力：

- `scripts/bfd_install.py`
  - 安装 `BFD-Kit` 到目标工作区
  - 更新 / 状态检查
  - 可选同步技能与共享资源
- `scripts/bfd_tool_config.py`
  - 统一维护工作区级 / 用户级工具路径
  - 明确 `STM32CubeCLT`、`STM32CubeProgrammer`、`J-Link`、`pyocd` 等路径
- `scripts/bfd_project_detect.py`
  - 统一识别 `CMake / CubeMX / Keil / AC6 / GCC / STM32 家族`
  - 输出规范 profile
- `docs/platform_compatibility.md`
  - 明确 `Windows / Linux` 的路径、可执行名、串口命名、常见问题

### Phase B. Telemetry Ring 工程化

围绕现有 `resources/stm32/telemetry_ring/` 和 `scripts/bfd_telemetry_ring.py` 继续补强：

- H7/F4 的集成模板与命名规范
- 与控制环时间基对齐的推荐用法
- ring header / record / field 规范说明
- 与 `bfd_pyocd_hss.py` 的职责边界说明
- 基准采集、结果归档、报告格式统一

### Phase C. 跨平台 STM32CubeCLT 统一

把 `Ubuntu -> Windows` 迁移时最容易出问题的项，显式纳入 `BFD-Kit`：

- `arm-none-eabi-*`、`cmake`、`ninja`、`make` 的路径差异
- `STM32CubeProgrammer`、`STLink-gdb-server`、`JLink` 的路径差异
- Windows 路径空格、反斜杠、`.exe` 后缀
- CubeCLT 安装根目录约定
- `Keil` 工程保留，但不再扩展 `IAR`
- 常见链接脚本 / include path / line ending / shell 命令差异

### Phase D. 发布层

- 更新 `README.md / README-en.md / README-zh.md`
- 补 `BFD-Kit` 真源文档
- 同步到项目副本
- 发布前检查 `.learnings/*` 不进入 GitHub 提交

## 5. 执行顺序

### 第一步：先收 telemetry ring 现状

- 复核 `bfd_telemetry_ring.py`
- 复核 `resources/stm32/telemetry_ring/*`
- 复核 `bfd_pyocd_hss.py benchmark-float`
- 明确当前 `RSCF_h7` 上
  - host polling 上限
  - telemetry ring 预期收益
  - 下一轮实机基准命令

### 第二步：补公共基础设施

- 引入 `install/config/detect/platform-compatibility` 四件套
- 但按 `BFD-Kit` 命名与目录风格重写
- 不照抄 `embed-ai-tool` 命名

### 第三步：做 H7/F4 通用化

- 补 `telemetry ring` 集成模板
- 补通用字段声明 / 容量计算 / 发布接口说明
- 确保 F4 与 H7 都能直接复用

### 第四步：做实机基准

- 基准 A：当前 `PyOCD polling`
- 基准 B：当前 `telemetry ring + block dump`
- 输出：
  - 速度上限
  - 最短有效更新时间 `us`
  - 哪一段是瓶颈

### 第五步：更新 README 与发布

- 把安装、配置、跨平台、telemetry ring、benchmark 命令统一写进三份 README
- 清理 `.learnings/*` 的发布边界
- 最后再推送 GitHub

## 6. 验收标准

完成本轮任务时，至少满足：

1. `BFD-Kit` 真源中存在可运行的安装/配置/项目探测基础设施。
2. `telemetry ring` 在文档、模板、主机脚本三个层面都形成闭环。
3. `RSCF_h7` 上有新的 `DAPLink` 实机基准结果，明确：
   - host polling 上限
   - telemetry ring 路径上限
   - 最短有效更新时间 `us`
4. `H7` 和 `F4` 的通用化说明落入 `BFD-Kit` 资源或文档。
5. 三份 README 完成中英并存更新。
6. 真源与项目副本完成同步。
7. GitHub 推送时不包含 `.learnings/*`。

## 7. 当前建议

本轮不要再继续扩散到更多 probe 或更多 IDE。

当前最优推进顺序是：

1. 先把 `telemetry ring` 基准闭环做实
2. 再补 `install/config/detect/platform` 基础设施
3. 最后统一 README 与 GitHub 发布

这样可以优先解决“当前工程真正缺的能力”，而不是先做大而全的仓库重构。
