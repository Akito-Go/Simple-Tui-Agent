# TUI 终端编码 Agent

从零实现的 TUI 终端 AI 编码助手。

用户在终端交互界面中通过自然语言下达开发任务，Agent 结合代码仓库上下文自主规划执行步骤，完成工具调用并在结果基础上继续推理。

## 从 0 到 1 运行指引

按顺序完成以下步骤，即可在全新机器上跑起来。

### 第 0 步：准备环境

| 项目 | 要求 |
|------|------|
| Python | **3.11+**（`python --version` 确认） |
| API Key | OpenAI 兼容：`TUI_AGENT_API_KEY` / `OPENAI_API_KEY`；Anthropic：`ANTHROPIC_API_KEY` |
| 终端 | 支持全屏 TUI（macOS Terminal / iTerm2、Windows Terminal 等） |

> macOS 通过 Homebrew 安装的 Python 受 [PEP 668](https://peps.python.org/pep-0668/) 保护，**不要**直接用系统 `pip install`，请使用下方虚拟环境。

### 第 1 步：获取代码

```bash
git clone https://github.com/Akito-Go/tui-agent.git
cd tui-agent
```

### 第 2 步：创建虚拟环境并安装

**macOS / Linux：**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**Windows（CMD）：**

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

**Windows（PowerShell）：**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

> PowerShell 若提示脚本执行策略错误，先运行：
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

验证安装：

```bash
python -c "import tui_agent; print('安装成功')"
```

### 第 3 步：配置 API Key

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

编辑 `.env`，按 Provider 填入密钥：

```bash
# OpenAI 兼容（默认）
TUI_AGENT_PROVIDER=openai_compat
TUI_AGENT_API_KEY=你的真实-api-key

# 或 Anthropic Messages API
# TUI_AGENT_PROVIDER=anthropic
# ANTHROPIC_API_KEY=你的-anthropic-key
# TUI_AGENT_MODEL=claude-sonnet-4-5
```

按需修改 `TUI_AGENT_API_BASE` 和模型名称。其余配置见 `.env.example`。

### 第 4 步：启动

每次新开终端都需要先激活虚拟环境：

```bash
# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

启动方式（二选一）：

```bash
python -m tui_agent
# 或
tui-agent
```

### 第 5 步：首次交互

1. 启动后进入欢迎页（Le+O + Q 版小猫）与新会话，直接输入任务即可，例如：
   ```
   帮我看看项目结构
   ```
2. 需要恢复历史时使用 `/sessions`（或 `/sessions <序号>`）；选择阶段输入序号恢复，`N` 取消
3. 只读工具（`list_dir`、`read_file` 等）自动执行；写入/Shell 会弹出确认（↑↓ + Enter 或 Y/N）
4. 运行中可用 `/stop` 终止；退出用 `/exit` 或 `Ctrl+C`

### 常见问题

| 现象 | 处理 |
|------|------|
| `externally-managed-environment` | 使用 `.venv`，不要往系统 Python 装包 |
| `配置错误: 未找到 API Key` | 检查 `.env` 中 `TUI_AGENT_API_KEY` 是否填写 |
| `LLM 请求失败: bad_request` | 恢复旧会话后若报错，可新建会话；旧 JSONL 已在 loader 层做兼容修复 |
| 工具参数含 `[]` 导致界面异常 | 已禁用 Textual markup 解析，升级后应不再出现 |

---

## 快速开始

（若已完成上方「从 0 到 1」可跳过本节。）

### 环境要求

- Python 3.11+
- OpenAI 兼容 API Key，或 Anthropic API Key

### 安装与启动

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows 见上文
pip install -e ".[dev]"
cp .env.example .env   # 填入 API Key 与可选 TUI_AGENT_PROVIDER
python -m tui_agent
```

### 配置说明

**配置优先级**：

```
.env 环境变量  >  项目级 .tui-agent.yaml  >  用户级 ~/.tui-agent.yaml  >  config/default.yaml
```

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `TUI_AGENT_PROVIDER` | `openai_compat` | `openai_compat` 或 `anthropic` |
| `TUI_AGENT_API_KEY` | — | OpenAI 兼容密钥（也可用 `OPENAI_API_KEY`） |
| `ANTHROPIC_API_KEY` | — | Anthropic 密钥（`provider=anthropic` 时） |
| `TUI_AGENT_MODEL` | `gpt-4o-mini` | 当前模型 |
| `TUI_AGENT_API_BASE` | `https://api.openai.com/v1` | API 地址 |
| `TUI_AGENT_TIMEOUT` | `120` | 请求超时（秒） |
| `TUI_AGENT_MAX_TURNS` | `50` | 最大推理轮次 |
| `TUI_AGENT_MAX_RETRIES` | `3` | 网络错误重试次数 |
| `TUI_AGENT_CONTEXT_MAX_TOKENS` | `32000` | 上下文压缩阈值 |
| `TUI_AGENT_MODELS` | 内置模型列表 | `/model` 可切换列表 |

> 运行时用 `/model <序号\|名称>` 可立即切换模型（同步更新 system prompt）。

### 使用示例

```
╭─ Le+O · tui-agent v0.1.0 ────────────────────────────────────╮
│  欢迎回来！              │  入门提示                         │
│     ▄▄      ▄▄           │  只读工具会自动执行…（轮播）      │
│    ████    ████          ├───────────────────────────────────┤
│   ██▀████████▀██         │  最近活动                         │
│    Q版小猫吉祥物         │  输入 /sessions 恢复会话          │
│  gpt-4o · openai_compat  │                                   │
│  ~/project               │                                   │
╰──────────────────────────┴───────────────────────────────────╯
│  👤 帮我创建一个 Python 俄罗斯方块游戏                        │
│  🤖 我先看看项目结构...                                       │
│  ● list_dir(path=.)                                           │
│    ⎿ src/ tests/ ...                                          │
> _
? for shortcuts · /help · /sessions
tui-agent · openai · gpt-4o-mini · 轮次 1/50    就绪
```

### 内置命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助和可用工具 |
| `/clear` | 清空当前会话 |
| `/sessions` | 列出/恢复历史会话（`/sessions <序号>` 直接恢复） |
| `/stop` | 停止当前 Agent 运行 |
| `/model` | 列出/切换模型（跨 Provider 会重建客户端） |
| `/provider` | 查看/切换 `openai_compat` / `anthropic` |
| `/status` | 查看运行状态 |
| `/exit` | 退出（或 Ctrl+C） |

### 可用工具

| 工具 | 权限 | 说明 |
|------|:----:|------|
| `list_dir` | 自动 | 列出目录 |
| `read_file` | 自动 | 读取文件（支持行范围） |
| `glob_search` | 自动 | Glob 匹配 |
| `grep_search` | 自动 | 内容搜索 |
| `write_file` | 需确认 | 创建/覆盖文件 |
| `edit_file` | 需确认 | 查找替换 |
| `shell_exec` | 需确认 | 执行 Shell 命令（高危命令黑名单拦截） |

## 项目结构

```
tui-agent/
├── src/tui_agent/
│   ├── __main__.py             # 入口
│   ├── agent/
│   │   ├── loop.py             # Agent Loop（推理→工具→回传）
│   │   ├── context.py
│   │   └── types.py            # AgentEvent 事件类型
│   ├── tools/                  # 7 个工具 + registry
│   ├── permissions/            # READ/WRITE/SHELL 权限守卫
│   ├── session/
│   │   ├── manager.py          # 多轮上下文 + system prompt
│   │   ├── storage.py          # JSONL 增量持久化
│   │   ├── loader.py           # 会话列表与恢复
│   │   └── compressor.py       # 上下文压缩
│   ├── config/                 # YAML + .env 加载
│   ├── llm/                    # OpenAI 兼容 Provider
│   ├── tui/                    # Textual 界面
│   │   ├── app.py
│   │   ├── commands.py         # 6 个内置命令
│   │   └── widgets/            # chat / confirm / header / input
│   └── logging/                # loguru + 脱敏
├── tests/
├── config/default.yaml
├── docs/
│   ├── architecture.md
│   ├── ai-audit-report.md
│   └── review-report.md
├── openspec/
├── deliverables/
├── .env.example
└── pyproject.toml
```

## 运行测试

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## 技术栈

| 维度 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| TUI | Textual |
| LLM | openai SDK（OpenAI 兼容）+ anthropic SDK（Messages API） |
| 配置 | YAML + pydantic + .env |
| 日志 | loguru |
| 测试 | pytest + pytest-asyncio |

## 核心特性

- Agent Loop、工具系统、权限控制、会话管理均为自实现（未使用 LangChain / AutoGPT 等 Agent SDK）
- 支持 OpenAI 兼容协议与 Anthropic Messages API（配置切换）
- API Key 仅环境变量，日志脱敏
- 支持多模型 / Provider 切换、会话恢复、上下文压缩、`/stop` 终止
- 工作区沙箱、敏感文件拦截、Shell 高危命令黑名单
- 权限确认支持「本次会话全部允许」

## 更多文档

- [架构设计](docs/architecture.md)
- [AI 产出审计单](docs/ai-audit-report.md)
- [Review 报告](docs/review-report.md)

## License

MIT
