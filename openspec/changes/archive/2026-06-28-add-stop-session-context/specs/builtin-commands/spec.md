## ADDED Requirements

### Requirement: 终止命令

系统 必须 (MUST) 支持 `/stop` 内置命令。运行中优先于输入拦截；终止当前任务并保留已完成结果；空闲时提示无运行中任务；等待确认时取消 pending 工具。

#### Scenario: 运行中终止
- **给定** Agent 正在执行
- **当** 用户输入 `/stop`（不被「正在运行」拦截）
- **那么** 系统 必须 (MUST) 终止 Loop，状态恢复等待输入

#### Scenario: 空闲时提示
- **给定** Agent 等待输入
- **当** 用户输入 `/stop`
- **那么** 系统 必须 (MUST) 提示「当前没有正在运行的任务」

## MODIFIED Requirements

### Requirement: 退出命令

系统 必须 (MUST) 支持 `/exit` 内置命令（或 Ctrl+C），退出前自动保存当前会话日志。

#### Scenario: 退出程序
- **给定** 用户输入 `/exit`
- **当** 按下回车
- **那么** 系统 必须 (MUST) 保存当前会话（增量）到 `.tui-agent/logs/`，然后退出

### Requirement: 帮助命令

系统 必须 (MUST) 在 `/help` 中包含 `/stop` 命令说明。

#### Scenario: help 含 stop
- **给定** 用户输入 `/help`
- **当** 显示帮助
- **那么** 帮助文本 必须 (MUST) 包含 `/stop` 及使用场景说明
