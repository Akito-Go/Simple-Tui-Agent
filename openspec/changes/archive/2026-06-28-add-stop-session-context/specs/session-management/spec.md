## MODIFIED Requirements

### Requirement: 会话日志持久化

系统 必须 (MUST) 在 Agent 交互节点将**新增**会话记录以 JSONL 增量追加到 `.tui-agent/logs/{session_id}.jsonl`。工具相关记录 必须 (MUST) 含 `tool_call_id`；每次 save 写入 `meta` 记录（`turn_count`、`model`）。

#### Scenario: 对话结束后自动保存
- **给定** 用户完成一轮对话
- **当** Agent Loop 结束
- **那么** 系统 必须 (MUST) 仅追加本轮新增记录到 JSONL

#### Scenario: JSONL 格式正确性
- **给定** 会话含用户消息、工具调用、助手回复
- **当** 持久化
- **那么** 每行 必须 (MUST) 为合法 JSON，含 `type`、`timestamp`；工具记录含 `tool_call_id`

#### Scenario: 增量写入不重复
- **给定** 同一会话 save 两次
- **当** 读取 JSONL
- **那么** 第二次写入 必须 (MUST) 不包含第一次已写入的记录

#### Scenario: meta 记录
- **给定** turn_count=5，model=`deepseek/deepseek-v4-flash`
- **当** save_session 执行
- **那么** 必须 (MUST) 写入 `{"type":"meta","turn_count":5,"model":"..."}`
