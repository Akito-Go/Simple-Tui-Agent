# tool-system Specification

## Purpose
TBD - created by archiving change implement-tui-coding-agent. Update Purpose after archive.
## Requirements
### Requirement: 工具注册与 Schema 暴露

系统 必须 (MUST) 提供工具注册表（ToolRegistry），支持注册 7 个工具（list_dir / read_file / glob_search / grep_search / write_file / edit_file / shell_exec），并将工具定义转为 OpenAI function calling schema 格式暴露给 LLM。

#### Scenario: 注册所有工具
- **给定** 系统启动
- **当** 初始化 ToolRegistry
- **那么** 系统 必须 (MUST) 注册全部 7 个工具，每个工具包含 name、description、parameters（JSON Schema）和 permission_level

#### Scenario: 生成 OpenAI Schema
- **给定** 已注册的工具列表
- **当** 调用 `to_openai_schemas()`
- **那么** 系统 必须 (MUST) 返回符合 OpenAI function calling 格式的工具定义数组

### Requirement: 目录浏览工具

系统 必须 (MUST) 实现 `list_dir` 工具，接受目录路径参数，返回指定目录下的文件和子目录列表。权限级别为 READ。

#### Scenario: 列出项目根目录
- **给定** 当前工作目录包含 src/、tests/、pyproject.toml
- **当** 调用 `list_dir("./")`
- **那么** 系统 必须 (MUST) 返回包含 src/、tests/、pyproject.toml 的列表

#### Scenario: 列出不存在的目录
- **给定** 目录 `./nonexistent` 不存在
- **当** 调用 `list_dir("./nonexistent")`
- **那么** 系统 必须 (MUST) 返回错误信息，说明目录不存在

### Requirement: 文件读取工具

系统 必须 (MUST) 实现 `read_file` 工具，接受文件路径参数，返回文件内容。支持可选的 start_line 和 end_line 参数读取指定行范围。权限级别为 READ。

#### Scenario: 读取完整文件
- **给定** 文件 `pyproject.toml` 存在
- **当** 调用 `read_file("pyproject.toml")`
- **那么** 系统 必须 (MUST) 返回文件完整内容

#### Scenario: 读取指定行范围
- **给定** 文件 `pyproject.toml` 有 20 行
- **当** 调用 `read_file("pyproject.toml", start_line=1, end_line=5)`
- **那么** 系统 必须 (MUST) 返回第 1 到第 5 行内容

### Requirement: Glob 文件匹配工具

系统 必须 (MUST) 实现 `glob_search` 工具，接受 glob 模式参数，返回匹配的文件路径列表。权限级别为 READ。

#### Scenario: 匹配所有 Python 文件
- **给定** 项目包含 src/main.py、tests/test_main.py、README.md
- **当** 调用 `glob_search("**/*.py")`
- **那么** 系统 必须 (MUST) 返回 src/main.py 和 tests/test_main.py

### Requirement: Grep 内容搜索工具

系统 必须 (MUST) 实现 `grep_search` 工具，接受正则表达式模式和搜索路径参数，返回匹配的文件路径、行号和行内容。权限级别为 READ。

#### Scenario: 搜索函数定义
- **给定** 项目包含多个 Python 文件
- **当** 调用 `grep_search("def main", "./")`
- **那么** 系统 必须 (MUST) 返回所有包含 "def main" 的文件路径、行号和行内容

### Requirement: 文件写入工具

系统 必须 (MUST) 实现 `write_file` 工具，接受文件路径和内容参数，创建或覆盖文件。权限级别为 WRITE。

#### Scenario: 创建新文件
- **给定** 文件 `new_file.py` 不存在
- **当** 调用 `write_file("new_file.py", "print('hello')")`
- **那么** 系统 必须 (MUST) 创建文件并写入指定内容

#### Scenario: 覆盖已有文件
- **给定** 文件 `existing.py` 已存在
- **当** 调用 `write_file("existing.py", "new content")`
- **那么** 系统 必须 (MUST) 覆盖文件内容为新内容

### Requirement: 文件编辑工具

系统 必须 (MUST) 实现 `edit_file` 工具，接受文件路径、旧字符串和新字符串参数，在文件中查找并替换指定内容。权限级别为 WRITE。

#### Scenario: 替换文件中的代码片段
- **给定** 文件 `main.py` 包含 `version = "1.0"`
- **当** 调用 `edit_file("main.py", 'version = "1.0"', 'version = "2.0"')`
- **那么** 系统 必须 (MUST) 将文件中的 `version = "1.0"` 替换为 `version = "2.0"`

#### Scenario: 旧字符串不匹配
- **给定** 文件 `main.py` 不包含 `old_string`
- **当** 调用 `edit_file("main.py", "old_string", "new_string")`
- **那么** 系统 必须 (MUST) 返回错误信息，说明未找到匹配内容

### Requirement: Shell 命令执行工具

系统 必须 (MUST) 实现 `shell_exec` 工具，接受命令字符串和工作目录参数，执行 Shell 命令并返回 stdout、stderr 和退出码。权限级别为 SHELL。系统 必须 (MUST) 在执行前对高危命令做黑名单拦截。

#### Scenario: 执行简单命令
- **给定** 用户确认执行
- **当** 调用 `shell_exec("ls -la", "./")`
- **那么** 系统 必须 (MUST) 返回命令的 stdout、stderr 和退出码

#### Scenario: 拦截高危命令
- **给定** 命令为 `rm -rf /` 或 `curl ... | sh` 或反弹壳类命令
- **当** Agent 准备执行 `shell_exec`
- **那么** 系统 必须 (MUST) 在权限确认之前拒绝执行，并返回安全策略拦截错误

#### Scenario: 命令执行失败
- **给定** 用户确认执行
- **当** 调用 `shell_exec("nonexistent-command", "./")`
- **那么** 系统 必须 (MUST) 返回非零退出码和错误信息

