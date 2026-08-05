## Context

项目目标要求从零实现 TUI 终端编码 Agent。项目当前为空仓库，需完整构建 Agent 系统。技术栈已确定为 Python 3.11+ / Textual / openai SDK / pydantic / loguru / pytest。核心约束：禁止使用任何第三方 Agent SDK 或 Framework 实现 Agent Loop、工具系统、权限控制和会话管理。

完整架构设计见 `docs/architecture.md`，本文档聚焦关键设计决策。

## Goals / Non-Goals

**Goals:**
- 实现完整的 Agent Loop（模型决策 → 工具调用 → 结果回传 → 继续推理）
- 实现 7 个代码仓库操作工具（list_dir / read_file / glob_search / grep_search / write_file / edit_file / shell_exec）
- 实现权限分级控制（只读自动执行，写入/Shell 需用户确认）
- 实现 TUI 全屏对话流界面（Header + Body + Footer）
- 实现 5 个内置命令（/help /clear /model /status /exit）
- 实现多轮会话管理与 JSONL 格式日志持久化
- 实现配置三级优先级（项目级 > 用户级 > 默认）
- 接入 OpenAI-compatible API 协议（openai SDK 兼容），支持流式输出/超时/重试
- API Key 仅环境变量读取，日志脱敏
- 完整测试覆盖（Mock LLM Provider）

**Non-Goals:**
- 不含 websearch、沙箱等非核心能力
- 不含 Git 操作、代码审查等高级功能
- 不含上下文压缩等扩展能力（可在基础稳定后扩展）
- 不含多模型并行/模型路由

## Decisions

### 1. 编程语言：Python 3.11+

**选择**：Python
**备选**：TypeScript/Node (ink)
**理由**：常见参考项目（OpenCode、Aider、Goose）多为 Python，社区熟悉度高；Textual 是当前最成熟的 Python TUI 框架；Python 异步生态（asyncio）适合 Agent Loop 的 I/O 密集型场景。

### 2. TUI 框架：Textual

**选择**：Textual
**备选**：Rich + Prompt Toolkit、ink (Node)
**理由**：Textual 提供完整的 CSS-like 布局系统、内置组件库、异步支持，是 Python TUI 的事实标准。全屏对话流布局可通过 `VerticalScroll` + `Input` + `Header`/`Footer` 组合实现。

### 3. TUI 布局：全屏对话流

**选择**：全屏对话流（类似 Claude Code 风格）
**备选**：单面板 + 侧边栏
**理由**：更贴近常见参考的 Claude Code / Cursor Agent 产品形态；实现更简单，可聚焦核心逻辑；工具调用和权限确认内联在对话流中，交互更自然。

### 4. LLM SDK：openai

**选择**：openai Python SDK
**备选**：anthropic SDK、httpx 直接请求
**理由**：OpenAI-compatible API 提供 OpenAI 兼容 API，openai SDK 原生支持 function calling（工具调用）、流式输出、超时和重试。无需额外适配层。

### 5. 配置格式：YAML + pydantic

**选择**：YAML + pydantic 模型
**备选**：TOML、JSON
**理由**：YAML 可读性好，Python 生态支持完善；pydantic 提供类型安全校验和默认值；三级优先级通过深度合并实现。

### 6. 日志库：loguru

**选择**：loguru
**备选**：structlog、标准 logging
**理由**：loguru 提供开箱即用的 JSONL 格式输出、日志脱敏 filter、简洁 API。无需额外配置即可满足 TUI 项目日志需求。

### 7. Agent Loop 架构：异步生成器模式

**选择**：`AsyncIterator[AgentEvent]` 流式产出事件
**备选**：回调模式、消息队列
**理由**：Python 异步生成器天然适合流式场景；TUI 层通过 `async for` 消费事件并渲染；事件类型（TextDelta / ToolCallStart / PermissionRequest 等）清晰定义状态转换。

### 8. 工具系统：注册表 + 基类模式

**选择**：`ToolRegistry` 注册表 + `ToolBase` 抽象基类
**备选**：装饰器注册、函数式
**理由**：基类定义统一接口（execute / to_openai_schema / permission_level），注册表管理工具生命周期。每个工具独立文件，便于测试和扩展。

### 9. 权限控制：基于 PermissionLevel 的策略模式

**选择**：`PermissionGuard` 根据 `PermissionLevel` 分流
**备选**：ACL、RBAC
**理由**：需求明确为三级（READ/WRITE/SHELL），策略模式简单直接。READ 自动放行，WRITE/SHELL 通过 TUI 的 `await` 机制等待用户确认。

### 10. 会话持久化：JSONL 格式

**选择**：JSONL（每行一条 JSON 记录）
**备选**：SQLite、Pickle
**理由**：JSONL 人类可读、易于追加、便于评审查看；每行独立，崩溃时不会丢失全部数据；无需额外依赖。

## Risks / Trade-offs

- **[风险] Textual 学习曲线**：Textual CSS-like 布局和异步模型有一定复杂度 → 缓解：使用最简单的 VerticalScroll + Input + Header/Footer 布局，不涉及复杂 CSS
- **[风险] openai SDK 与 OpenAI-compatible API 兼容性**：OpenAI-compatible API 可能不完全兼容 OpenAI 协议 → 缓解：通过 `base_url` 配置切换，必要时可降级为 httpx 直接请求
- **[风险] 大上下文 Token 超限**：多轮对话可能超出模型上下文窗口 → 缓解：当前版本不做上下文压缩（Non-Goal），通过 `max_turns` 限制轮次
- **[风险] Shell 执行安全性**：Shell 命令可能造成破坏 → 缓解：所有 Shell 命令需用户确认，后续可加命令白名单
- **[权衡] 简单优先 vs 可扩展性**：当前设计偏向简单，工具系统、Provider 等通过接口抽象预留扩展点，但不实现未要求的功能

## Open Questions

- OpenAI-compatible API 的具体 API base URL 和模型列表？（实施时从环境变量/配置获取）
- 是否需要支持多行输入？（当前设计为单行输入，可按需扩展）
