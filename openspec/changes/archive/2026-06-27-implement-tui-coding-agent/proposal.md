## Why

项目目标要求从零实现一个最小可用的 TUI 终端编码 Agent。当前项目为空仓库，需要构建完整的 Agent 系统——包括 Agent Loop、工具调用、权限控制、TUI 交互界面、会话管理、配置管理和 LLM Provider 接入——以完成项目交付。

## What Changes

- 新增 TUI 终端编码 Agent 完整实现（Python + Textual）
- 新增 Agent Loop 核心循环（模型决策 → 工具调用 → 结果回传 → 继续推理）
- 新增 7 个代码仓库操作工具（list_dir / read_file / glob_search / grep_search / write_file / edit_file / shell_exec）
- 新增权限控制系统（只读自动执行，写入/Shell 需用户确认）
- 新增 TUI 全屏对话流界面（Header + Body + Footer 布局）
- 新增 5 个内置命令（/help /clear /model /status /exit）
- 新增会话管理与对话日志持久化（.tui-agent/logs/ JSONL 格式）
- 新增配置管理系统（项目级 > 用户级 > 默认，YAML + pydantic）
- 新增 LLM Provider 接入（openai SDK 兼容 OpenAI-compatible API 协议，流式输出/超时/重试）
- 新增日志脱敏机制（API Key 保护）
- 新增完整测试覆盖（Agent Loop / 工具 / 权限 / 配置 / 会话 / Mock LLM Provider）

## Capabilities

### New Capabilities
- `agent-loop`: Agent 主循环 — 上下文组装、LLM 调用、响应解析、工具结果回传的完整推理循环
- `tool-system`: 工具系统 — 7 个代码仓库操作工具的注册、schema 暴露、执行与错误处理
- `permission-control`: 权限控制 — 基于操作类型的分级权限策略，只读自动执行，写入/Shell 需用户确认
- `tui-interface`: TUI 终端交互界面 — 基于 Textual 的全屏对话流布局，展示用户输入、模型回复、工具调用、权限确认和运行状态
- `session-management`: 会话管理 — 多轮对话上下文维护与 .tui-agent/logs/ JSONL 格式持久化
- `config-management`: 配置管理 — 项目级/用户级/默认三级配置优先级，API Key 仅环境变量读取
- `llm-provider`: LLM Provider 接入 — openai SDK 兼容 OpenAI-compatible API 协议，支持流式输出、超时控制和重试
- `builtin-commands`: 内置命令 — /help /clear /model /status /exit 五个 TUI 内置命令
- `logging-system`: 日志系统 — 日志脱敏、结构化输出、两层日志（考核交付日志 + TUI 项目日志）区分

### Modified Capabilities
<!-- 无已有 capability 需要修改 -->

## Impact

- 新增目录：`src/tui_agent/`（主包）、`tests/`（测试）、`config/`（默认配置）
- 新增文件：`pyproject.toml`（项目配置与依赖）
- 新增运行时目录：`.tui-agent/logs/`（TUI 产品日志）
- 依赖库：textual、openai、pydantic、pyyaml、loguru、pytest、pytest-asyncio
- 交付验证：使用 Agent 创建俄罗斯方块游戏，截图保存至 `deliverables/`
