## ADDED Requirements

### Requirement: Token 数估算

系统 必须 (MUST) 在压缩检查前估算消息 token 数，使用 `len(json.dumps(messages, ensure_ascii=False)) // 4`（字符估算法，允许 ±20% 误差）。

#### Scenario: 估算小消息列表
- **给定** 消息列表含 system + 1 轮对话（约 200 字符）
- **当** 调用 token 估算
- **那么** 系统 必须 (MUST) 返回约 50 tokens

### Requirement: 自动触发压缩

系统 必须 (MUST) 在 `AgentLoop` 调用 `build_messages()` 之前，通过 `await compress_if_needed()` 检查 token 数；超过 `context_max_tokens`（默认 8000）时触发压缩。

#### Scenario: 超阈值触发压缩
- **给定** `context_max_tokens=8000`，当前约 10000 tokens
- **当** 进入新一轮 Agent turn
- **那么** 系统 必须 (MUST) 在 `build_messages()` 前完成压缩

#### Scenario: 未超阈值不压缩
- **给定** `context_max_tokens=8000`，当前约 3000 tokens
- **当** 进入新一轮 Agent turn
- **那么** 系统 必须 (MUST) 不触发压缩

### Requirement: 压缩策略

系统 必须 (MUST) 保留 system prompt 和**最近 2 轮完整对话**（每轮从 user 消息到下一 user 之前的所有 assistant/tool 消息，保证 tool 对完整）；对更早消息调用 LLM 生成摘要。

#### Scenario: 保留最近 2 轮完整
- **给定** 消息列表含 6 轮对话
- **当** 触发压缩
- **那么** 最近 2 轮的 assistant/tool 消息 必须 (MUST) 原样保留，不被截断

#### Scenario: 摘要不截断 tool 对
- **给定** 第 3 轮含 assistant(tool_calls) + tool 结果
- **当** 该轮落入「最近 2 轮」保留区
- **那么** assistant 与对应 tool 消息 必须 (MUST) 成对保留

#### Scenario: 摘要包含技术细节
- **给定** 被压缩的早期消息含 `src/main.py` 和 `ModuleNotFoundError`
- **当** LLM 生成摘要
- **那么** 摘要 应该 (SHOULD) 包含上述关键信息

### Requirement: 配置项 context_max_tokens

系统 必须 (MUST) 支持 `TUI_AGENT_CONTEXT_MAX_TOKENS` 或 YAML `context_max_tokens`，默认 8000。该值为**压缩触发阈值**，非模型上下文窗口上限。

#### Scenario: 自定义压缩阈值
- **给定** `.env` 中 `TUI_AGENT_CONTEXT_MAX_TOKENS=4000`
- **当** 系统加载配置
- **那么** 系统 必须 (MUST) 使用 4000 作为压缩触发阈值

### Requirement: 压缩不在 build_messages 内执行

系统 必须 (MUST) 在 `AgentLoop` 内异步调用压缩，不得 (MUST NOT) 在同步 `build_messages()` 内发起 LLM 请求或修改 session。

#### Scenario: build_messages 无副作用
- **给定** 消息超阈值
- **当** 仅调用 `build_messages()`
- **那么** 系统 必须 (MUST) 不触发 LLM 调用，session 不变
