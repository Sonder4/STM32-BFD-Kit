# embed-ai-tool -> BFD-Kit 收敛映射

## 目标

本文件用于明确：

- `embed-ai-tool` 中哪些能力已经吸收进 `BFD-Kit`
- 哪些能力只借鉴思路、不直接移植
- 哪些能力与 `BFD-Kit` 主定位冲突，因此明确排除

## 已吸收

以下能力已经按 `BFD-Kit` 命名和目录风格重写，而不是直接照搬：

- 安装/状态入口：
  - `scripts/bfd_install.py`
- 工具路径配置：
  - `scripts/bfd_tool_config.py`
- STM32 工程画像识别：
  - `scripts/bfd_project_detect.py`
- 统一 `STM32CubeCLT` 构建预检与 `elf/hex/bin` 一致性校验：
  - `scripts/bfd_cubeclt_build.py`
- 仓库发布前自检：
  - `scripts/bfd_repo_validate.py`
- Ubuntu/Windows 迁移说明：
  - `docs/platform_compatibility.md`

## 只借鉴思路，不直接移植

- 通用 embedded 仓库的 installer / config / detect / validate 分层思路
- 平台兼容文档的组织方式
- 发布前先做仓库门禁和路径自检的流程化习惯

这些部分在 `BFD-Kit` 中都已重新落在 `STM32 + 调试/采集/MCD` 的上下文里。

## 明确不吸收

- `IAR`
- 与 `BFD-Kit` 主线无关的宽泛 embedded 功能集合
- 第二套平行命名体系
- 会削弱当前 `J-Link HSS`、`DAPLink/PyOCD`、`telemetry ring`、`Matlab/Simulink/MCD` 主定位的功能堆叠

## BFD-Kit 保留的差异化能力

这些是 `BFD-Kit` 继续保留并优先发展的内容，不会为了贴近参考项目而淡化：

- `J-Link HSS` 原生固定地址高速采样
- `DAPLink/PyOCD` 的 float-count benchmark 与 HSS-compatible CSV/meta 输出
- `MCU telemetry ring` 模板与主机抓取链
- 面向 `STM32F4/STM32H7` 的技能化调试/采集路径
- 与 `Matlab/Simulink/System Identification/MCD` 的联动实验流
- `Keil` 兼容路径

## 当前收敛原则

1. 统一使用 `STM32CubeCLT` 作为 Ubuntu/Windows 共享构建主通道。
2. 保留 `Keil`，不引入 `IAR`。
3. 新基础设施优先做成：
   - Python CLI
   - 可测试
   - 可 dry-run
   - 可输出结构化结果
4. 先验证 `elf/hex/bin` 产物一致性，再宣称迁移成功。
