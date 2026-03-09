# BFD-Kit：AI STM32 调试工具包

简体中文 | [English](README-en.md)

BFD-Kit 是一个可移植、CLI 优先的 STM32 AI 调试工具包。
它统一了 `.ioc` 识别、运行配置生成、代码再生成、烧录、RTT 日志、寄存器/数据采集和故障证据归档流程，适合在嵌入式项目中作为一套可复用的调试与协作基础设施。

## 项目说明

本项目由 NCU Roboteam 在使用 DJI A 板及 DM MC-02 开发板过程中编写的 STM32 Skills，项目还存在很多可优化的内容，欢迎各位提出 issue。

## 适用范围

- 当前内置芯片族：`STM32F4`、`STM32H7`
- 支持代理：Codex、Claude
- 技能源目录：`skills/{codex,claude}/bfd-*`
- 运行时配置目录：`.codex/bfd/`
- 旧路径兼容镜像：`.codex/stm32/bootstrap/`

## 目录结构

- `skills/codex/`：Codex 技能源树
- `skills/claude/`：Claude 技能源树
- `resources/stm32/templates/`：芯片族模板（`f4/`、`h7/`）
- `init_project.sh`：一键项目接入入口
- `scripts/migrate_bfd_skills.py`：技能导入/回灌脚本
- `STM32_AGENT_PROMPT-zh.md`：面向 STM32 场景的中文代理提示词参考

## 技能列表

- `bfd-project-init`：扫描 `.ioc`、startup、linker、svd、cfg 和构建产物，生成统一调试配置
- `bfd-ioc-parser`：解析 `.ioc`，并把 JSON 结果落到 `.codex/bfd/ioc_json/`
- `bfd-cubemx-codegen`：基于现有 `.ioc` 以只读生成模式重新生成 CubeMX 管理代码
- `bfd-flash-programmer`：稳定的 J-Link / ST-Link 烧录流程
- `bfd-rtt-logger`：RTT 运行日志采集
- `bfd-debug-interface`：结构化调试流程与故障上下文处理
- `bfd-debug-executor`：一次性 J-Link 命令执行
- `bfd-register-capture`：外设寄存器采样与导出
- `bfd-data-acquisition`：运行时数据采集与分析
- `bfd-fault-logger`：HardFault / BusFault / UsageFault 归档
- `bfd-debug-orchestrator`：端到端调试编排
- `bfd-user-feedback`：用户反馈与状态回传

## 快速初始化

下面的命令假设你在 `BFD-Kit` 仓库根目录执行，并将技能安装到目标 STM32 项目中。

```bash
# 一条命令完成技能接入/更新，并刷新目标项目的 .codex/bfd 运行配置
bash ./init_project.sh --project-root /path/to/your/stm32-project

# 可选模式
bash ./init_project.sh --project-root /path/to/your/stm32-project --cutover-only
bash ./init_project.sh --project-root /path/to/your/stm32-project --bootstrap-only --force-refresh
```

## 标准流程

下面的命令在目标 STM32 项目根目录中执行。

```bash
# 1) 生成/刷新统一运行配置
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check

# 1.5) 可选：基于现有 .ioc 只读重新生成 CubeMX 管理代码
python3 ./.codex/skills/bfd-cubemx-codegen/scripts/generate_from_ioc.py --project-root . --log-dir logs/skills

# 2) 烧录
./build_tools/jlink/flash.sh builds/gcc/debug | tee logs/flash/flash_$(date +%Y%m%d_%H%M%S).log

# 3) RTT 日志
./build_tools/jlink/rtt.sh logs/rtt/rtt_$(date +%Y%m%d_%H%M%S).log 5 --mode quick

# 4) 一次性调试会话
./build_tools/jlink/debug.sh | tee logs/debug/debug_$(date +%Y%m%d_%H%M%S).log
```

## 运行配置约定

- 规范路径：
  - `.codex/bfd/active_profile.json`
  - `.codex/bfd/active_profile.env`
  - `.codex/bfd/bootstrap_report.md`
  - `.codex/bfd/ioc_json/`
- 兼容镜像：
  - `.codex/stm32/bootstrap/active_profile.json`
  - `.codex/stm32/bootstrap/active_profile.env`
- 自动刷新：
  - `build_tools/jlink/profile_env.sh` 会调用 `ensure_profile.py`
  - `rtt_plot_live.py` 会优先读取 `.codex/bfd/active_profile.env`

## 在现有项目中接入

下面的命令在 `BFD-Kit` 仓库根目录执行，用于把本工具包同步到目标项目中。

```bash
bash ./init_project.sh --project-root /path/to/your/stm32-project
python3 ./scripts/migrate_bfd_skills.py --repo-root /path/to/your/stm32-project --mode stage
python3 ./scripts/migrate_bfd_skills.py --repo-root /path/to/your/stm32-project --mode cutover
```

- `stage`：把目标项目当前 `.codex/.claude` 活动 BFD 技能导入到 `BFD-Kit/` 规范树
- `cutover`：把 `BFD-Kit/` 规范技能回灌到目标项目的活动镜像，并自动备份到 `archive/skills_migration/`

## 快速验证

```bash
bash ./init_project.sh --help
python3 ./scripts/migrate_bfd_skills.py --help
```

在目标 STM32 项目根目录中，还可以继续执行：

```bash
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
python3 ./.codex/skills/bfd-project-init/scripts/ensure_profile.py --project-root . --print-env-path
python3 ./.codex/skills/bfd-cubemx-codegen/scripts/generate_from_ioc.py --help
```

## 社区反馈

欢迎提交 issue 反馈问题、优化建议和使用体验。
如果你在实际项目中扩展了新的 STM32 调试、烧录、采集或 CubeMX 生成能力，也欢迎继续完善本项目。
