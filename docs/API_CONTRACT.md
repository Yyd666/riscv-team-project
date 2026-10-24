# API 契约 0.1.0

实现状态：待实现。接口前缀为 `/api/v1`，数据格式为 UTF-8 JSON。本地服务地址建议使用 `127.0.0.1:8000`，Vite 开发代理转发 `/api`。服务范围限定为本机开发环境。

## GET /api/v1/health

HTTP 200，返回 `{"status":"ok","ready":false,"missing_tools":["qemu-riscv64"]}`。`status` 表示 API 服务状态，`ready` 表示工具链就绪状态。全部工具可用时，返回 `ready: true`、`missing_tools: []`；前端分别展示服务状态与工具链状态。

## GET /api/v1/benchmarks

HTTP 200，返回 `contracts/examples/benchmarks.mock.json` 所示结构：`schema_version`、`is_mock`、`benchmarks`。每项为 `id`、`name`、`description`、`case_ids`。实际内容来自 manifest；真实服务返回 `is_mock: false`。

## POST /api/v1/experiments

首版采用同步、串行执行方式，不提供后台任务及取消接口。

机器可读请求约束见 `contracts/experiment-request.schema.json`；未知但格式合法的样例 ID 在后端注册表检查阶段返回 400。

请求示例：

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

每次运行保存 `case_id`、状态、`exit_code`（超时未正常结束时为 `null`）、`stdout`、`stderr`、`wall_time_ms`。运行时间仅作诊断。`passed` 要求退出码、stdout 和 stderr 均与清单期望一致，输出按原始字节比较。

`selection` 为 `null` 或 `{ "objective": "min_text_section_bytes", "optimization": "Os", "evidence": "static_size_only" }`。推荐仅依据静态体积，具体规则见技术基线。

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
| 504 | `REQUEST_TIMEOUT` | 实验总预算耗尽，清理全部子进程；单个用例超时记入方案结果 |
| 500 | `INTERNAL_ERROR` | 未预期基础设施异常；前端不得回退 mock |

内部异常不向客户端暴露堆栈或私密路径；具体错误保存在本机日志。用户代码自身失败属于方案状态，不全部映射为 HTTP 500。

## Mock 数据与联调

`contracts/examples/experiment.mock.json` 中的体积、指令数、时间和环境为合成数据，仅用于 UI 与 Schema 联调。mock 必须标记 `is_mock: true`，界面显示“演示数据”。实测报告使用 `is_mock: false`，并具备对应的执行记录和数据来源。

错误状态示例：`experiment.failed.mock.json` 表示全部方案编译失败且无推荐；`experiment.partial.mock.json` 表示 O0 的首个用例输出错误，其余方案仍可参与推荐。两份文件均为合成数据。

前端提供显式的 mock / API 模式切换，并在实现 PR 中说明配置方式。API 模式出现错误时直接展示错误信息。Schema 检查负责结构校验；执行记录、哈希与推荐规则由后端语义校验及集成验收覆盖。
