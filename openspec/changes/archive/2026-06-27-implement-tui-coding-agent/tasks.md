## 1. 项目初始化

- [x] 1.1 创建 `pyproject.toml`，配置项目元数据与依赖（textual、openai、pydantic、pyyaml、loguru、pytest、pytest-asyncio）
- [x] 1.2 创建 `src/tui_agent/` 包结构和 `__init__.py` 文件
- [x] 1.3 创建 `config/default.yaml` 默认配置模板
- [x] 1.4 创建 `tests/` 目录和 `conftest.py`（Mock LLM Provider fixtures）
- [x] 1.5 创建 `.tui-agent/logs/` 目录的 `.gitkeep`

## 2. 配置管理

- [x] 2.1 实现 `config/schema.py`：pydantic 配置模型（LLMConfig、AppConfig）
- [x] 2.2 实现 `config/loader.py`：三级配置加载（项目级 > 用户级 > 默认），深度合并
- [x] 2.3 实现 API Key 从环境变量读取（`TUI_AGENT_API_KEY`），配置文件中不存储
- [x] 2.4 编写 `test_config.py`：配置优先级、默认值、环境变量读取测试

## 3. LLM Provider

- [x] 3.1 实现 `llm/provider.py`：LLMProvider 抽象基类（chat 接口定义）
- [x] 3.2 实现 `llm/openai_compat.py`：OpenAI 兼容协议实现（openai SDK，function calling，流式输出）
- [x] 3.3 实现 `llm/retry.py`：超时控制 + 指数退避重试（仅网络错误重试）
- [x] 3.4 编写 `test_llm_provider.py`：Mock LLM Provider 场景测试（流式输出、超时、重试、错误处理）

## 4. 工具系统

- [x] 4.1 实现 `tools/base.py`：ToolBase 抽象基类 + PermissionLevel 枚举 + ToolResult 类型
- [x] 4.2 实现 `tools/registry.py`：ToolRegistry 注册表（注册、查找、to_openai_schemas）
- [x] 4.3 实现 `tools/list_dir.py`：目录浏览工具（READ 级别）
- [x] 4.4 实现 `tools/read_file.py`：文件读取工具（READ 级别，支持行范围）
- [x] 4.5 实现 `tools/glob_search.py`：Glob 文件匹配工具（READ 级别）
- [x] 4.6 实现 `tools/grep_search.py`：内容搜索工具（READ 级别，正则匹配）
- [x] 4.7 实现 `tools/write_file.py`：文件写入工具（WRITE 级别）
- [x] 4.8 实现 `tools/edit_file.py`：文件编辑工具（WRITE 级别，字符串替换）
- [x] 4.9 实现 `tools/shell_exec.py`：Shell 命令执行工具（SHELL 级别）
- [x] 4.10 编写 `test_tools.py`：7 个工具的正常执行、错误处理、参数校验测试

## 5. 权限控制

- [x] 5.1 实现 `permissions/policy.py`：PermissionLevel 枚举 + PermissionDecision 枚举
- [x] 5.2 实现 `permissions/guard.py`：PermissionGuard（READ 自动放行，WRITE/SHELL 请求确认）
- [x] 5.3 编写 `test_permissions.py`：只读自动执行、写入需确认、拒绝后不执行测试

## 6. 会话管理

- [x] 6.1 实现 `session/manager.py`：SessionManager（消息累积、上下文组装、轮次计数）
- [x] 6.2 实现 `session/storage.py`：JSONL 格式持久化到 `.tui-agent/logs/`
- [x] 6.3 编写 `test_session.py`：消息累积、上下文组装、JSONL 持久化、会话清空测试

## 7. Agent Loop

- [x] 7.1 实现 `agent/types.py`：AgentEvent 类型定义（TextDelta、ToolCallStart、ToolCallResult、PermissionRequest、PermissionDenied、AgentFinished、AgentError）
- [x] 7.2 实现 `agent/context.py`：系统提示组装 + 上下文构建
- [x] 7.3 实现 `agent/loop.py`：Agent Loop 核心（AsyncIterator[AgentEvent] 流式产出）
- [x] 7.4 编写 `test_agent_loop.py`：文本回复、工具调用、多轮推理、max_turns 终止测试

## 8. 日志系统

- [x] 8.1 实现 `logging/logger.py`：loguru 配置（结构化输出、日志级别、脱敏 filter）
- [x] 8.2 实现日志脱敏规则（API Key、Bearer Token、环境变量值）
- [x] 8.3 确保两层日志路径区分（`.tui-agent/logs/` vs `.ai_history/logs/`）

## 9. TUI 界面

- [x] 9.1 实现 `tui/widgets/header.py`：Header 组件（模型名、轮次、运行状态）
- [x] 9.2 实现 `tui/widgets/chat.py`：对话流组件（用户输入、模型回复、工具调用、权限确认）
- [x] 9.3 实现 `tui/widgets/input.py`：输入框组件（多行输入、命令识别）
- [x] 9.4 实现 `tui/commands.py`：5 个内置命令处理（/help /clear /model /status /exit）
- [x] 9.5 实现 `tui/screens.py`：主界面布局（Header + Body + Footer）
- [x] 9.6 实现 `tui/app.py`：Textual App 主类（事件绑定、Agent Loop 集成）

## 10. 程序入口与集成

- [x] 10.1 实现 `__main__.py`：程序入口（`python -m tui_agent`）
- [x] 10.2 实现 `app.py`：顶层 App 组装（配置加载 → Provider 初始化 → 工具注册 → Agent Loop → TUI 启动）
- [x] 10.3 端到端集成验证：启动 TUI Agent，完成一次完整的对话交互

## 11. 交付验证

- [x] 11.1 使用实现的 TUI Agent 创建俄罗斯方块游戏（`tetris.py`）
- [x] 11.2 截取关键运行截图，保存至 `deliverables/`
- [x] 11.3 确认 `.tui-agent/logs/` 中有对应的 JSONL 对话日志
- [x] 11.4 确认 `.ai_history/logs/` 中有本轮 Cursor 对话摘要

## 12. 红线检查

- [x] 12.1 确认 Agent Loop 为自实现（未使用 LangChain/AutoGPT/任何 Agent SDK）
- [x] 12.2 确认工具系统为自实现（未使用第三方 Tool 框架）
- [x] 12.3 确认权限控制为自实现（未使用 Agent Framework 的权限模块）
- [x] 12.4 确认会话管理为自实现（未使用 Framework 的 Memory 模块）
- [x] 12.5 确认 API Key 仅从环境变量读取，日志已脱敏
- [x] 12.6 确认 7 个工具和 5 个内置命令全部实现

## 13. 手动优化（用户自主完成）

- [x] 13.1 优化 ChatWidget 展示逻辑（工具参数格式化、空行折叠、流式文本与工具调用交叉排列）
- [x] 13.2 新增 `test_chat_widget.py`（7 个展示逻辑测试）
- [x] 13.3 新增 `TUI_AGENT_MODELS` 配置支持（多模型列表，支持逗号分隔和多行格式）
- [x] 13.4 新增 `TestAvailableModels` 测试（3 个用例）
- [x] 13.5 优化 system prompt（工具调用与文字交替输出）
- [x] 13.6 优化 shell_exec 工具（超时、输出截断等细节）
