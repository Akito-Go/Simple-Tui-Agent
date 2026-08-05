## ADDED Requirements

### Requirement: TUI 全屏对话流布局

系统 必须 (MUST) 提供基于 Textual 的全屏对话流界面，包含 Header（模型名、轮次、运行状态）、Body（对话流：用户输入、模型回复、工具调用、权限确认）和 Footer（输入框、内置命令提示）。

#### Scenario: 界面初始化
- **给定** 用户启动 TUI Agent
- **当** 程序加载完成
- **那么** 系统 必须 (MUST) 展示 Header（显示模型名和状态）、空的 Body 区域和 Footer（显示输入框和命令提示）

#### Scenario: 对话流实时更新
- **给定** Agent 正在处理用户请求
- **当** 产生 TextDelta、ToolCallStart、ToolCallResult 等事件
- **那么** 系统 必须 (MUST) 在 Body 区域实时追加渲染对应内容

### Requirement: 工具调用内联展示

系统 必须 (MUST) 在对话流中内联展示工具调用信息，包括工具名称、参数、权限决策（自动执行/需确认/已拒绝）和执行结果。

#### Scenario: 只读工具自动执行展示
- **给定** Agent 调用 `list_dir("./")`
- **当** 权限守卫自动放行并执行
- **那么** 系统 必须 (MUST) 在对话流中展示 `⚡ list_dir("./") ✓ 自动执行` 及执行结果

#### Scenario: 写入工具确认提示展示
- **给定** Agent 调用 `write_file("test.py")`
- **当** 权限守卫请求用户确认
- **那么** 系统 必须 (MUST) 在对话流中展示 `⚡ write_file("test.py") ⚠ 需确认` 及 [Y]/[N] 选项

### Requirement: 运行状态展示

系统 必须 (MUST) 在 Header 中实时展示当前模型名称、当前轮次/最大轮次和运行状态（运行中/等待输入/已完成）。

#### Scenario: 运行中状态
- **给定** Agent 正在调用 LLM
- **当** 等待响应
- **那么** 系统 必须 (MUST) 在 Header 显示 🔴 运行中状态

#### Scenario: 等待输入状态
- **给定** Agent 完成上一轮任务
- **当** 等待用户输入
- **那么** 系统 必须 (MUST) 在 Header 显示 🟢 等待输入状态
