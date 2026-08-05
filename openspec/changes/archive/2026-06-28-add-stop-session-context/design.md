## Context

当前 TUI Agent demo 已完成核心功能（Agent Loop、7 工具、权限控制、TUI 界面、会话管理、配置管理），72+ 测试通过。现需在稳定基础上增量增强三个能力：`/stop` 命令、会话恢复、上下文压缩。

**前置问题（必须先修）**：现有 `save_session()` 使用 append 模式且每次写入全量 `to_log_records()`，导致 JSONL 重复膨胀。会话恢复依赖持久化正确性，因此持久化修复为 P0 阻塞项。

## Goals / Non-Goals

**Goals:**
- 新增 `/stop` 命令，用户可在 Agent 运行中安全终止（含等待确认态）
- 修复会话持久化为增量/覆盖写入，消除重复记录
- 新增会话恢复，启动时可选择 `session_*.jsonl` 历史会话继续对话
- 新增上下文压缩，token 超阈值时在 Agent Loop 内异步压缩早期消息
- 完善 JSONL schema（`tool_call_id`、`turn_count` 等）以支持无损还原

**Non-Goals:**
- 不重构 Agent Loop 主流程（决策 → 工具 → 回传），仅增加 stop 检查点与压缩钩子
- 不改变工具系统、权限控制、LLM Provider 接口
- 不引入新的外部依赖（压缩复用现有 LLM Provider；token 估算用字符法）
- 不做沙箱隔离、Git 集成、TUI 完整历史回放（恢复后仅保证 LLM 上下文正确）

## Decisions

### 0. 会话持久化：增量 checkpoint（P0，阻塞会话恢复）

**选择**：`SessionManager` 维护 `_saved_message_count`，`save_session()` 仅追加新增消息对应的 records；文件首次创建用 write，后续用 append
**备选**：每次全量覆盖写文件
**理由**：当前 append 全量导致 JSONL 指数重复，必须先修。增量写入与现有多次 `save_session()` 调用兼容，IO 更小。

### 1. /stop 命令：标志位 + Task 引用 + Loop 协作

**选择**：
1. `on_input_submitted` 中 **`/stop` 优先于 `_agent_running` 拦截**（运行中仍可输入 `/stop`）
2. `TuiAgentApp` 保存 `_agent_task: asyncio.Task | None`，stop 时对 task 执行 `cancel()` 并 `aclose()` 事件生成器
3. `AgentLoop` 每轮 turn 开始前检查 `_stop_requested`（由 App 注入或共享状态），为 True 时 yield `AgentFinished` 并 `save_session`
4. 等待确认态（`_waiting_confirmation`）：`/stop` 移除 ConfirmWidget、拒绝 pending 工具、终止任务

**备选**：仅在 `_process_events` 设标志位 return（无法停止后台 Loop）
**理由**：仅停止 UI 消费会导致 Agent Loop 在后台继续调用 LLM/工具。Task cancel + Loop 边界检查才能可靠终止。

**限制（文档化）**：正在进行的单次 LLM HTTP 请求无法立即中断，stop 在请求返回后的下一个 turn/事件边界生效（通常 <30s）。

### 2. 会话恢复：启动时内联选择 + 状态机

**选择**：
1. `init_agent()` 扫描 `.tui-agent/logs/session_*.jsonl`（**排除** `agent_*.jsonl` 等应用日志）
2. 有历史会话时进入 `_selecting_session` 状态，在 chat 显示序号列表（session_id、最后活动时间、消息数）
3. 用户输入序号恢复或 `0`/回车新建；恢复后 `SessionManager` 使用**当前配置模型**重建 system prompt（`set_model`）
4. **不回放** ChatWidget 历史（Non-Goal）；可选显示一行系统提示「已恢复会话 {id}，共 N 条消息」

**备选**：独立 Screen / CLI 参数 / 完整 TUI 回放
**理由**：内联选择最简单；LLM 上下文恢复是核心，UI 回放可后续迭代。

### 3. JSONL schema 与 loader 还原

**选择**：扩展 JSONL 记录格式：
```json
{"type":"tool_call","tool_call_id":"call_1","name":"list_dir","arguments":"{...}","timestamp":"..."}
{"type":"tool_result","tool_call_id":"call_1","name":"list_dir","result":"...","timestamp":"..."}
{"type":"meta","turn_count":5,"model":"deepseek/deepseek-v4-flash","timestamp":"..."}
```

**还原规则**（`session/loader.py`）：
1. 顺序扫描 JSONL，跳过非会话行（无 `type` 或 `type` 不在已知集合）
2. 连续 `tool_call` 记录合并为一条 `assistant` 消息（`tool_calls` 数组，`content` 可为空）
3. `tool_result` 按 `tool_call_id` 生成 `role: tool` 消息；缺 id 时用 `call_{index}` 并按顺序配对（兼容旧日志）
4. 文件末尾或首条 `meta` 记录恢复 `turn_count`；无 meta 时按 user 消息数估算
5. 加载后用当前 `config.llm.model` 调用 `set_model()`，不恢复旧 system prompt 文本

### 4. 上下文压缩：Loop 内 async 钩子（非 build_messages 副作用）

**选择**：
1. `session/compressor.py` 提供 `estimate_tokens(messages)` 和 `async compress_if_needed(session, llm_provider, threshold)`
2. 在 `AgentLoop.run()` / `_continue_loop()` 中，`build_messages()` **之前**调用 `await compress_if_needed(...)`
3. **不在**同步 `build_messages()` 内做压缩（避免 async 调用与副作用）

**压缩策略**：
- 保留 system prompt + **最近 2 轮完整对话**（一轮 = 从 user 消息到下一个 user 之前的所有 assistant/tool 消息，保证 tool 对完整）
- 更早消息调用 LLM 生成摘要，插入一条 `role: user` 的 `[历史摘要]` 消息（或专用 `summary` 类型转写）
- 压缩后 token 数 SHOULD 低于阈值的 80%；未达标可二次压缩或截断摘要
- token 估算：`len(json.dumps(messages, ensure_ascii=False)) // 4`（中文偏差可接受，标注为估算）

### 5. 实施顺序（修订）

1. **P0** 持久化修复（增量 save + JSONL schema）
2. `/stop` 命令（含输入优先级、Task cancel、Loop 检查点）
3. 会话恢复（loader + 启动选择状态机）
4. 上下文压缩（compressor + Loop 钩子 + 配置项）

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| `/stop` 无法中断单次 LLM HTTP 请求 | 文档化延迟；UI 立即反馈「正在停止…」 |
| Task.cancel 导致 GeneratorExit | Loop 内 try/finally 确保 `save_session` 与状态复位 |
| 旧 JSONL 无 tool_call_id | loader 用 `call_{index}` 顺序配对；单测覆盖 |
| 压缩摘要丢细节 | prompt 明确要求保留路径/错误/决策；保留最近 2 轮完整 |
| `context_max_tokens=8000` 与模型实际上下文窗不一致 | 配置项文档注明为「压缩触发阈值」，非模型上限 |
| 恢复后会话 ID 与文件 | 恢复时复用原 session_id，后续 save 继续追加同一文件 |
