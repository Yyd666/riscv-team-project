# API 契约 0.1.0

此文档是待实现约定，不代表服务已存在。前缀 `/api/v1`，JSON UTF-8；本地服务建议 `127.0.0.1:8000`，Vite 开发代理转发 `/api`。后端不开放公网执行服务。

## GET /api/v1/health

HTTP 200，返回 `{"status":"ok","ready":false,"missing_tools":["qemu-riscv64"]}`。`status` 表示 API 活着，`ready` 表示全部工具可用；工具齐备时 `ready: true`、`missing_tools: []`。前端不能将两者混同。

## GET /api/v1/benchmarks

HTTP 200，返回 `contracts/examples/benchmarks.mock.json` 所示结构：`schema_version`、`is_mock`、`benchmarks`。每项为 `id`、`name`、`description`、`case_ids`。实际内容来自 manifest；真实服务返回 `is_mock: false`。

## POST /api/v1/experiments

首版同步执行、单实验串行，不支持后台任务和取消接口。请求示例：

机器可读请求约束见 `contracts/experiment-request.schema.json`；未知但格式合法的样例 ID 在后端注册表检查阶段返回 400。

```json
{
  "benchmark_id": "sum_u32",
  "optimizations": ["O0", "O2", "Os"]
}
```

仅允许这两个字段；`optimizations` 必填，1 到 3 个不重复 ID，只能是 `O0`、`O2`、`Os`。请求档位顺序保留在响应中。始终运行该样例的全部登记用例，顺序与 manifest 相同。请求不接收源码、路径、自由 flags 或任意 stdin。

HTTP 200 表示实验已经执行结束，响应符合 `contracts/experiment.schema.json`。其中某些或全部编译方案仍可能失败；前端逐方案展示 `status`。单进程服务实验互斥，忙时返回 409。总请求预算 120 秒，前端超时建议 130 秒，超时不得再发一条无提示的重试请求。

## 结果字段

根字段：版本、实验 ID、`is_mock`、UTC 创建时间、基线版本及配置哈希、语料版本、样例 ID、源码哈希、各输入/预期输出哈希、实际环境、方案结果、推荐。

每个方案包含 `optimization`、`status`、`compile_argv`、`run_argv`、`analysis_argv`、`diagnostics`、`kernel_disassembly`、`metrics` 和 `runs`。命令必须是实际使用的参数数组；`analysis_argv` 是多条命令的数组。日志不能携带凭据。

方案状态：`passed`、`compile_error`、`runtime_error`、`wrong_answer`、`timeout`、`output_limit`、`analysis_error`。编译失败不运行，`runs` 为空；编译成功后按序运行全部用例（基础设施/总预算中止除外），即使一个用例输出错误也保留其余结果。方案状态取按 manifest 顺序遇到的第一个用例失败；全部用例通过后分析失败则为 `analysis_error`。仅 `passed` 有非空 metrics 且参与推荐，其余 metrics 为 `null`。

每次运行保存 `case_id`、状态、`exit_code`（超时未正常结束时 `null`）、`stdout`、`stderr`、`wall_time_ms`。运行时间仅作诊断。`passed` 必须同时满足退出码、stdout、stderr 清单期望；没有“输出看起来差不多”的成功状态。

`selection` 为 `null` 或 `{ "objective": "min_text_section_bytes", "optimization": "Os", "evidence": "static_size_only" }`。规则见基线，不允许把宿主耗时偷偷加入选择条件。

## 错误响应

统一格式：

```json
{
  "error": {
    "code": "UNKNOWN_BENCHMARK",
    "message": "Unknown benchmark ID: missing",
    "details": {}
  }
}
```

| HTTP | code | 场景 |
| --- | --- | --- |
| 400 | `UNKNOWN_BENCHMARK` | 未登记 ID |
| 422 | `INVALID_REQUEST` | 非法字段、格式、优化选项或重复档位；覆盖框架默认校验响应以保持结构 |
| 409 | `EXPERIMENT_BUSY` | 已有实验运行 |
| 503 | `TOOLCHAIN_UNAVAILABLE` | 缺工具、版本探测失败或工具不支持固定目标；details 列出原因 |
| 504 | `REQUEST_TIMEOUT` | 总预算耗尽，清理全部子进程；不是某个用例的局部超时 |
| 500 | `INTERNAL_ERROR` | 未预期基础设施异常；前端不得回退 mock |

内部异常不向客户端暴露堆栈或私密路径；具体错误保存在本机日志。用户代码自身失败属于方案状态，不全部映射为 HTTP 500。

## Mock 与交接

`contracts/examples/experiment.mock.json` 中体积、指令数、时间和环境全部为人为示例，只用于 UI/Schema 联调。`is_mock: true` 是必需标记，界面显著显示“演示数据”。正式报告必须 `is_mock: false`，不能通过改这个布尔值把 mock 当真实结果。

补充状态资产：`experiment.failed.mock.json` 表示所有方案编译失败、无推荐；`experiment.partial.mock.json` 表示 O0 的首个用例输出错误，其余方案仍可参与推荐。它们同样没有真实执行过工具。

前端切换 mock/real 必须显式，默认真实模式报错就显示报错；实现 PR 提交开关说明。Schema 验证只覆盖结构，不能证明命令确实执行、哈希正确或推荐符合算法，后端仍须执行语义验证与集成验收。
