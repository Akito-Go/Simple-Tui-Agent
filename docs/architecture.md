# TUI 终端编码 Agent — 架构设计文档

## 1. 概述

### 1.1 项目定位

从零实现一个最小可用的 TUI 终端编码 Agent。用户在终端交互界面中通过自然语言下达开发任务，Agent 结合代码仓库上下文自主规划执行步骤，完成工具调用并在结果基础上继续推理，直到任务完成、失败终止或给出明确回复。

### 1.2 核心约束

| 约束 | 说明 |
|------|------|
| **禁止 Agent SDK** | Agent Loop、工具系统、权限控制、会话管理必须自实现 |
| **TUI 终端界面** | 基于 Textual 的全屏对话流布局 |
| **7 个工具** | list_dir / read_file / glob / grep / write_file / edit_file / shell_exec |
| **权限分级** | 只读自动执行，写入/Shell 需用户确认 |
| **OpenAI 兼容 API** | 通过 openai SDK 兼容 OpenAI 协议接入 |
| **API Key 保护** | 仅环境变量，日志脱敏 |
| **工作区沙箱** | 文件路径与 Shell 工作目录边界校验；本机命令不受系统沙箱隔离 |

### 1.3 技术栈

| 维度 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 参考项目多为 Python，生态成熟 |
| TUI | Textual | 最成熟的 Python TUI 框架 |
| LLM SDK | openai | 兼容 OpenAI-compatible API (OpenAI 兼容 API) |
| 配置 | YAML + pydantic | 类型安全，可读性好 |
| 日志 | loguru | 简洁强大，支持 JSONL 输出 |
| 测试 | pytest + pytest-asyncio | Python 标配 |

---

## 2. 系统架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TUI 终端编码 Agent                            │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                     TUI Layer (Textual)                        │ │
│  │  ┌──────────────────────────────────────────────────────────┐ │ │
│  │  │  全屏对话流布局                                           │ │ │
│  │  │  ┌────────────────────────────────────────────────────┐  │ │ │
│  │  │  │  Header: 模型名 · 轮次 · 运行状态                   │  │ │ │
│  │  │  ├────────────────────────────────────────────────────┤  │ │ │
│  │  │  │  Body: 对话流 (用户输入/模型回复/工具调用/权限确认) │  │ │ │
│  │  │  ├────────────────────────────────────────────────────┤  │ │ │
│  │  │  │  Footer: 输入框 + 内置命令提示                     │  │ │ │
│  │  │  └────────────────────────────────────────────────────┘  │ │ │
│  │  └──────────────────────────────────────────────────────────┘ │ │
│  │  内置命令: /help /clear /sessions /stop /model /provider ...  │ │
│  └───────────────────────────────┬───────────────────────────────┘ │
│                                  │                                  │
│  ┌───────────────────────────────┼───────────────────────────────┐ │
│  │                         Core Layer                             │ │
│  │                               │                                │ │
│  │  ┌────────────────────────────┼─────────────────────────────┐ │ │
│  │  │                    Agent Loop (自实现)                    │ │ │
│  │  │                                                          │ │ │
│  │  │   用户输入 → 上下文组装 → LLM调用(流式) → 响应解析       │ │ │
│  │  │       ↑                                      ↓           │ │ │
│  │  │       │                              文本回复? 工具调用?   │ │ │
│  │  │       │                                      ↓           │ │ │
│  │  │       │                          ┌──────────┴────────┐   │ │ │
│  │  │       │                          ▼                   ▼   │ │ │
│  │  │       │                     文本展示           权限检查    │ │ │
│  │  │       │                          │            ┌──┴──┐    │ │ │
│  │  │       │                          │       只读自动 写入确认│ │ │
│  │  │       │                          │            └──┬──┘    │ │ │
│  │  │       │                          ▼               ▼       │ │ │
│  │  │       └────────────────── 结果注入上下文 ←── 工具执行     │ │ │
│  │  │                                                          │ │ │
│  │  └──────────────────────────────────────────────────────────┘ │ │
│  │                               │                                │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐    │ │
│  │  │ 权限控制  │ │ 会话管理 │ │ 配置管理 │ │ 日志系统     │    │ │
│  │  │ (Guard)  │ │(Session) │ │ (Config) │ │ (Logger)     │    │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘    │ │
│  └───────────────────────────────┬───────────────────────────────┘ │
│                                  │                                  │
│  ┌───────────────────────────────┼───────────────────────────────┐ │
│  │                       Infra Layer                              │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐     │ │
│  │  │ LLM      │ │ 工具执行器│ │ 文件系统 │ │ Shell        │     │ │
│  │  │ Provider │ │(ToolExec)│ │ (FS Ops) │ │ Runner       │     │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘     │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent Loop 状态机

```
                    ┌──────────┐
                    │   IDLE   │
                    └────┬─────┘
                         │ 用户输入
                         ▼
                 ┌───────────────┐
                 │  组装上下文    │
                 │ (系统提示+     │
                 │  历史+用户输入) │
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │  LLM 调用     │◄──────── 工具结果注入 ──────┐
                 │  (流式输出)   │                             │
                 └───────┬───────┘                             │
                         │                                     │
                    ┌────┴────┐                                │
                    │ 响应类型? │                                │
                    └────┬────┘                                │
                         │                                     │
              ┌──────────┼──────────┐                          │
              ▼          ▼          ▼                          │
        ┌─────────┐ ┌────────┐ ┌────────┐                     │
        │ 文本回复 │ │工具调用 │ │ 错误   │                     │
        └────┬────┘ └───┬────┘ └───┬────┘                     │
             │          │          │                           │
             ▼          ▼          ▼                           │
        ┌────────┐ ┌────────┐ ┌────────┐                      │
        │ 展示给  │ │权限检查│ │重试/   │                      │
        │ 用户   │ └───┬────┘ │终止    │                      │
        └───┬────┘     │      └────────┘                      │
            │     ┌────┴────┐                                  │
            │     │ 操作类型? │                                  │
            │     └────┬────┘                                  │
            │     ┌────┼────┐                                  │
            │     ▼         ▼                                  │
            │ ┌──────┐ ┌──────┐                                │
            │ │ 只读  │ │ 写入 │                                │
            │ │ 自动 │ │/Shell│                                │
            │ │ 执行 │ │需确认│                                │
            │ └──┬───┘ └──┬───┘                                │
            │    │         │                                    │
            │    │    ┌────┴────┐                               │
            │    │    │ 用户确认?│                               │
            │    │    └────┬────┘                               │
            │    │    ┌────┼────┐                               │
            │    │    ▼         ▼                               │
            │    │ ┌──────┐ ┌──────┐                            │
            │    │ │ 执行  │ │ 拒绝  │                           │
            │    │ └──┬───┘ └──┬───┘                            │
            │    │    │        │                                 │
            │    └────┼────────┘                                 │
            │         ▼                                          │
            │   ┌──────────┐                                     │
            │   │ 结果注入  │────────────────────────────────────┘
            │   │ 到上下文  │
            │   └──────────┘
            │
            ▼
      ┌──────────┐
      │ 对话结束  │
      │ 持久化日志│
      └──────────┘
```

---

## 3. 项目目录结构

```
tui-agent/
├── .ai_history/logs/              # 考核交付日志 (Cursor 对话摘要，本地)
├── .tui-agent/logs/               # TUI 产品对话日志 (JSONL，本地)
├── deliverables/                  # 本地交付物（.gitignore，不推远端）
├── docs/                          # 设计文档
│   └── architecture.md            # 本文档
├── openspec/                      # OpenSpec（本地，不推远端）
├── .github/                       # GitHub Actions 静态检查与跨平台测试
├── src/
│   └── tui_agent/                 # 主包
│       ├── __init__.py
│       ├── __main__.py            # 入口: python -m tui_agent
│       ├── app.py                 # Textual App 主类
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── loop.py            # Agent Loop 核心 (自实现)
│       │   └── types.py           # 核心类型定义
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py        # 工具注册表
│       │   ├── base.py            # 工具基类 + 权限级别定义
│       │   ├── list_dir.py        # 目录浏览
│       │   ├── read_file.py       # 文件读取
│       │   ├── glob_search.py     # 文件匹配 (glob pattern)
│       │   ├── grep_search.py     # 内容搜索 (grep)
│       │   ├── write_file.py      # 文件写入
│       │   ├── edit_file.py       # 文件编辑
│       │   ├── shell_exec.py      # Shell 命令执行
│       │   ├── shell_policy.py    # Shell 高危命令黑名单
│       │   ├── builtin.py         # 内置工具注册
│       │   └── workspace.py       # 工作区沙箱（路径边界校验）
│       ├── permissions/
│       │   ├── __init__.py
│       │   ├── guard.py           # 权限守卫
│       │   └── policy.py          # 权限策略定义
│       ├── session/
│       │   ├── __init__.py
│       │   ├── manager.py         # 会话管理 (上下文维护 + system prompt)
│       │   ├── storage.py         # JSONL 增量持久化 → .tui-agent/logs/
│       │   ├── loader.py          # 会话列表 + 恢复 + 消息序列规范化
│       │   └── compressor.py      # 上下文压缩 (token 估算 + LLM 摘要)
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py          # 配置加载 (项目级 > 用户级 > 默认)
│       │   └── schema.py          # 配置模型 (pydantic)
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── provider.py        # LLM Provider 抽象基类
│       │   ├── openai_compat.py   # OpenAI 兼容协议
│       │   ├── anthropic_compat.py# Anthropic Messages API
│       │   ├── factory.py         # Provider 工厂（按需导入）
│       │   └── retry.py           # 超时控制 + 重试逻辑
│       ├── tui/
│       │   ├── __init__.py
│       │   ├── app.py             # Textual App
│       │   ├── screens.py         # 界面定义
│       │   ├── widgets/
│       │   │   ├── chat.py        # 对话流组件
│       │   │   ├── input.py       # 输入框组件
│       │   │   └── header.py      # 状态栏组件
│       │   └── commands.py        # 内置命令 (/help /clear /sessions /stop /model ...)
│       └── logging/
│           ├── __init__.py
│           └── logger.py          # 日志系统 (loguru 配置 + 脱敏)
├── tests/
│   ├── conftest.py                # Mock LLM Provider
│   ├── test_agent_loop.py
│   ├── test_chat_widget.py
│   ├── test_config.py
│   ├── test_context_compressor.py
│   ├── test_llm_provider.py
│   ├── test_permissions.py
│   ├── test_session.py
│   ├── test_session_loader.py
│   ├── test_stop_command.py
│   ├── test_workspace.py
│   ├── test_shell_policy.py       # Shell 黑名单
│   ├── test_stop_cancel.py        # Esc//stop CancelledError 复位
│   └── test_tools.py              # 全量用例合计
├── config/
│   └── default.yaml               # 默认配置模板
├── pyproject.toml
└── README.md
```

---

## 4. 核心模块设计

### 4.1 Agent Loop (`agent/loop.py`)

**职责**：实现「模型决策 → 工具调用 → 结果回传 → 继续推理」的完整循环。

```
class AgentLoop:
    """Agent 主循环 — 自实现，不使用任何 Agent SDK/Framework"""

    max_turns: int              # 最大循环轮次 (来自配置)
    llm_provider: LLMProvider   # LLM 调用抽象
    tool_registry: ToolRegistry # 工具注册表
    permission_guard: PermissionGuard
    session: SessionManager

    async def run(user_input: str) -> AsyncIterator[AgentEvent]:
        """
        流式产出 AgentEvent 给 TUI 层渲染:
        - TextDelta: 流式文本片段
        - ToolCallStart: 工具调用开始
        - ToolCallResult: 工具执行结果
        - PermissionRequest: 权限确认请求
        - PermissionDenied: 权限被拒绝
        - AgentFinished: 任务完成
        - AgentError: 错误信息
        """
```

**关键流程**：

1. 用户输入 → `session.add_user_message()`
2. 循环 (最多 `max_turns` 轮)：
   - `compress_if_needed()` 检查上下文是否超阈值，必要时压缩早期消息
   - `session.build_messages()` 组装上下文
   - `llm_provider.chat(messages, tools, stream=True)` 流式调用
   - 解析响应：文本 → `TextDelta`；工具调用 → 权限检查 → 执行 → 结果注入 session
   - 纯文本结束 → `AgentFinished` → `save_session()` 持久化
3. 写入/Shell 需确认时 → `PermissionRequest` → TUI 等待 → `continue_with_confirmation()`

### 4.2 工具系统 (`tools/`)

**7 个工具，每个工具定义包含：名称、描述、参数 schema、权限级别、执行函数。**

| 工具 | 文件 | 权限级别 | 说明 |
|------|------|----------|------|
| `list_dir` | `list_dir.py` | READ | 列出目录内容 |
| `read_file` | `read_file.py` | READ | 读取文件内容 |
| `glob_search` | `glob_search.py` | READ | Glob 模式匹配文件 |
| `grep_search` | `grep_search.py` | READ | 文件内容正则搜索 |
| `write_file` | `write_file.py` | WRITE | 创建/覆盖文件 |
| `edit_file` | `edit_file.py` | WRITE | 编辑已有文件 |
| `shell_exec` | `shell_exec.py` | SHELL | 执行 Shell 命令 |

**工具基类**：

```python
class ToolBase:
    name: str
    description: str
    parameters: dict  # JSON Schema 格式
    permission_level: PermissionLevel  # READ | WRITE | SHELL

    async def execute(self, **kwargs) -> ToolResult: ...
    def to_openai_schema(self) -> dict: ...  # 转为 OpenAI function schema
```

### 4.2.1 工作区沙箱 (`tools/workspace.py`)

**设计目标**：将文件工具的路径及 Shell 工作目录限制在**项目启动目录**内；Shell 命令本身仍拥有当前用户的系统权限。

```
TUI 启动 (_do_init_agent)
    └── set_workspace_root(Path.cwd().resolve())

工具调用
    └── resolve_in_workspace(path)
            ├── 相对路径 → root / path → resolve()
            ├── 绝对路径 → resolve() 后校验 is_relative_to(root)
            └── 越界 → ToolResult.fail("路径超出工作区范围")

shell_exec
    ├── cwd 默认 = workspace root
    └── 指定 cwd 也必须通过 resolve_in_workspace
```

**与配置的关系**：沙箱**不读取**任何配置项，仅依赖进程 cwd；`.env` / YAML 配置行为不变。

**已知限制**：用户确认后本机 Shell 可访问工作区外资源。高危命令黑名单是辅助检查，不能替代容器或操作系统隔离。

### 4.3 权限控制 (`permissions/`)

```
┌────────────────────────────────────────────┐
│            权限分级策略                     │
├────────────┬──────────┬────────────────────┤
│   工具     │  级别    │   行为             │
├────────────┼──────────┼────────────────────┤
│ list_dir   │ READ     │ 自动执行 ✓         │
│ read_file  │ READ     │ 自动执行 ✓         │
│ glob_search│ READ     │ 自动执行 ✓         │
│ grep_search│ READ     │ 自动执行 ✓         │
├────────────┼──────────┼────────────────────┤
│ write_file │ WRITE    │ 需用户确认 ⚠       │
│ edit_file  │ WRITE    │ 需用户确认 ⚠       │
│ shell_exec │ SHELL    │ 需用户确认 ⚠       │
└────────────┴──────────┴────────────────────┘
```

**权限守卫流程**：

```python
class PermissionGuard:
    async def check(self, tool_call: ToolCall) -> PermissionDecision:
        tool = self.registry.get(tool_call.name)
        if tool.permission_level == PermissionLevel.READ:
            return PermissionDecision.ALLOW  # 自动执行
        else:
            # 发送确认请求到 TUI，等待用户响应
            return await self.request_user_confirmation(tool_call)
```

### 4.4 LLM Provider (`llm/`)

**接入 OpenAI 兼容 API 协议**：

```python
class OpenAICompatProvider(LLMProvider):
    """通过 openai SDK 接入 OpenAI 兼容 API (OpenAI 兼容 API)"""

    def __init__(self, config: LLMConfig):
        self.client = openai.AsyncOpenAI(
            base_url=config.api_base,   # API 地址
            api_key=config.api_key,     # 从环境变量读取
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        stream: bool = True,
    ) -> AsyncIterator[LLMResponse]: ...
```

**流式输出 / 超时 / 重试**：

- **流式输出**：`stream=True`，逐 token yield `TextDelta`
- **超时控制**：`timeout` 参数 + `asyncio.wait_for`
- **重试逻辑**：指数退避，最多 `max_retries` 次，仅对网络错误重试

### 4.5 会话管理 (`session/`)

**多轮上下文维护**（`manager.py`）：

- `SessionManager` 维护 OpenAI 格式消息列表
- system prompt 注入当前模型名，禁止 Agent 自称 Claude 等未配置身份
- `to_log_records()` 按对话顺序导出：`assistant 文本 → tool_call* → tool_result*`

**JSONL 增量持久化**（`storage.py`）：

- 路径：`.tui-agent/logs/session_{uuid}.jsonl`
- 原始历史独立追加，保存游标跟踪 `_transcript`；压缩检查点独立持久化，失败不推进游标
- 兼容旧格式（`tool_call` 在 `assistant` 之前）

**会话恢复**（`loader.py`）：

- `/sessions` 调用 `list_sessions()` 扫描历史（时间、模型、轮次、消息预览）；启动不自动弹出
- `load_session()` 还原消息 → `_sanitize_messages()` → `_normalize_message_sequence()` 合并连续 assistant，避免 API `bad_request`
- 恢复后 `_saved_message_count` 对齐，后续增量写入

**上下文压缩**（`compressor.py`）：

- 每轮推理前 `compress_if_needed()`，超 `context_max_tokens`（默认 32000）时摘要早期消息
- 保留最近 2 轮完整对话

```jsonl
{"type":"meta","session_id":"session_xxx","model":"deepseek/deepseek-v4-flash","turn_count":1}
{"type":"user","content":"帮我创建俄罗斯方块"}
{"type":"assistant","content":"我先看看项目结构"}
{"type":"tool_call","tool_call_id":"call_1","name":"list_dir","arguments":"{\"path\":\".\"}"}
{"type":"tool_result","tool_call_id":"call_1","name":"list_dir","result":"src/ tests/"}
{"type":"assistant","content":"项目结构清晰，我来创建..."}
```

### 4.6 配置管理 (`config/`)

**优先级**：

```
.env 环境变量  >  项目级 .tui-agent.yaml  >  用户级 ~/.tui-agent.yaml  >  配置模型内置默认值
```

**配置示例**（`config/default.yaml`，内置默认值统一在 `src/tui_agent/config/schema.py` 定义）：

```yaml
max_turns: 50
context_max_tokens: 32000
available_models:
  - gpt-4o-mini
  - gpt-4o
  - claude-sonnet-4-5
  - deepseek-chat
llm:
  provider: openai_compat   # 或 anthropic
  model: gpt-4o-mini
  api_base: https://api.openai.com/v1
  timeout: 120
  max_retries: 3
```

**API Key 保护**：
- OpenAI 兼容：`TUI_AGENT_API_KEY` / `OPENAI_API_KEY`
- Anthropic：`ANTHROPIC_API_KEY`（`provider=anthropic`）
- 不写入任何配置文件
- 日志输出前脱敏：`sk-xxx...` → `sk-***`

### 4.7 TUI 界面 (`tui/`)

**全屏对话流布局**：上方为可滚动对话流，下方依次为确认槽、输入框、状态相关快捷提示和状态栏。状态栏优先显示状态与模型，宽屏补充轮次及 Provider。

- `MainScreen` 在 resize 时切换 `narrow` / `short` 样式，缩减边距、确认预览高度并更新快捷提示。短窗口保留三个确认选项。
- `WelcomeWidget` 根据终端宽度切换左右双栏 / 上下紧凑布局（不足 84 列时紧凑显示，避免滚动条触发布局反复切换）；紧凑模式隐藏大字标，保留模型、路径、入门提示和最近活动。
- `HeaderWidget` 使用 Rich Text 显示状态色，按可用列宽隐藏次要字段并截断超长内容，模型名不解析 markup。
- `ToolResultWidget` 保留在原工具调用位置；点击或 Enter / 空格展开、收起返回内容。失败默认展开并使用错误色；显示区域最多 16 行，可独立滚动。
- 展开只影响 UI，不触发工具重跑、不读取结果路径，也不改变模型上下文。文件中更长的输出仍由 `read_file` 分段读取。
- 停止任务时移除工具卡片的运行态，同时复位助手 spinner。

操作说明和 Textual 导出的示例快照见 [UI 使用说明](ui-guide.md)。

**内置命令**：

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助信息 |
| `/clear` | 清空当前会话（并重置会话级全允） |
| `/sessions` | 列出/恢复历史会话（`/sessions <序号>` 可直接恢复） |
| `/stop` / `Esc` | 停止当前 Agent（Task.cancel + CancelledError 收尾复位 UI） |
| `/model` | 查看/切换模型（跨 Provider 重建客户端） |
| `/provider` | 查看/切换 `openai_compat` / `anthropic` |
| `/status` | 查看运行状态（含估算 tokens） |
| `/exit` | 退出程序 (或 Ctrl+C) |

**Shell 安全**：`shell_exec` 在权限确认前即经 `shell_policy` 黑名单拦截（`rm -rf /`、家目录删除、`curl|sh`、反弹壳、fork bomb 等）。「本会话全部允许」不绕过黑名单。

**会话恢复**（`/sessions`）：

- 启动始终进入新会话 + 欢迎页；不自动弹出历史列表
- `/sessions` 列出历史；输入序号恢复，`N` 取消；`/sessions <n>` 直接恢复

### 4.8 日志系统 (`logging/`)

**两层日志区分**：

```
┌────────────────────────────┬────────────────────────────────────┐
│  考核交付日志               │  TUI 项目日志                      │
│  .ai_history/logs/         │  .tui-agent/logs/                  │
├────────────────────────────┼────────────────────────────────────┤
│  记录: Cursor 对话摘要      │  记录: Agent 与用户的完整对话       │
│  用途: 讲师评审打分         │  用途: 用户回顾/恢复会话            │
│  格式: Markdown             │  格式: JSONL                       │
│  触发: 每轮对话结束手动导出 │  触发: 每次 Agent 交互自动保存      │
│  实现: 遵循 copilot-        │  实现: session/storage.py          │
│        instructions.md 约定 │                                    │
└────────────────────────────┴────────────────────────────────────┘
```

**日志脱敏规则**：
- API Key 模式：`sk-[a-zA-Z0-9]+` → `sk-***`
- Bearer Token：`Bearer [^\s]+` → `Bearer ***`
- 环境变量值：匹配已知敏感 key 的值进行替换

---

## 5. 测试策略

### 5.1 测试范围

| 测试模块 | 覆盖内容 |
|----------|----------|
| `test_agent_loop.py` | Agent 主循环：文本、工具、多轮、max_turns、异常 |
| `test_chat_widget.py` | TUI 展示：消息顺序、流式、spinner、markup 安全 |
| `test_tools.py` | 7 个工具正常/异常/权限 |
| `test_permissions.py` | 只读自动、写入确认、拒绝 |
| `test_config.py` | 配置优先级、.env、模型列表 |
| `test_session.py` | 消息累积、JSONL 导出顺序、增量持久化 |
| `test_session_loader.py` | 会话列表、恢复、旧日志兼容、消息合并 |
| `test_stop_command.py` | /stop 终止逻辑 |
| `test_context_compressor.py` | 上下文压缩阈值与保留轮次 |
| `test_workspace.py` | 工作区路径解析、越界拒绝、Shell cwd |
| `test_llm_provider.py` | Mock Provider 流式/重试 |

### 5.2 本地回归

`.github/workflows/tests.yml` 提供跨平台 CI；本地执行：

```bash
pip install -e ".[dev]"
pytest tests/ -v --tb=short
```

### 5.3 Mock LLM Provider

```python
# tests/conftest.py
@pytest.fixture
def mock_llm_provider():
    """Mock LLM Provider — 返回预设响应，不调用真实 API"""
    provider = MockLLMProvider()
    provider.set_responses([
        ToolCallResponse(name="list_dir", args={"./"}),
        TextResponse("项目结构如下..."),
        ToolCallResponse(name="write_file", args={"path":"tetris.py", ...}),
        TextResponse("俄罗斯方块已创建完成！"),
    ])
    return provider
```

---

## 6. 交付验证

### 6.1 验证任务

使用实现的 TUI Agent 完成一个 **俄罗斯方块游戏** 的创建：

1. 启动 TUI Agent
2. 输入：「帮我创建一个 Python 俄罗斯方块游戏，使用 pygame 库」
3. Agent 自动：浏览目录 → 创建 tetris.py → 用户确认写入 → 执行测试运行
4. 截图保存至 `deliverables/`

### 6.2 交付清单

| 交付物 | 路径 | 说明 |
|--------|------|------|
| 项目源码 | `src/tui_agent/` | 完整可运行源码 |
| 测试代码 | `tests/` | 覆盖核心模块 |
| AI 协作记录 | `.ai_history/logs/` | 每轮对话摘要 |
| TUI 产品日志 | `.tui-agent/logs/` | JSONL 格式对话记录 |
| 运行截图 | `deliverables/`（本地） | 小游戏实现/运行截图，不纳入公开仓 |
| OpenSpec / CI 脚手架 | `openspec/`（本地）、`.github/`（版本管理） | 本地规格与公开 CI |
| 设计文档 | `docs/architecture.md` | 本文档 |

---

## 7. 红线检查清单

- [x] Agent Loop 自实现（未使用 LangChain/AutoGPT/Agent SDK）
- [x] 工具系统自实现（未使用第三方 Tool 框架）
- [x] 权限控制自实现（未使用 Agent Framework 权限模块）
- [x] 会话管理自实现（未使用 Framework Memory 模块）
- [x] API Key 仅从环境变量读取
- [x] 日志脱敏处理
- [x] 7 个工具完整实现
- [x] 6 个内置命令完整实现（含 `/stop`）
- [x] 权限分级正确（只读自动，写入/Shell 确认）
- [x] 文件工具路径边界与 Shell 工作目录校验（无系统隔离）

运行时执行、保存、压缩及工具资源边界的最新细节见 [Runtime 改造说明](runtime-improvements.md)。


### 任务检查点与撤销

新增 `session/checkpoint.py`，由 AgentLoop 保存任务生命周期与对话快照，由内置文件工具的 `tracked_write` 保存写入前后内容。检查点独立于 JSONL 会话历史；恢复会创建新会话和新的续接检查点，不恢复运行中的 Python 栈或自动重放 Shell。

TUI 提供 `/resume`、`/undo`、`/undo list`、`/undo confirm`、`/undo cancel`。撤销预览与实际恢复都检查当前文件，后续修改导致冲突；磁盘失败后的部分恢复可重试。支持范围见 [UI 使用说明](ui-guide.md#任务检查点恢复与撤销)。
