## ADDED Requirements

### Requirement: 三级配置优先级

系统 必须 (MUST) 支持三级配置优先级：项目级配置（`.tui-agent.yaml`）优先于用户级配置（`~/.tui-agent.yaml`），用户级配置优先于内置默认配置。配置项通过深度合并叠加。

#### Scenario: 项目级配置覆盖用户级
- **给定** 用户级配置 `model: gpt-4o`，项目级配置 `model: gpt-4o-mini`
- **当** 系统加载配置
- **那么** 系统 必须 (MUST) 使用项目级的 `gpt-4o-mini`

#### Scenario: 用户级配置覆盖默认值
- **给定** 默认配置 `max_turns: 20`，用户级配置 `max_turns: 30`
- **当** 项目级未设置 `max_turns`
- **那么** 系统 必须 (MUST) 使用用户级的 `30`

#### Scenario: 无自定义配置时使用默认值
- **给定** 项目级和用户级配置均不存在
- **当** 系统加载配置
- **那么** 系统 必须 (MUST) 使用内置默认配置

### Requirement: 配置内容覆盖

系统 必须 (MUST) 支持配置以下基础信息：Provider 类型、模型名称、API 地址、超时时间、最大循环轮次和最大重试次数。

#### Scenario: 完整配置加载
- **给定** 配置文件包含 provider、model、api_base、timeout、max_turns、max_retries
- **当** 系统启动
- **那么** 系统 必须 (MUST) 正确解析所有配置项并应用到对应模块

### Requirement: API Key 保护

系统 必须 (MUST) 仅从环境变量读取 API Key（如 `TUI_AGENT_API_KEY`），不得将 API Key 写入任何配置文件或日志输出。

#### Scenario: 从环境变量读取 API Key
- **给定** 环境变量 `TUI_AGENT_API_KEY` 设置为 `sk-test123`
- **当** 系统初始化 LLM Provider
- **那么** 系统 必须 (MUST) 从环境变量读取 API Key，配置文件中不包含 API Key

#### Scenario: 环境变量未设置时提示
- **给定** 环境变量 `TUI_AGENT_API_KEY` 未设置
- **当** 系统启动
- **那么** 系统 必须 (MUST) 显示明确的错误提示，告知用户需要设置环境变量
