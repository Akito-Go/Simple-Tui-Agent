## ADDED Requirements

### Requirement: Agent 主循环执行

系统 必须 (MUST) 实现完整的 Agent Loop：接收用户输入后，组装上下文（系统提示 + 历史消息 + 用户输入），调用 LLM 获取响应，解析响应类型（文本/工具调用/结束），对工具调用执行权限检查和工具执行，将结果注入上下文后继续推理，直到任务完成或达到最大轮次。

#### Scenario: 用户输入触发完整推理循环
- **给定** 用户输入「帮我创建一个 Python 文件」
- **当** Agent Loop 开始执行
- **那么** 系统 必须 (MUST) 依次完成：上下文组装 → LLM 调用 → 响应解析 → 工具调用/文本回复 → 结果回传

#### Scenario: 达到最大轮次自动终止
- **给定** 配置 `max_turns` 为 3
- **当** Agent 完成第 3 轮推理后仍未结束
- **那么** 系统 必须 (MUST) 终止循环并提示用户已达到最大轮次

#### Scenario: LLM 返回纯文本回复
- **给定** LLM 返回不含工具调用的文本回复
- **当** Agent Loop 解析响应
- **那么** 系统 必须 (MUST) 将文本展示给用户并结束当前轮次

### Requirement: 流式事件产出

系统 必须 (MUST) 通过 `AsyncIterator[AgentEvent]` 流式产出事件给 TUI 层，事件类型包括：TextDelta（流式文本片段）、ToolCallStart（工具调用开始）、ToolCallResult（工具执行结果）、PermissionRequest（权限确认请求）、PermissionDenied（权限被拒绝）、AgentFinished（任务完成）、AgentError（错误信息）。

#### Scenario: 流式文本渲染
- **给定** LLM 返回流式文本响应
- **当** 每个 token 到达
- **那么** 系统 必须 (MUST) yield `TextDelta` 事件，TUI 层实时渲染

#### Scenario: 工具调用事件序列
- **给定** LLM 返回工具调用响应
- **当** Agent Loop 处理工具调用
- **那么** 系统 必须 (MUST) 依次 yield `ToolCallStart` → `PermissionRequest`（如需确认）→ `ToolCallResult`

### Requirement: 上下文组装

系统 必须 (MUST) 在每轮 LLM 调用前组装完整上下文，包含系统提示（定义 Agent 角色和能力）、历史消息（用户消息、助手回复、工具调用及结果）和当前用户输入。

#### Scenario: 多轮对话上下文累积
- **给定** 用户已完成 2 轮对话
- **当** 用户输入第 3 条消息
- **那么** 系统 必须 (MUST) 将前 2 轮的所有消息（用户输入、助手回复、工具调用、工具结果）包含在上下文中
