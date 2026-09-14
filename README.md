<p align="center">
  <img src="docs/images/sta-cat.png" alt="STA 笑眼坐猫 Logo" width="160" />
</p>

<h1 align="center">STA · Simple TUI Agent</h1>

<h3 align="center">在终端中用自然语言阅读代码、修改文件与执行开发任务的 AI 编码助手</h3>

<p align="center">
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/version-v0.1.0-blue" alt="Version 0.1.0" /></a>
  <a href="#快速开始"><img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11+" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT" /></a>
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#核心特性">核心特性</a> ·
  <a href="#配置说明">配置说明</a> ·
  <a href="docs/ui-guide.md">界面与操作</a> ·
  <a href="#常见问题">常见问题</a> ·
  <a href="#版本规范">版本规范</a>
</p>

---

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
git clone https://github.com/Akito-Go/Simple-Tui-Agent.git
cd Simple-Tui-Agent
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

1. 启动后进入欢迎页（STA + Q 版小猫）与新会话，直接输入任务即可，例如：
   ```
   帮我看看项目结构
   ```
2. 需要恢复历史时使用 `/sessions`（或 `/sessions <序号>`）；选择阶段输入序号恢复，`N` 取消
3. 只读工具（`list_dir`、`read_file` 等）自动执行；写入/Shell 会弹出确认（↑↓ + Enter 或 Y/N）
4. 寒暄/闲聊默认不应调工具；有明确编码任务时再浏览与修改
5. 运行中可用 `/stop` 或 `Esc` 终止；退出用 `/exit` 或 `Ctrl+C`

### 界面与操作

- 底部状态栏优先显示「就绪 / 运行中 / 执行工具 / 等待确认」和模型；窗口较宽时显示任务轮次及 Provider。
- 工具结果默认收起。点击结果，或用 Tab 聚焦后按 Enter / 空格，可展开、收起本次返回的内容；失败结果默认展开并标红，长内容在结果区滚动。
- 超出工具预算的输出仍通过保存路径读取，展开操作不会加载磁盘上的完整结果。
- 确认区位于输入框上方：`Y` 允许一次、`A` 本次会话允许、`N` 拒绝；也可用 ↑↓ + Enter，`Esc` 停止。diff 可滚动查看。
- 窄窗口自动切换为上下排列的紧凑欢迎页，并简化底栏。建议使用至少 **80×24**；已验证 **48×20** 下输入框和确认选项可见。

完整操作及界面示例见 [UI 使用说明](docs/ui-guide.md)。

### 常见问题

| 现象 | 处理 |
|------|------|
| `externally-managed-environment` | 使用 `.venv`，不要往系统 Python 装包 |
| `配置错误: 未找到 API Key` | 检查 `.env` 中 `TUI_AGENT_API_KEY` 是否填写 |
| `LLM 请求失败: bad_request` | 恢复旧会话后若报错，可新建会话；旧 JSONL 已在 loader 层做兼容修复 |
| 退出时出现 `PoolByteStream` / `generator didn't stop after athrow()` | 在虚拟环境执行 `python -m pip install -e ".[dev]"`，安装项目限定的 OpenAI 2.x，再重启；详见 [兼容性说明](docs/runtime-improvements.md#sdk-流式退出兼容性) |
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
.env 环境变量  >  项目级 .tui-agent.yaml  >  用户级 ~/.tui-agent.yaml  >  配置模型内置默认值
```

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `TUI_AGENT_PROVIDER` | `openai_compat` | `openai_compat` 或 `anthropic` |
| `TUI_AGENT_API_KEY` | — | OpenAI 兼容密钥（也可用 `OPENAI_API_KEY`） |
| `ANTHROPIC_API_KEY` | — | Anthropic 密钥（`provider=anthropic` 时） |
| `TUI_AGENT_MODEL` | `gpt-4o-mini` | 当前模型 |
| `TUI_AGENT_API_BASE` | `https://api.openai.com/v1` | API 地址 |
| `TUI_AGENT_TIMEOUT` | `120` | 请求超时（秒） |
| `TUI_AGENT_MAX_TURNS` | `50` | 单次任务最大推理轮次 |
| `TUI_AGENT_MAX_RETRIES` | `3` | 网络错误重试次数 |
| `TUI_AGENT_CONTEXT_MAX_TOKENS` | `32000` | 请求上下文预算（含工具定义和回复预留） |
| `TUI_AGENT_MODELS` | 内置模型列表 | `/model` 可切换列表 |

> 运行时用 `/model <序号\|名称>` 可立即切换模型（同步更新 system prompt）。

### 使用示例

```
╭─ STA · tui-agent v0.1.0 ────────────────────────────────────╮
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
Esc=/stop · /help · /sessions · 写入与 Shell 需确认 · 只读自动执行
tui-agent · openai · gpt-4o-mini · 轮次 1/50    就绪
```

### 内置命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助和可用工具 |
| `/clear` | 清空当前会话 |
| `/sessions` | 列出/恢复历史会话（`/sessions <序号>` 直接恢复） |
| `/resume [检查点ID]` | 列出未完成任务，或核对现状后继续指定任务 |
| `/undo [检查点ID]` | 预览撤销指定任务的文件修改；省略 ID 选择最近有文件记录的检查点 |
| `/undo list` | 列出最近的文件检查点 |
| `/undo confirm` / `/undo cancel` | 确认已预览的撤销 / 取消预览 |
| `/stop` | 停止当前 Agent 运行（快捷键 `Esc`） |
| `/model` | 列出/切换模型（跨 Provider 会重建客户端） |
| `/provider` | 查看/切换 `openai_compat` / `anthropic` |
| `/status` | 查看运行状态 |
| `/plan <目标>` | 生成执行计划，不修改文件 |
| `/exit` | 退出（或 Ctrl+C） |

长任务会在状态栏显示阶段、工具进度和已修改文件。

任务检查点自动保存在 `.tui-agent/checkpoints/`。`/resume` 创建新的续接会话与检查点，保留旧历史，重新判断剩余工作并确认新操作。`/undo` 只恢复 `write_file` / `edit_file` 的文件内容和权限；有后续修改时报告冲突，Shell 副作用不在撤销范围。具体操作和限制见 [任务恢复与撤销](docs/ui-guide.md#任务检查点恢复与撤销)。

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
│   │   ├── commands.py         # /help /sessions /stop ...
│   │   ├── welcome.py          # STA 欢迎页
│   │   └── widgets/            # chat / confirm / header / input
│   └── logging/                # loguru + 脱敏
├── tests/
├── config/default.yaml
├── docs/architecture.md
├── .env.example
└── pyproject.toml
```

> `openspec/`、`deliverables/` 等仅本地保留，已在 `.gitignore`，不推远端。

## 运行测试

```bash
source .venv/bin/activate
python -m ruff check src tests
python -m pytest tests/ -v
```

CI 已纳入仓库，对 Python 3.11 / 3.12 及 Linux、macOS、Windows 运行检查。

## Runtime 可靠性

- `/stop` 补齐取消结果并清理当前工具队列；轮次额度按每次任务重置。
- 历史记录与模型上下文分离，压缩后可继续保存和恢复；摘要失败保留原文。`/clear` 保留旧会话文件。
- 确认前可查看文件 diff；覆盖/编辑会校验已读状态及外部修改，使用原子替换写入。
- 搜索支持超时和取消；大工具输出有界落盘并返回读取路径，避免撑爆上下文。
- 本机 Shell 超时/取消会清理进程树，非零退出码显示失败。命令拥有当前用户的系统权限，工作目录限制不等于系统隔离。

详细行为、输出限额和验证范围见 [Runtime 改造说明](docs/runtime-improvements.md)。

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
- 支持多模型 / Provider 切换、`/sessions` 会话恢复、上下文压缩
- `/stop` 与 `Esc` 可随时中断当前任务（取消后台 Task 并复位 UI）
- 闲聊/寒暄时 system prompt 引导不主动扫仓库
- 文件工具工作区边界、敏感文件及符号链接目标拦截；本机 Shell 需确认并有高危命令黑名单（不提供系统沙箱隔离）
- 权限确认支持「本次会话全部允许」（不绕过 Shell 黑名单）

## 更多文档

- [界面使用说明](docs/ui-guide.md)
- [架构设计](docs/architecture.md)
- [Runtime 改造与边界说明](docs/runtime-improvements.md)

## 版本规范

项目采用 [Semantic Versioning 2.0.0（SemVer）](https://semver.org/lang/zh-CN/)，版本格式为 `MAJOR.MINOR.PATCH`，以 `pyproject.toml` 中的 `project.version` 为唯一版本来源。当前版本为 **0.1.0**，处于初始开发阶段，接口与行为尚未承诺稳定。

- `0.x.y` 阶段：新增功能或不兼容调整递增 `MINOR`，兼容的问题修复递增 `PATCH`。
- 自 `1.0.0` 起：不兼容变更递增 `MAJOR`，向后兼容的新功能递增 `MINOR`，向后兼容的问题修复递增 `PATCH`；递增高位时将低位归零。
- 发布前同步更新 README 版本徽章；Git 标签使用 `v0.1.0` 这样的形式，其中 `v` 是标签前缀，不属于 SemVer 版本号。
- 预发布可使用 `0.2.0-rc.1`；Python 包构建时按 PEP 440 表示为 `0.2.0rc1`。两者表达同一个候选版本，不混写版本格式。

顶部徽章展示源码版本，不代表已经创建对应的发布或 Git 标签。

## License

MIT

### 非交互模式

```bash
python -m tui_agent --prompt "检查项目测试" --json
```

`--json` 输出结构化结果；写入或 Shell 默认不会自动批准，自动化场景需显式添加 `--yes`。输入框按 `Tab` 可补全命令、工具名和模型。

使用 `/files` 查看当前任务的文件列表与净增删行数，使用 `/diff [路径]` 查看全部或指定文件的差异。文件写入确认会展示操作类型、预计影响与 diff；任务结束后自动汇总变更。统计基于任务 checkpoint，不包含 Shell 修改或后续手动修改。详见 [界面指南](docs/ui-guide.md)。
