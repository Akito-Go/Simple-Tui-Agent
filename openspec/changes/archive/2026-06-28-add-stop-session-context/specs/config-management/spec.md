## ADDED Requirements

### Requirement: 上下文压缩阈值配置

系统 必须 (MUST) 支持 `context_max_tokens`（默认 8000），可通过 `TUI_AGENT_CONTEXT_MAX_TOKENS` 或 YAML 配置。该值为**压缩触发阈值**，当估算 token 超过此值时触发压缩。

#### Scenario: 使用默认阈值
- **给定** 未配置 `context_max_tokens`
- **当** 系统启动
- **那么** 系统 必须 (MUST) 使用默认值 8000

#### Scenario: 自定义阈值
- **给定** `.env` 中 `TUI_AGENT_CONTEXT_MAX_TOKENS=4000`
- **当** 系统加载配置
- **那么** 系统 必须 (MUST) 使用 4000 作为压缩触发阈值

## MODIFIED Requirements

### Requirement: 配置内容覆盖

系统 必须 (MUST) 支持配置：Provider 类型、模型名称、API 地址、超时时间、最大循环轮次、最大重试次数、上下文压缩触发阈值（`context_max_tokens`）。

#### Scenario: 完整配置加载
- **给定** 配置含 provider、model、api_base、timeout、max_turns、max_retries、context_max_tokens
- **当** 系统启动
- **那么** 系统 必须 (MUST) 正确解析并应用所有配置项
