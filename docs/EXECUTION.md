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

最终 JSON 声明 `passed` 时，检查在 Linux/WSL2 上另外运行 GNU `readelf`、`size` 与 `objdump`，独立核对 ELF64/RISC-V/LP64D/静态链接与 RV64GC 属性、完整 `.text`、`kernel` 符号范围和 16/32 位指令计数。反汇编编码须逐条匹配 ELF 原始字节，最终 JSON 的指标及指令文本也必须一致。未知编码、边界缺失或工具输出不支持时拒绝验收。该参考实现只位于检查脚本，不作为产品分析引擎或报告数据源；每次工具调用仍使用受限执行器。

参考实现通过手写 3 指令、8 字节、其中 2 条压缩指令的 RV64GC ELF 校验，另覆盖缺失符号、未知编码、指标篡改和反汇编操作数篡改。投影测试覆盖明确的 `analysis_error` 及独立核验指标的 `passed`，均为接口检查构造，不计为 SJS 产品模块已经交付。

此检查不证明归因证据定位、报告一致性或独立评估通过。INTEG-01 的后续条件如下：

| 阶段 | 等待交付 | 后续复核 |
| --- | --- | --- |
| M0 | ENG-03/04、CLI-01、REPORT-01 | 真实完整实验、独立 ELF 指标、推荐、CLI 退出码和 Markdown 一致性 |
| M1 | ATTR-01 | 真实编码、符号范围、节成员关系、规则证据和拒判 |
| M2 | GOLD-01、EVAL-01、REPORT-02 | 两人分别标注、分歧裁决、留出隔离、实际统计及最终结论 |

上述模块或第二位复核人的记录缺失时，INTEG-01 保持进行中，不因执行检查通过而标为完成。

## 执行与候选分析器的集成检查

`scripts/check_analysis_integration.py` 将真实执行记录交给指定 Git 提交中的 ENG-03 候选实现，再独立核对静态指标。该开发检查只读取已获取的本地 Git 对象，不创建工作树，不修改候选分支；当前加载边界为 `backend/app/analysis/elf.py` 单模块及已合并的执行接口。候选模块是明确选择的可信仓库代码，不提供给产品 API 或任意上传执行流程。

```sh
git fetch origin
python3 scripts/check_analysis_integration.py --analysis-ref origin/sjs --output artifacts/analysis-integration
```

每次执行创建独立 `integration-<UUID>` 目录，固定候选提交和源码 SHA-256，保存候选源码快照、消费方提交/代码哈希、全部实际工具参数、原始 stdout/stderr 和分析输出。源模块按固定 Git 路径读取；测试注入的记录器只保存真实工具调用，不替换工具结果。检查产物不进入 Git。

- 正常路径：3 个注册程序、3 个档位、27 次 QEMU 校验；9 份 ELF 的实际分析指标与独立 GNU 参考完全一致才通过。
- 真实负例：16/32 位未知编码、缺失符号、非 `.text` 函数、符号越界、动态 ELF、RV64IM/LP64。负例只编译和分析，不作为注册语料运行，不计为独立评估样本。
- 基础设施失败、缺工具、非零工具退出、超时或取消不能记为成功拒判；原始日志保留，摘要显式记录基础设施错误。
- 退出码 0 表示本次边界检查全部通过；1 表示至少一个实际用例未通过；5 表示初始化或基础设施失败。成功的正常样例不能掩盖失败负例。

`summary.json` 分别列出正负例、预期/实际状态、实验 ID、ELF 哈希、候选版本及所有产物哈希。此摘要是集成验收记录，不是产品 `result.json`，也不替代完整 CLI、报告、归因和双人评估验收。

`Linux execution checks` 工作流在 pull request 中自动获取 `sjs` 分支当时的头提交，以 `FETCH_HEAD` 执行集成检查。该候选随分支更新，不等于固定提交，也不一定等于被审查 PR 的头提交；摘要记录本次实际解析出的完整 SHA 与源码哈希。自动检查用于持续对接，不能替代发布版本验收。

发布或最终验收必须明确提供经核对的完整提交 SHA，并记录消费方实现版本。手动触发支持 `analysis_ref`：留空时仅运行执行回归；非空时还运行指定候选的集成检查。PR 自动检查和指定候选的手动检查均上传 `analysis-integration-evidence-<消费方提交>`，保留 30 天。失败检查同样上传已生成的证据；无证据时上传步骤报错。该输入执行的是成员选定的可信仓库代码。

候选导入产生的 `SyntaxError`、`TypeError` 及其他未预期的普通异常，也按基础设施失败返回 5，保留已生成的摘要和原始证据。命令行语法错误沿用 argparse 的退出码 2；进程中断不转换为用例失败。

```sh
gh workflow run execution.yml --ref yyd -f analysis_ref=d779581b40915000cf8f5311a3c480a1914170bc
```
