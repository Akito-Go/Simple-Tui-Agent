## 0. 持久化修复（P0，阻塞会话恢复）

- [x] 0.1 `SessionManager` 新增 `_saved_message_count: int = 1`（system 不计入）；`to_log_records(since_index)` 仅导出 index ≥ since 的消息
- [x] 0.2 `save_session()` 改为增量追加；首次写入用 `w`，后续用 `a`；更新 `_saved_message_count`
- [x] 0.3 `to_log_records()` 补充 `tool_call_id`；新增 `meta` 记录写入 `turn_count`、`model`
- [x] 0.4 编写/更新 `test_session.py`：两次 save 不重复、tool_call_id 存在、meta 记录

## 1. /stop 命令

- [x] 1.1 `tui/commands.py` 新增 `STOP = "/stop"`；`/help` 补充说明
- [x] 1.2 `on_input_submitted`：**`/stop` 优先于 `_agent_running` 拦截**（运行中可执行 stop）
- [x] 1.3 `TuiAgentApp` 新增 `_stop_requested`、`_agent_task`；`_run_agent` / `_run_agent_continue` 保存 task 引用并重置 stop 标志
- [x] 1.4 `_handle_command(STOP)`：运行中设 `_stop_requested=True` + `cancel(_agent_task)`；空闲时提示「当前没有正在运行的任务」
- [x] 1.5 等待确认态：`/stop` 移除 ConfirmWidget、调用 `permission_guard.deny()`、终止任务
- [x] 1.6 `_process_events` 每次迭代前检查 stop，触发时显示系统消息、复位 header、`_agent_running=False`
- [x] 1.7 `AgentLoop` 每轮 turn 开始前检查 stop 标志（通过构造参数或回调注入），为 True 时 yield `AgentFinished` 并 save
- [x] 1.8 编写 `test_stop_command.py`：运行中终止、空闲提示、保留已完成工具结果、确认态 stop

## 2. 会话恢复

- [x] 2.1 新增 `session/loader.py`：`list_sessions()` 仅扫描 `session_*.jsonl`；`load_session(filepath, model)` 按 design 还原规则构建 SessionManager
- [x] 2.2 `init_agent()` 集成：有历史则进入 `_selecting_session`，显示列表；输入序号恢复或新建
- [x] 2.3 恢复后 `set_model(config.llm.model)`，chat 显示「已恢复会话 {id}」系统消息
- [x] 2.4 编写 `test_session_loader.py`：列表过滤、完整还原（含多 tool_call 合并）、旧日志兼容、turn_count 恢复

## 3. 上下文压缩

- [x] 3.1 新增 `session/compressor.py`：`estimate_tokens()`、`async compress_if_needed(session, llm_provider, threshold)`
- [x] 3.2 压缩策略：保留 system + 最近 2 轮完整对话；中间消息 LLM 摘要；保证 tool 对不被截断
- [x] 3.3 `AgentLoop.run()` / `_continue_loop()` 在 `build_messages()` 前 `await compress_if_needed(...)`（**不在 build_messages 内**）
- [x] 3.4 `config/schema.py` + `default.yaml` + `.env.example` + `loader.py` 新增 `context_max_tokens`（默认 8000）
- [x] 3.5 编写 `test_context_compressor.py`：估算、超阈值压缩、未超阈值跳过、保留最近 2 轮、摘要含路径/错误

## 4. 集成验证

- [x] 4.1 全量测试无回归
- [x] 4.2 端到端：启动选会话 → 多轮对话 → `/stop` → 检查 JSONL 无重复 → 长对话触发压缩
