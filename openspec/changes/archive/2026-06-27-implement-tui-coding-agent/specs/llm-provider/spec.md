## ADDED Requirements

### Requirement: OpenAI 兼容协议接入

系统 必须 (MUST) 通过 openai Python SDK 接入 OpenAI-compatible API 平台，使用 OpenAI 兼容的 chat completion API（含 function calling）。支持通过 `base_url` 和 `api_key` 配置连接参数。

#### Scenario: 发起 Chat Completion 请求
- **给定** 配置了 OpenAI-compatible API 的 base_url 和 api_key
- **当** Agent Loop 调用 `llm_provider.chat(messages, tools)`
- **那么** 系统 必须 (MUST) 通过 openai SDK 向指定 base_url 发起请求，携带 messages 和 tools 参数

### Requirement: 工具调用解析

系统 必须 (MUST) 从 LLM 响应中正确解析工具调用（tool_calls），提取每个工具调用的 name 和 arguments，并转换为结构化的 ToolCall 对象供 Agent Loop 使用。支持单次响应中包含多个工具调用。

#### Scenario: 解析单个工具调用
- **给定** LLM 返回包含一个 tool_call 的响应（name: "list_dir", arguments: {"path": "./"}）
- **当** Provider 解析响应
- **那么** 系统 必须 (MUST) 提取出 name="list_dir"、arguments={"path": "./"} 的 ToolCall 对象

#### Scenario: 解析多个工具调用
- **给定** LLM 返回包含两个 tool_calls 的响应
- **当** Provider 解析响应
- **那么** 系统 必须 (MUST) 提取出两个独立的 ToolCall 对象，按 LLM 返回的顺序排列

#### Scenario: 流式响应中的工具调用解析
- **给定** LLM 以流式方式返回 tool_calls（增量传输）
- **当** Provider 接收流式响应
- **那么** 系统 必须 (MUST) 累积 tool_call 的增量片段，在完成后组装为完整的 ToolCall 对象

### Requirement: 流式输出

系统 必须 (MUST) 支持流式输出（stream=True），逐 token 产出文本内容，使 TUI 能够实时渲染 LLM 回复。

#### Scenario: 流式文本渲染
- **给定** LLM 返回流式响应
- **当** 每个 token 到达
- **那么** 系统 必须 (MUST) 逐 token yield 给上层，TUI 实时显示

### Requirement: 超时控制

系统 必须 (MUST) 对 LLM 请求设置超时时间（通过配置 `timeout` 参数），超时后终止请求并返回错误信息。

#### Scenario: 请求超时
- **给定** 配置 `timeout` 为 30 秒
- **当** LLM 请求超过 30 秒未响应
- **那么** 系统 必须 (MUST) 终止请求并返回超时错误信息

### Requirement: 重试机制

系统 必须 (MUST) 在网络错误或临时故障时自动重试，使用指数退避策略，最多重试 `max_retries` 次。非网络错误（如 4xx 认证错误）不重试。

#### Scenario: 网络错误自动重试
- **给定** 配置 `max_retries` 为 3
- **当** LLM 请求因网络错误失败
- **那么** 系统 必须 (MUST) 自动重试，最多 3 次，使用指数退避间隔

#### Scenario: 认证错误不重试
- **给定** LLM 请求返回 401 认证错误
- **当** Provider 收到错误响应
- **那么** 系统 必须 (MUST) 不重试，直接返回认证错误信息
