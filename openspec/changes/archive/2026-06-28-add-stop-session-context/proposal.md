## Why

当前 demo 在基础功能稳定后，需要增强三个关键能力：1) 缺少显式的 Agent 终止命令；2) 会话日志已持久化但存在重复写入 bug，且无法恢复历史会话；3) 多轮对话可能超出模型上下文窗口，需要上下文压缩机制。

## What Changes

- **P0** 修复 `save_session()` 增量写入，消除 JSONL 重复记录（会话恢复的前置条件）
- 新增 `/stop` 内置命令，运行中可安全终止（含等待确认态）
- 新增会话恢复，启动时从 `session_*.jsonl` 选择历史会话继续对话
- 新增上下文压缩，token 超阈值时在 Agent Loop 内异步压缩早期消息
- 新增 `context_max_tokens` 配置项（默认 8000，压缩触发阈值）
- 完善 JSONL schema（`tool_call_id`、`turn_count`、`meta` 记录）

## Capabilities

### New Capabilities
- `stop-command`: /stop 内置命令 — 安全终止当前任务，保留已完成操作
- `session-restore`: 会话恢复 — 启动时选择 `session_*.jsonl` 恢复 LLM 上下文
- `context-compression`: 上下文压缩 — 超阈值时将早期消息压缩为 LLM 摘要

### Modified Capabilities
- `session-management`: 增量持久化 + JSONL schema 完善（tool_call_id、meta、turn_count）
- `builtin-commands`: 新增 `/stop`，更新 `/help`
- `config-management`: 新增 `context_max_tokens`

## Impact

- 新增文件：`session/loader.py`、`session/compressor.py`
- 修改文件：`session/storage.py`、`session/manager.py`、`agent/loop.py`、`tui/commands.py`、`tui/app.py`、`config/*`
- 新增测试：`test_stop_command.py`、`test_session_loader.py`、`test_context_compressor.py`；更新 `test_session.py`
- 无新依赖；JSONL 增量写入对旧文件无破坏，旧格式 loader 兼容
