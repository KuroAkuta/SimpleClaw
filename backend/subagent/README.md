# 子 Agent 系统

## 概述

子 Agent 系统允许主 agent 将复杂任务委托给专门的子 agent 执行。每个子 agent 在隔离的上下文中自主执行任务，完成后返回结果。

这个实现参考了 Claude Code 的 subagent 架构。

## 架构

```
backend/subagent/
├── __init__.py          # 模块入口，导出所有公共 API
├── config.py            # SubagentConfig 数据类定义
├── registry.py          # 子 agent 注册表和查询接口
├── executor.py          # SubagentExecutor 执行引擎
├── builtins.py          # 内置子 agent 配置
├── tools.py             # 子 agent 相关工具 (task, get_task_result 等)
```

## 核心组件

### 1. SubagentConfig

定义子 agent 配置的数据类：

```python
@dataclass
class SubagentConfig:
    name: str                    # 唯一标识符
    description: str             # 何时使用该 agent 的说明
    system_prompt: str           # 指导 agent 行为的系统提示词
    tools: list[str] | None      # 允许的工具列表 (None=继承全部)
    disallowed_tools: list[str]  # 禁止的工具列表
    model: str                   # 使用的模型 ("inherit"=继承父级)
    max_turns: int               # 最大执行轮数
    timeout_seconds: int         # 超时时间 (秒)
```

### 2. SubagentExecutor

子 agent 执行引擎：

```python
executor = SubagentExecutor(
    config=config,
    tools=all_tools,
)

# 同步执行
result = executor.execute(task_description)

# 异步执行
task_id = executor.execute_async(task_description)
result = get_background_task_result(task_id)
```

### 3. 内置子 Agent

#### general-purpose
- **用途**: 复杂的多步骤任务，需要探索和修改
- **工具**: 继承所有工具（除了 task 本身，防止嵌套）
- **最大轮数**: 100

#### bash
- **用途**: 执行一系列相关的 bash 命令
- **工具**: bash, ls, read_file, write_file, find_files
- **最大轮数**: 60

## 使用方法

### 在系统提示词中添加子 agent 描述

```python
from subagent import get_subagent_tool_descriptions

system_prompt += get_subagent_tool_descriptions()
```

### 获取子 agent 工具

```python
from subagent import get_all_subagent_tools
from tools.basic_tools import get_all_tools

all_tools = get_all_tools()  # 自动包含子 agent 工具
```

### 使用 task 工具委托任务

```python
from subagent import task

result = task.invoke({
    "description": "简短的任务描述",
    "prompt": "详细的任务指令",
    "subagent_type": "general-purpose",  # 或 "bash"
    "max_turns": 50,  # 可选
})
```

### 异步任务执行

```python
from subagent import task_async, get_task_result, list_task_status

# 启动异步任务
task_id = task_async.invoke({
    "description": "分析项目结构",
    "prompt": "分析当前项目的目录结构，找出所有 Python 文件并统计数量",
    "subagent_type": "bash",
})

# 查询结果
result = get_task_result.invoke({"task_id": task_id})

# 查看所有任务状态
status = list_task_status.invoke({})
```

## 系统提示词集成

系统提示词中已自动包含子 agent 描述：

```
### Subagent Delegation
- `task(description, prompt, subagent_type, max_turns)` - Delegate a task to a subagent
  - Use for complex, multi-step tasks that benefit from isolated context
  - Available subagent types: general-purpose, bash
  - The subagent will execute autonomously and return a result
```

## 工具过滤

子 agent 可以配置允许/禁止的工具：

```python
BASH_AGENT_CONFIG = SubagentConfig(
    name="bash",
    tools=["run_command", "list_directory", "read_file", "write_file", "find_files"],
    disallowed_tools=["task", "execute_skill_script"],  # 防止嵌套
)
```

## 执行流程

1. 主 agent 调用 `task` 工具
2. 创建 `SubagentExecutor` 实例，过滤工具
3. 构建独立的 agent graph
4. 在隔离的上下文中执行任务
5. 收集结果并返回给主 agent

## 超时处理

```python
# 默认 15 分钟超时
config = SubagentConfig(
    name="my-agent",
    timeout_seconds=900,  # 15 分钟
)
```

异步执行时，超时会自动取消任务：

```python
# execute_async 内部会检测超时
if result.status == SubagentStatus.TIMED_OUT:
    print(f"任务超时：{result.error}")
```

## 取消任务

```python
from subagent import request_cancel_background_task

request_cancel_background_task(task_id)
```

## 测试

运行测试脚本：

```bash
cd backend
python -m subagent.test_subagent
```

测试项目：
- 子 agent 注册表
- 工具描述生成
- 实际 agent 执行（需要 API key）

## 扩展自定义子 Agent

添加新的子 agent：

```python
# subagent/builtins.py
from subagent.config import SubagentConfig

MY_CUSTOM_AGENT = SubagentConfig(
    name="my-custom-agent",
    description="专门处理 XXX 任务的 agent",
    system_prompt="你是 XXX 专家...",
    tools=["specific_tool_1", "specific_tool_2"],
    max_turns=80,
)

BUILTIN_SUBAGENTS["my-custom-agent"] = MY_CUSTOM_AGENT
```

## 与参考项目的对比

| 特性 | 参考项目 | 本项目 |
|------|----------|--------|
| 配置类 | `SubagentConfig` | `SubagentConfig` |
| 执行器 | `SubagentExecutor` | `SubagentExecutor` |
| 内置 agent | general-purpose, bash | general-purpose, bash |
| 工具过滤 | ✓ | ✓ |
| 模型继承 | ✓ | ✓ |
| 超时控制 | ✓ | ✓ |
| 异步执行 | ✓ | ✓ |
| 取消机制 | ✓ | ✓ |
| LangGraph 集成 | ✓ | ✓ |

## 注意事项

1. **防止嵌套**: `task` 工具被所有子 agent 禁止使用
2. **工具隔离**: 每个子 agent 只访问配置允许的工具
3. **上下文隔离**: 子 agent 在独立的状态图中执行
4. **错误处理**: 所有异常被捕获并返回为 FAILED 状态
5. **内存管理**: 完成后调用 `cleanup_background_task` 清理结果

## 未来增强

- [ ] 支持更多内置子 agent（如代码审查、测试专家等）
- [ ] 子 agent 间通信机制
- [ ] 动态子 agent 创建
- [ ] 子 agent 执行统计和日志
- [ ] 可视化子 agent 执行流程
