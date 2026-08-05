## ADDED Requirements

### Requirement: 日志脱敏

系统 必须 (MUST) 在日志输出前对敏感信息进行脱敏处理，包括 API Key（`sk-[a-zA-Z0-9]+` → `sk-***`）、Bearer Token（`Bearer [^\s]+` → `Bearer ***`）和其他已知敏感字段。

#### Scenario: API Key 脱敏
- **给定** 日志内容包含 `Authorization: Bearer sk-test123abc`
- **当** 日志输出
- **那么** 系统 必须 (MUST) 将 `sk-test123abc` 替换为 `sk-***`

#### Scenario: 环境变量值脱敏
- **给定** 日志内容包含 `TUI_AGENT_API_KEY=sk-secret`
- **当** 日志输出
- **那么** 系统 必须 (MUST) 将 key 值替换为 `***`

### Requirement: 两层日志区分

系统 必须 (MUST) 区分两层日志：考核交付日志（`.ai_history/logs/`，Markdown 格式，记录 Cursor 对话摘要）和 TUI 项目日志（`.tui-agent/logs/`，JSONL 格式，记录 Agent 对话历史）。两层日志的路径、格式和触发机制不同。

#### Scenario: TUI 项目日志自动保存
- **给定** Agent 完成一轮对话
- **当** Agent Loop 结束
- **那么** 系统 必须 (MUST) 自动将对话历史以 JSONL 格式写入 `.tui-agent/logs/`

#### Scenario: 考核交付日志独立管理
- **给定** 考核交付日志位于 `.ai_history/logs/`
- **当** TUI Agent 运行
- **那么** 系统 必须 (MUST) 不修改 `.ai_history/logs/` 中的内容（该目录由 Cursor 对话管理）

### Requirement: 日志结构化输出

系统 必须 (MUST) 使用 loguru 实现结构化日志输出，TUI 项目日志包含时间戳、日志级别、模块名和消息内容。

#### Scenario: 结构化日志格式
- **给定** Agent Loop 开始执行
- **当** 记录日志
- **那么** 系统 必须 (MUST) 输出包含 timestamp、level、module、message 字段的结构化日志
