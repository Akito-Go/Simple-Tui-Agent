# session-restore Specification

## Purpose
TBD - created by archiving change add-stop-session-context. Update Purpose after archive.
## Requirements
### Requirement: 列出历史会话

系统 必须 (MUST) 在启动时扫描 `.tui-agent/logs/session_*.jsonl`，列出可恢复的历史会话（排除 `agent_*.jsonl` 等应用日志）。每个会话显示序号、session_id、最后活动时间和消息数量。

#### Scenario: 有历史会话时列出
- **给定** `.tui-agent/logs/` 中有 3 个 `session_*.jsonl` 文件
- **当** 系统启动
- **那么** 系统 必须 (MUST) 进入 `_selecting_session` 状态，在对话区显示会话列表

#### Scenario: 无历史会话时跳过
- **给定** `.tui-agent/logs/` 中无 `session_*.jsonl`
- **当** 系统启动
- **那么** 系统 必须 (MUST) 直接初始化新会话，不显示选择列表

#### Scenario: 排除应用日志文件
- **给定** 目录中同时存在 `session_123.jsonl` 和 `agent_2026-06-27.jsonl`
- **当** 列出会话
- **那么** 系统 必须 (MUST) 仅列出 `session_123.jsonl`

### Requirement: 从 JSONL 恢复会话

系统 必须 (MUST) 支持从 JSONL 加载历史会话，将扁平记录还原为 OpenAI 格式消息列表（含 assistant+tool_calls 合并）。

#### Scenario: 恢复完整会话
- **给定** JSONL 含 user、连续 tool_call、tool_result、assistant 记录
- **当** 用户选择恢复
- **那么** 系统 必须 (MUST) 正确还原 `SessionManager.messages` 和 `turn_count`

#### Scenario: 恢复后继续对话
- **给定** 已恢复会话含 5 轮对话
- **当** 用户输入新消息
- **那么** 系统 必须 (MUST) 在历史上下文基础上继续推理

#### Scenario: 恢复后使用当前模型 system prompt
- **给定** 配置模型为 `deepseek/deepseek-v4-flash`，JSONL meta 记录旧模型
- **当** 恢复会话
- **那么** 系统 必须 (MUST) 用当前模型调用 `set_model()` 重建 system prompt

### Requirement: JSONL 格式包含 tool_call_id 与 meta

系统 必须 (MUST) 在持久化时写入 `tool_call_id`；每次 save 写入 `meta` 记录含 `turn_count` 和 `model`。

#### Scenario: tool_call 记录含 tool_call_id
- **给定** Agent 执行 `list_dir`（tool_call_id="call_1"）
- **当** 会话持久化
- **那么** tool_call 和 tool_result 记录 必须 (MUST) 含 `"tool_call_id": "call_1"`

#### Scenario: 旧日志兼容加载
- **给定** 旧 JSONL 缺少 tool_call_id
- **当** 加载会话
- **那么** 系统 必须 (MUST) 用 `call_{index}` 顺序配对，不崩溃

### Requirement: 增量持久化（P0）

系统 必须 (MUST) 每次 `save_session` 仅追加自上次 save 以来的新记录，不得 (MUST NOT) 重复写入完整历史。

#### Scenario: 两次 save 不重复
- **给定** 会话完成一轮对话并 save，再完成一轮并 save
- **当** 读取 JSONL 行数
- **那么** 行数 必须 (MUST) 等于两轮新增记录之和，而非第二轮包含第一轮全量重复

