# stop-command Specification

## Purpose
TBD - created by archiving change add-stop-session-context. Update Purpose after archive.
## Requirements
### Requirement: /stop 命令终止 Agent 执行

系统 必须 (MUST) 支持 `/stop` 内置命令。当 Agent 正在运行（`_agent_running=True`）时，用户输入 `/stop` 必须 (MUST) 能够提交（优先于「Agent 正在运行」输入拦截），并在下一个 turn/事件边界终止任务，保留已完成的操作结果。

#### Scenario: 运行中执行 /stop
- **给定** Agent 正在执行多轮工具调用
- **当** 用户输入 `/stop`
- **那么** 系统 必须 (MUST) 终止当前 Agent Loop 与 `_agent_task`，Header 恢复 🟢 等待输入，chat 显示「任务已停止」

#### Scenario: 空闲时执行 /stop
- **给定** Agent 处于等待输入状态
- **当** 用户输入 `/stop`
- **那么** 系统 必须 (MUST) 提示「当前没有正在运行的任务」

#### Scenario: /stop 后保留已完成操作
- **给定** Agent 已完成 2 个工具调用，正在执行第 3 个
- **当** 用户输入 `/stop`
- **那么** 系统 必须 (MUST) 保留前 2 个工具调用的结果在 SessionManager 上下文中，并调用 `save_session`

#### Scenario: 等待确认时执行 /stop
- **给定** Agent 等待用户对 `shell_exec` 确认
- **当** 用户输入 `/stop`
- **那么** 系统 必须 (MUST) 移除确认组件、拒绝 pending 工具、终止任务，状态恢复等待输入

### Requirement: /stop 与后台 Loop 协作

系统 必须 (MUST) 通过 `asyncio.Task.cancel()` 和 Agent Loop turn 边界检查协作停止，不得 (MUST NOT) 仅停止 `_process_events` 消费而放任 Loop 在后台继续执行。

#### Scenario: stop 取消 agent task
- **给定** `_agent_task` 正在运行
- **当** `/stop` 触发
- **那么** 系统 必须 (MUST) 对 `_agent_task` 调用 `cancel()`，并在 Loop 内检测停止标志后退出

