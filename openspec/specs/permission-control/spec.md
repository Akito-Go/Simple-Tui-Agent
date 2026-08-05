# permission-control Specification

## Purpose
TBD - created by archiving change implement-tui-coding-agent. Update Purpose after archive.
## Requirements
### Requirement: 权限分级策略

系统 必须 (MUST) 实现基于操作类型的权限分级策略：READ 级别工具（list_dir / read_file / glob_search / grep_search）自动执行无需确认；WRITE 级别工具（write_file / edit_file）需用户确认后执行；SHELL 级别工具（shell_exec）需用户确认后执行。用户 可以 (MAY) 选择「本次会话全部允许」，之后 WRITE/SHELL 在本会话内跳过确认，直至 `/clear` 或新会话；Shell 黑名单仍必须 (MUST) 生效，且命中黑名单时不得先弹出确认。

#### Scenario: 只读工具自动执行
- **给定** Agent 调用 `list_dir("./")`
- **当** 权限守卫检查该工具
- **那么** 系统 必须 (MUST) 自动放行，不弹出确认提示

#### Scenario: 写入工具需用户确认
- **给定** Agent 调用 `write_file("test.py", "content")`
- **当** 权限守卫检查该工具
- **那么** 系统 必须 (MUST) 在 TUI 中展示确认提示，等待用户响应

#### Scenario: Shell 工具需用户确认
- **给定** Agent 调用 `shell_exec("pytest", "./")`
- **当** 权限守卫检查该工具
- **那么** 系统 必须 (MUST) 在 TUI 中展示确认提示，等待用户响应

### Requirement: 用户确认交互

系统 必须 (MUST) 在需要确认时展示工具名称、参数摘要和操作描述，提供 [Y] 确认 / [N] 拒绝选项。用户确认后执行工具，用户拒绝后将拒绝结果注入会话上下文。

#### Scenario: 用户确认写入操作
- **给定** 权限守卫弹出 `write_file("tetris.py")` 确认提示
- **当** 用户按下 Y
- **那么** 系统 必须 (MUST) 执行文件写入，并将执行结果注入上下文

#### Scenario: 用户拒绝写入操作
- **给定** 权限守卫弹出 `write_file("tetris.py")` 确认提示
- **当** 用户按下 N
- **那么** 系统 必须 (MUST) 不执行文件写入，并将「用户拒绝了 write_file 操作」注入上下文

### Requirement: 拒绝结果进入上下文

系统 必须 (MUST) 在用户拒绝操作后，将拒绝信息作为工具结果注入会话上下文，使 LLM 能够感知拒绝并调整后续行为。

#### Scenario: 拒绝后 LLM 调整策略
- **给定** 用户拒绝了 `write_file` 操作
- **当** LLM 收到拒绝结果
- **那么** 系统 必须 (MUST) 使 LLM 在后续推理中感知到该操作被拒绝，不再重复尝试相同操作

