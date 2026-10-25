# 编译执行模块

## 范围与环境

本模块实现 ENV-01、ENG-01、ENG-02：按固定基线编译登记程序、执行全部输入、校验原始输出并保留证据。输出是内部执行记录包，不是 `contracts/experiment.schema.json` 定义的完整实验结果。ELF 指标、推荐、归因、产品 CLI 和报告由相应任务继续实现。

运行环境为 Linux/WSL2 Ubuntu 24.04、Python 3.12。执行模块本身仅使用 Python 标准库；Schema 和公共检查使用 `requirements-foundation.txt`。Windows 不执行编译或 QEMU，缺少工具时显式失败。

```sh
sudo apt-get update
sudo apt-get install gcc-riscv64-linux-gnu binutils-riscv64-linux-gnu qemu-user python3-venv
python3 -m venv .venv-execution
.venv-execution/bin/python -m pip install -r requirements-foundation.txt
.venv-execution/bin/python -m unittest discover -s backend/tests -v
.venv-execution/bin/python scripts/check_execution_real.py
```

最后一条命令对现有 3 个程序、全部输入及 O0/O2/Os 分别执行两轮，共 54 次 QEMU 运行，核对每次输出与两轮 ELF 哈希，随后独立核查原始执行证据。该命令属于开发检查，不替代待实现的 `python -m optipilot` 产品入口。

## Python 接口

```python
from pathlib import Path
from backend.app.execution import execute, experiment_session
from backend.app.execution_types import ExecutionRequest

root = Path.cwd().resolve()
request = ExecutionRequest("sum_u32", ("O0", "O2", "Os"))
with experiment_session(root, root / "artifacts") as context:
    bundle = execute(request, repo_root=root, context=context)
    print(bundle.experiment_id)
    print([(variant.optimization, variant.status) for variant in bundle.variants])
```

- `ExecutionRequest` 只接受登记 ID 和 1–3 个不重复档位；档位为 tuple，保留请求顺序，不增加未请求配置。
- `experiment_session(repo_root, output_root)` 创建全新实验目录、120 秒单调时钟总预算，并持有单进程互斥锁。同一产物根目录另有跨进程文件锁。编排模块应在此 `with` 内完成后续分析和结果保存，避免提前释放全流程互斥。
- `execute(request, *, repo_root, context) -> ExecutionBundle` 在创建 session 的同一线程内调用一次。失败目录也不可重用。源码、配置、manifest、输入和预期值先快照，再使用快照编译与比较。
- `ExecutionBundle` 包含实验/版本/哈希、输入、实际环境、逐配置编译及逐用例记录、ELF 路径/哈希和共享 deadline；具体类型见 `backend/app/execution_types.py`。deadline 属于当前进程单调时钟，不得从归档恢复后据此继续执行。
- `ProcessRunner(context).run(argv, *, cwd, timeout_s, max_output_bytes, stdin=b"")` 可供 binutils 适配器复用。argv 只接受数组，cwd 必须在当前实验目录内。调用方负责保存分析原始产物；分析阶段沿用同一 context、5 秒工具时限和每流 1 MiB 限额。

进程使用 `shell=False`、独立 Linux 进程组和非阻塞管道。stdin、stdout、stderr 并行处理；读取时达到单流上限即停止并清理整组。正常结束也清理同组后代。总预算、取消 Event 和 KeyboardInterrupt 均触发清理；此机制适用于可信语料，不能代替任意代码执行的隔离沙箱。

工具从标准系统路径解析，子进程环境固定 `LC_ALL=C`、`LANG=C`，不继承用户的编译器注入环境变量。工具版本、编译器详细配置、目标 triplet、跨架构 libc 及相关包版本均归档。编译后进行 ELF64、小端、RISC-V、可执行类型和 LP64D 标志的最低限度检查；完整 ISA 属性、节、符号和编码解析仍由 ENG-03 验收。

## 状态与错误

配置状态 `execution_passed` 仅表示编译成功且全部登记用例通过，不能直接映射为完整实验的 `passed`。只有 SJS 分析模块成功、指标与原始证据可核对后，编排器才可生成完整 `passed`。

编译非零为 `compile_error`，不执行用例；编译阶段超时或超限分别保留 `timeout`、`output_limit`。编译成功后执行全部登记输入，逐例记录 `passed`、`runtime_error`、`wrong_answer`、`timeout` 或 `output_limit`；配置状态取清单顺序中的首个失败。超时/超限的退出码为 null。比较不 strip、不转换换行，也不丢弃 stderr。

`ExecutionError.code` 区分 `INVALID_REQUEST`、`UNKNOWN_BENCHMARK`、`EXPERIMENT_BUSY`、`TOOLCHAIN_UNAVAILABLE`、`REQUEST_TIMEOUT`、`EXPERIMENT_CANCELLED` 和 `INTERNAL_ERROR`。总预算耗尽或基础设施错误终止实验；已完成配置和当前命令的可用日志保留，根目录不生成完整执行包。KeyboardInterrupt 清理后原样抛出。外层 CLI/API 按原有契约转换错误，不返回 mock。

## 证据目录

每个实验使用 `artifacts/exec-<UUID>/`：

| 路径 | 内容 |
| --- | --- |
| `baseline.json`、`manifest.json`、`request.json` | 原始配置/清单与实际登记请求 |
| `source/main.c`、`inputs/<case>/` | 实际编译源码、原始输入和独立预期输出 |
| `environment.json`、`environment/<probe>/` | 环境信息、版本探测参数和原始输出 |
| `<profile>/program.elf` | 编译成功的目标文件 |
| `<profile>/compile/`、`<profile>/runs/<case>/` | `stdout.bin`、`stderr.bin`、`process.json`，包括实际 argv、状态、退出码、时间和流哈希 |
| `<profile>/execution.json` | 已完成配置的中间记录，便于总实验失败后诊断 |
| `execution.json` | 全部请求配置执行结束后的内部记录包 |
| `error.json` | 基础设施/请求异常记录；不是成功实验结果 |

JSON 中的输出是 UTF-8 展示文本，非法字节使用替代字符显示；正确性始终比较原始 bytes，原始 `.bin` 保留准确内容。展示文本不得用于重新计算原始哈希。失败数据同样为实测，`is_mock` 不因失败而改为 true。

`check_execution_real.py` 在产物根目录生成 `summary.json`，记录全部实验 ID、运行次数、重复 ELF 哈希、实现/检查脚本哈希和产物 SHA-256。CI 另记录实际 `GITHUB_SHA`，并上传原始数据，保留期为 30 天；长期发布需团队另行归档。运行产物不进入 Git。

## 对接检查与验收边界

```sh
.venv-execution/bin/python scripts/check_execution_integration.py --execution artifacts/EXPERIMENT_ID/execution.json
.venv-execution/bin/python scripts/check_execution_integration.py --execution artifacts/EXPERIMENT_ID/execution.json --experiment artifacts/EXPERIMENT_ID/result.json
```

第一条核对源码、输入、配置、原始流、ELF 哈希、命令、用例顺序和首个失败状态。记录包绝对路径按原 workspace 映射到当前归档目录，支持 CI artifact 下载后的检查。第二条还核对最终 JSON Schema、环境/哈希、实际命令、用例和推荐门控，防止丢失或改写执行记录。

此检查不证明静态指标、归因证据定位、报告一致性或独立评估通过。正向投影测试使用实际执行记录和明确的 `analysis_error`，不构造虚假的静态结果。INTEG-01 的后续条件如下：

| 阶段 | 等待交付 | 后续复核 |
| --- | --- | --- |
| M0 | ENG-03/04、CLI-01、REPORT-01 | 真实完整实验、独立 ELF 指标、推荐、CLI 退出码和 Markdown 一致性 |
| M1 | ATTR-01 | 真实编码、符号范围、节成员关系、规则证据和拒判 |
| M2 | GOLD-01、EVAL-01、REPORT-02 | 两人分别标注、分歧裁决、留出隔离、实际统计及最终结论 |

上述模块或第二位复核人的记录缺失时，INTEG-01 保持进行中，不因执行检查通过而标为完成。
