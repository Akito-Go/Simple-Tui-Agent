# tui-interface Specification

## Purpose
TBD - created by archiving change implement-tui-coding-agent. Update Purpose after archive.
## Requirements
### Requirement: TUI 全屏对话流布局

系统 必须 (MUST) 提供基于 Textual 的全屏对话流界面（Claude Code 风格）：Body 对话流居中占满、底部输入区、底部状态行（模型名、轮次、运行状态）。

#### Scenario: 界面初始化
- **给定** 用户启动 TUI Agent
- **当** 程序加载完成
- **那么** 系统 必须 (MUST) 展示对话区域、`>` 风格输入框，以及底部状态行

#### Scenario: 对话流实时更新
- **给定** Agent 正在处理用户请求
- **当** 产生 TextDelta、ToolCallStart、ToolCallResult 等事件
- **那么** 系统 必须 (MUST) 在 Body 区域实时追加渲染对应内容

### Requirement: 工具调用内联展示

系统 必须 (MUST) 在对话流中内联展示工具调用信息，使用 `● tool(...)` / `⎿ result` 树状样式，并支持权限确认框。

#### Scenario: 只读工具自动执行展示
- **给定** Agent 调用 `list_dir("./")`
- **当** 权限守卫自动放行并执行
- **那么** 系统 必须 (MUST) 在对话流中展示 `● list_dir(...)` 及 `⎿` 结果摘要

#### Scenario: 写入工具确认提示展示
- **给定** Agent 调用 `write_file("test.py")`
- **当** 权限守卫请求用户确认
- **那么** 系统 必须 (MUST) 展示双线边框确认框，含 Yes / allow session / No 选项及 Y/A/N 快捷键

### Requirement: 运行状态展示

系统 必须 (MUST) 在底部状态行实时展示当前模型名称、当前轮次/最大轮次和运行状态（running / ready / awaiting approval）。

#### Scenario: 运行中状态
- **给定** Agent 正在调用 LLM
- **当** 等待响应
- **那么** 系统 必须 (MUST) 在状态行显示 `running`

#### Scenario: 等待输入状态
- **给定** Agent 完成上一轮任务
- **当** 等待用户输入
- **那么** 系统 必须 (MUST) 在状态行显示 `ready`

