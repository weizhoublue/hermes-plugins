# Hook 接口梳理

本文基于当前代码梳理以下 hook 的**作用、调用时机、入参和返回值**：

```python
VALID_HOOKS: Set[str] = {
    "pre_tool_call",
    "post_tool_call",
    "transform_terminal_output",
    "transform_tool_result",
    "pre_llm_call",
    "post_llm_call",
    "pre_api_request",
    "post_api_request",
    "on_session_start",
    "on_session_end",
    "on_session_finalize",
    "on_session_reset",
    "subagent_stop",
}
```

## 总体规则

先说结论：**统一后端 hook 接口本体就在 `hermes_cli/plugins.py`，不是定义在 CLI 或飞书各自的入口文件里。**

- hook 名字集合：`VALID_HOOKS`  
  代码：`hermes_cli/plugins.py`
- 注册入口：`ctx.register_hook(hook_name, callback)`  
  代码：`hermes_cli/plugins.py`
- 统一触发入口：`invoke_hook(hook_name, **kwargs)`  
  代码：`hermes_cli/plugins.py`
- 回调建议统一写成：`def my_hook(**kwargs): ...`
- `invoke_hook()` 会收集所有 **非 `None`** 返回值，但只有少数 hook 的返回值会真正影响主流程

### 当前会消费返回值的 hook

| Hook | 有效返回 |
|---|---|
| `pre_tool_call` | `{"action": "block", "message": "..."}`，阻止工具执行 |
| `transform_terminal_output` | 第一个 `str`，替换终端输出 |
| `transform_tool_result` | 第一个 `str`，替换工具结果 |
| `pre_llm_call` | `{"context": "..."}` 或 `str`，注入本轮 user message |

其余 hook 当前都是**观察型 hook**，返回值不会被主流程消费。

---

## 输入输出源码定义位置

这些 hook 本身没有单独的 typed schema 文件。  
真正的统一接口只有这一层：

```python
invoke_hook(hook_name: str, **kwargs) -> List[Any]
```

也就是说：

- **统一接口定义**：在 `hermes_cli/plugins.py`
- **具体 hook 的输入参数**：在各个业务调用点直接以 `invoke_hook(hook_name, **kwargs)` 构造
- **具体 hook 的返回值语义**：由调用点或 `hermes_cli/plugins.py` 中的辅助逻辑消费

### 总入口

| 主题 | 源码位置 | 说明 |
|---|---|---|
| hook 调度入口 | `hermes_cli/plugins.py:954-988` | `PluginManager.invoke_hook()`，逐个执行 callback，收集所有非 `None` 返回值 |
| 对外调用入口 | `hermes_cli/plugins.py:1062-1067` | 模块级 `invoke_hook()`，各业务代码都通过它触发 hook |
| `pre_tool_call` block 语义 | `hermes_cli/plugins.py:1071-1107` | `get_pre_tool_call_block_message()` 解析 `{"action":"block","message":"..."}` |

### 各 hook 的输入来源 / 输出消费位置

| Hook | 输入参数源码位置 | 返回值消费位置 |
|---|---|---|
| `pre_tool_call` | `model_tools.py:530-558` / `hermes_cli/plugins.py:1089-1096` | `hermes_cli/plugins.py:1098-1107` 解析 block；`model_tools.py:544-545` 把 block 转成错误返回 |
| `post_tool_call` | `model_tools.py:596-607` | 无专门消费位置，返回值忽略 |
| `transform_terminal_output` | `tools/terminal_tool.py:1862-1871` | `tools/terminal_tool.py:1872-1875`，第一个 `str` 替换 `output` |
| `transform_tool_result` | `model_tools.py:617-628` | `model_tools.py:629-632`，第一个 `str` 替换 `result` |
| `pre_llm_call` | `run_agent.py:9516-9526` | `run_agent.py:9527-9534`，解析 `{"context": ...}` 或 `str` |
| `post_llm_call` | `run_agent.py:12517-12526` | 无专门消费位置，返回值忽略 |
| `pre_api_request` | `run_agent.py:9948-9965` | 无专门消费位置，返回值忽略 |
| `post_api_request` | `run_agent.py:11639-11660` | 无专门消费位置，返回值忽略 |
| `on_session_start` | `run_agent.py:9414-9421` | 无专门消费位置，返回值忽略 |
| `on_session_end` | `run_agent.py:12618-12627` | 无专门消费位置，返回值忽略 |
| `on_session_finalize` | `cli.py:756-757`、`cli.py:4729-4734`、`gateway/run.py:1930-1935`、`gateway/run.py:2492-2499`、`gateway/run.py:5351-5354` | 无专门消费位置，返回值忽略 |
| `on_session_reset` | `cli.py:4729-4734`（通过 `_notify_session_boundary`） / `cli.py:4791`、`gateway/run.py:5387-5390` | 无专门消费位置，返回值忽略 |
| `subagent_stop` | `tools/delegate_tool.py:2119-2127` | 无专门消费位置，返回值忽略 |

### 一句话理解

- **入参定义在哪？** 在每个业务调用点的 `invoke_hook(..., key=value, ...)`
- **返回值定义在哪？** 在返回值被谁解析，就由谁定义：
  - `pre_tool_call` → `hermes_cli/plugins.py` + `model_tools.py`
  - `pre_llm_call` → `run_agent.py`
  - `transform_terminal_output` → `tools/terminal_tool.py`
  - `transform_tool_result` → `model_tools.py`
  - 其他 hook → 当前代码里返回值不消费

---

## 1. `pre_tool_call`

### 作用

工具执行前的拦截点，可用于审计、限流、审批、阻断危险工具。

### 调用时机

在 `model_tools.handle_function_call()` 中，真正 `registry.dispatch()` 前调用。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `tool_name` | `str` | 将要执行的工具名 |
| `args` | `dict` | 工具参数 |
| `task_id` | `str` | 任务 ID，没有则为空串 |
| `session_id` | `str` | 会话 ID，没有则为空串 |
| `tool_call_id` | `str` | 当前 tool call ID，没有则为空串 |

### 返回

- 生效返回：`{"action": "block", "message": "..."}`
- 含义：阻止该工具执行，错误消息直接返回给模型
- 规则：**第一个合法 block 生效**

---

## 2. `post_tool_call`

### 作用

工具执行后的观察点，适合做日志、打点、统计。

### 调用时机

在 `registry.dispatch()` 返回后、`transform_tool_result` 前调用。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `tool_name` | `str` | 刚执行完的工具名 |
| `args` | `dict` | 工具参数 |
| `result` | `str` | 工具返回值，通常是 JSON 字符串 |
| `task_id` | `str` | 任务 ID |
| `session_id` | `str` | 会话 ID |
| `tool_call_id` | `str` | 当前 tool call ID |
| `duration_ms` | `int` | 工具 dispatch 耗时，毫秒 |

### 返回

- 返回值当前**不消费**

---

## 3. `transform_terminal_output`

### 作用

专门用于改写 `terminal` 工具的前台输出。

### 调用时机

在 `tools/terminal_tool.py` 中，命令执行完成、拿到 `output` 后，**默认截断前**调用。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `command` | `str` | 执行的命令 |
| `output` | `str` | 原始终端输出 |
| `returncode` | `int` | 退出码 |
| `task_id` | `str` | 任务 ID |
| `env_type` | `str` | 终端环境类型，如 `local`、`docker`、`ssh` |

### 返回

- 生效返回：第一个 `str`
- 含义：替换 `output`
- 说明：替换后仍会继续走后续的截断/整理流程

---

## 4. `transform_tool_result`

### 作用

工具结果总出口改写点，适合统一规范 tool result 格式。

### 调用时机

在 `post_tool_call` 之后、工具结果写回 agent 对话上下文之前调用。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `tool_name` | `str` | 工具名 |
| `args` | `dict` | 工具参数 |
| `result` | `str` | 原始工具结果 |
| `task_id` | `str` | 任务 ID |
| `session_id` | `str` | 会话 ID |
| `tool_call_id` | `str` | 当前 tool call ID |
| `duration_ms` | `int` | 工具耗时 |

### 返回

- 生效返回：第一个 `str`
- 含义：替换整个工具结果

---

## 5. `pre_llm_call`

### 作用

每轮对话开始前注入额外上下文，例如记忆召回、RAG、策略提示。

### 调用时机

在 `run_agent.AIAgent.run_conversation()` 中，进入主 tool-calling loop 前调用。  
注意：这是**按 turn 触发**，不是按底层 API 请求触发。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | `str` | 当前会话 ID |
| `user_message` | `str` | 用户本轮原始输入 |
| `conversation_history` | `list` | 当前消息列表副本 |
| `is_first_turn` | `bool` | 是否新 session 首轮 |
| `model` | `str` | 当前模型 |
| `platform` | `str` | 平台，如 `cli`、`telegram` |
| `sender_id` | `str` | 发送者 ID，没有则空串 |

### 返回

- 生效返回：
  - `{"context": "..."}`
  - 或直接返回非空 `str`
- 含义：把返回内容拼接进**本轮 user message**
- 说明：
  - 注入位置是 **user message**
  - **不会**写进 system prompt
  - **不会**持久化到 session DB

---

## 6. `post_llm_call`

### 作用

每轮对话成功完成后的观察点，适合做记忆落盘、外部同步、日志。

### 调用时机

在本轮产生 `final_response` 且未被中断时调用。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | `str` | 当前会话 ID |
| `user_message` | `str` | 用户本轮输入 |
| `assistant_response` | `str` | 助手最终回复 |
| `conversation_history` | `list` | 完成后的消息列表副本 |
| `model` | `str` | 当前模型 |
| `platform` | `str` | 当前平台 |

### 返回

- 返回值当前**不消费**

---

## 7. `pre_api_request`

### 作用

底层模型请求发出前的观测点，适合记录 provider/model 级别调用信息。

### 调用时机

在 `run_agent.py` 中，构造完 API kwargs、真正发请求前调用。  
注意：这是**按 API 请求触发**，一轮里可能触发多次。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | `str` | 任务 ID |
| `session_id` | `str` | 会话 ID |
| `platform` | `str` | 平台 |
| `model` | `str` | 模型 |
| `provider` | `str` | 提供方 |
| `base_url` | `str` | 推理接口地址 |
| `api_mode` | `str` | 调用模式 |
| `api_call_count` | `int` | 当前 turn 内第几次 API 请求 |
| `message_count` | `int` | 请求里的消息数 |
| `tool_count` | `int` | 暴露给模型的工具数 |
| `approx_input_tokens` | `int` | 粗略输入 token 估计 |
| `request_char_count` | `int` | 请求字符数 |
| `max_tokens` | `int` | 请求输出上限 |

### 返回

- 返回值当前**不消费**

---

## 8. `post_api_request`

### 作用

底层模型请求完成后的观测点，适合记录 usage、耗时、finish reason。

### 调用时机

在收到模型响应并整理出 assistant message 后调用。  
同样是**按 API 请求触发**。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | `str` | 任务 ID |
| `session_id` | `str` | 会话 ID |
| `platform` | `str` | 平台 |
| `model` | `str` | 请求模型 |
| `provider` | `str` | 提供方 |
| `base_url` | `str` | 推理接口地址 |
| `api_mode` | `str` | 调用模式 |
| `api_call_count` | `int` | 当前 turn 内第几次 API 请求 |
| `api_duration` | `float` | 请求耗时，秒 |
| `finish_reason` | `str \| None` | 结束原因 |
| `message_count` | `int` | 请求消息数 |
| `response_model` | `str \| None` | 响应里返回的模型名 |
| `usage` | `dict \| None` | 归一化后的 usage 摘要 |
| `assistant_content_chars` | `int` | assistant 文本长度 |
| `assistant_tool_call_count` | `int` | assistant 返回的 tool call 数量 |

### 返回

- 返回值当前**不消费**

---

## 9. `on_session_start`

### 作用

新 session 建立时的一次性初始化点。

### 调用时机

在 brand-new session 首轮触发；续聊不会触发。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | `str` | 新会话 ID |
| `model` | `str` | 当前模型 |
| `platform` | `str` | 当前平台 |

### 返回

- 返回值当前**不消费**

---

## 10. `on_session_end`

### 作用

一次 `run_conversation()` 结束时的收尾点。注意它更接近“**一轮结束**”，不是“会话真正结束”。

### 调用时机

- 正常路径：每次 `run_conversation()` 返回前触发
- CLI 兜底路径：若 CLI 在 agent 处理中直接退出，也会补发一次

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | `str` | 会话 ID |
| `completed` | `bool` | 是否正常完成 |
| `interrupted` | `bool` | 是否中断 |
| `model` | `str` | 当前模型 |
| `platform` | `str` | 当前平台 |

### 返回

- 返回值当前**不消费**

---

## 11. `on_session_finalize`

### 作用

真正 session 边界结束时的通知点，适合做最终 flush/收尾。

### 调用时机

会在以下场景触发旧 session 的 finalize：

- CLI 退出
- CLI `/new`
- gateway 关闭活跃 agent
- gateway 清理过期 session
- gateway reset 旧 session

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | `str \| None` | 旧会话 ID，没有则可能是 `None` |
| `platform` | `str` | `cli` 或具体 gateway 平台名 |

### 返回

- 返回值当前**不消费**

---

## 12. `on_session_reset`

### 作用

新 session 已切换完成后的通知点。

### 调用时机

- CLI `new_session()` 创建新 session 后触发
- gateway reset 完成并拿到新 session ID 后触发

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | `str` | 新 session ID |
| `platform` | `str` | `cli` 或具体 gateway 平台名 |

### 返回

- 返回值当前**不消费**

---

## 13. `subagent_stop`

### 作用

子代理结束后的通知点，适合记录 orchestration 行为。

### 调用时机

在 `tools/delegate_tool.py` 中，每个 child agent 完成后触发一次。  
即使是批量 delegate，也会**每个 child 调一次**。  
并且是在**父线程串行触发**，避免插件处理并发复杂度。

### 入参

| 参数 | 类型 | 说明 |
|---|---|---|
| `parent_session_id` | `str` | 父 agent 的 session ID |
| `child_role` | `str \| None` | 子 agent 的角色标记 |
| `child_summary` | `str \| None` | 子 agent 总结 |
| `child_status` | `str` | 子 agent 状态 |
| `duration_ms` | `int` | 子 agent 耗时 |

### 返回

- 返回值当前**不消费**

---

## 最容易混淆的几个点

### `on_session_end` vs `on_session_finalize`

- `on_session_end`：更接近**每轮结束**
- `on_session_finalize`：更接近**会话边界结束**

### `pre_llm_call` / `post_llm_call` vs `pre_api_request` / `post_api_request`

- `pre_llm_call` / `post_llm_call`：**按 turn**
- `pre_api_request` / `post_api_request`：**按底层模型请求**

一轮对话里，后者可能触发多次。

### `transform_terminal_output` vs `transform_tool_result`

- `transform_terminal_output`：只管 `terminal` 工具输出
- `transform_tool_result`：面向**所有工具**的最终结果字符串

---

## 代码定位

| 主题 | 文件 |
|---|---|
| hook 定义、注册、统一调用 | `hermes_cli/plugins.py` |
| tool 相关 hook | `model_tools.py` |
| terminal 输出改写 hook | `tools/terminal_tool.py` |
| LLM / API / session hook | `run_agent.py` |
| gateway 入站 hook / reset / finalize | `gateway/run.py` |
| subagent hook | `tools/delegate_tool.py` |

