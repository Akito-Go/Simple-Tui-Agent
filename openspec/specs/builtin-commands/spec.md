# builtin-commands Specification

## Purpose
TBD - created by archiving change implement-tui-coding-agent. Update Purpose after archive.
## Requirements
### Requirement: 帮助命令

系统 必须 (MUST) 在 `/help` 中包含 `/stop` 命令说明。

#### Scenario: help 含 stop
- **给定** 用户输入 `/help`
- **当** 显示帮助
- **那么** 帮助文本 必须 (MUST) 包含 `/stop` 及使用场景说明

### Requirement: 清空会话命令

系统 必须 (MUST) 支持 `/clear` 内置命令，清空当前会话上下文和 TUI 对话区显示，开始新会话。

#### Scenario: 清空会话
- **给定** 当前会话包含多轮对话
- **当** 用户输入 `/clear`
- **那么** 系统 必须 (MUST) 清空会话历史和 TUI 对话区，显示空对话界面

### Requirement: 会话恢复命令

系统 必须 (MUST) 支持 `/sessions` 内置命令：无参数时列出历史会话并进入选择态；带数字参数时直接恢复对应会话。

#### Scenario: 列出历史会话
- **给定** 存在可恢复会话
- **当** 用户输入 `/sessions`
- **那么** 系统 必须 (MUST) 显示序号列表，并等待用户输入序号或 N 取消

#### Scenario: 直接恢复
- **给定** 至少存在 1 个历史会话
- **当** 用户输入 `/sessions 1`
- **那么** 系统 必须 (MUST) 加载该会话并替换当前会话上下文

### Requirement: 模型查看与切换命令

系统 必须 (MUST) 支持 `/model` 内置命令。无参数时显示可用模型列表与当前模型；带参数时切换至指定模型。若模型隐含不同 Provider，系统 必须 (MUST) 重建 LLM 客户端。

#### Scenario: 查看当前模型
- **给定** 当前模型为 `gpt-4o`
- **当** 用户输入 `/model`
- **那么** 系统 必须 (MUST) 显示可用模型列表，并标注当前模型

#### Scenario: 切换模型
- **给定** 用户输入 `/model gpt-4o-mini`
- **当** 模型名称有效
- **那么** 系统 必须 (MUST) 切换至 `gpt-4o-mini` 并显示确认信息

### Requirement: Provider 切换命令

系统 必须 (MUST) 支持 `/provider` 内置命令，用于查看或切换 `openai_compat` / `anthropic`。

#### Scenario: 切换 Provider
- **给定** 当前 provider 为 `openai_compat`
- **当** 用户输入 `/provider anthropic`
- **那么** 系统 必须 (MUST) 切换 provider、校正 api_base，并重建 LLM 客户端

### Requirement: 状态查看命令

系统 必须 (MUST) 支持 `/status` 内置命令，显示当前运行状态，包括 Provider、当前模型、已用轮次/最大轮次、估算 Token 与配置摘要。

#### Scenario: 查看运行状态
- **给定** Agent 已完成 3 轮对话
- **当** 用户输入 `/status`
- **那么** 系统 必须 (MUST) 显示 Provider、模型名、轮次、估算 tokens 和关键配置项

### Requirement: 退出命令

系统 必须 (MUST) 支持 `/exit` 内置命令（或 Ctrl+C），退出前自动保存当前会话日志。

#### Scenario: 退出程序
- **给定** 用户输入 `/exit`
- **当** 按下回车
- **那么** 系统 必须 (MUST) 保存当前会话（增量）到 `.tui-agent/logs/`，然后退出

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

