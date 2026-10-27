# 评估执行与证据追溯

## 输入与执行边界

评估运行器仅读取当前仓库登记的 `evaluation/corpus.json`。源文件限定为登记 ID 对应的 `benchmarks/ID/main.c` 或 `evaluation/programs/ID/main.c`，输入和预期输出限定在同一程序的 cases 目录。源码哈希、已登记输入/预期输出哈希、唯一用例 ID 和完整用例集合在编译前核对；路径越界、符号链接越界、哈希变化和遗漏用例均拒绝执行。

运行器将已核对的字节保存为独立的登记快照，然后调用正式 `run_experiment`。批次采用单进程互斥及产物根目录的跨进程锁；编译选项、Linux 限制、工具探测、实际版本、全部用例校验、120 秒实验预算、3 秒单次运行限额、输出限额、进程组清理和失败归档沿用现有执行模块。产品 CLI 的原有登记范围保持不变。

## 草稿诊断

当前语料已机器冻结为开发/留出各 6 个程序，`0.1.1` 登记 MIT 许可，双人独立标注及数值/oracle 复核仍待完成。可在 Linux/WSL 中显式执行登记冒烟程序，诊断评估链路：

```sh
python -B scripts/run_evaluation_corpus.py \
  --corpus evaluation/corpus.json --output artifacts/evaluation-execution \
  --diagnostic --program sum_u32 --program dot_i32 --program threshold_count
```

每次创建新的 `evaluation-UUID` 目录，不复用旧实验目录。成功退出 0 只表示所选程序完成真实诊断运行。`batch.json` 明确记录 mode=diagnostic、语料缺口和 acceptance_ready=false；旧清单没有用例哈希时记录 case_binding_origin=discovered_diagnostic。诊断数据可用于排查问题，正式评估门槛不会接收这些记录。

## 正式运行

正式运行使用同一命令并省略 `--diagnostic`、`--program`。运行前要求清单冻结、数量和集合隔离检查通过；每个程序须完整登记 cases 及其哈希。当前清单已通过机器冻结检查，本地正式批次完成 12 程序、36 配置和 108 用例。清单不满足要求时命令返回 3，且不创建实验目录。

```sh
python -B scripts/run_evaluation_corpus.py \
  --corpus evaluation/corpus.json --output artifacts/m2-formal-reproduction
```

cases 项包含 case_id、stdin、expected_stdout、stdin_sha256、expected_stdout_sha256；路径使用仓库相对 POSIX 路径，哈希针对原始字节。正式评价还要求完整清单、与当前清单一致的捕获哈希、已提交的实现版本、完整实现源码哈希清单及真实执行记录。双方独立标注、语料来源及已登记许可范围核对仍是单独验收要求。

`0.1.1` 清单新增 `license_file` / `license_sha256`，执行前核对固定的 `evaluation/LICENSE` 原文及哈希，登记快照保存 `LICENSE`，实现快照保存许可及范围说明。历史清单缺少这两个字段时仍按原格式读取；原始 `0.1.0` 证据不改写。复核历史批次时使用其内部清单，不将当前许可元数据混入历史实验。许可范围和关联规则见 [语料来源与许可](CORPUS_LICENSE.md)。

## 证据目录

| 路径 | 内容 |
| --- | --- |
| corpus.json | 执行时原始语料清单 |
| registry-repository/ | 核对后的源码、输入、预期输出和固定基线登记快照 |
| implementation.json | 实际 Git 提交、相对该提交变化的实现文件、源码哈希、Python 包版本 |
| implementation/ | 实际使用的实现、Schema、配置和登记清单原文 |
| experiments/exec-UUID/ | 正式执行模块生成的版本、源码/输入/配置快照、原始编译/QEMU 输出、ELF、分析记录及归因 |
| experiments/exec-UUID/evaluation.json | 正式/诊断模式、原始清单、实现记录及登记快照的哈希关联 |
| batch.json | 请求程序、未开始/执行中程序、逐程序结果、完成状态、实际退出码及可共享文件哈希 |

batch.json 的 artifact_sha256 不包含自身和临时操作标记 `.execution.lock`、`.execution-started`，其余列出的文件均应随归档保存。实现存在未提交变化时 modified_files 明确列出，不能按已提交版本计入正式评价。

## 退出与核验

- 0：请求程序的真实诊断或正式运行均成功，不表示 M2 已验收。
- 2：输入或登记无效，诊断预检发现路径、哈希或用例集合错误。
- 3：正式冻结检查未通过，或编译/运行/静态分析失败。
- 4：正确性与静态分析均成功，但强制归因不完整。
- 5：工具缺失、总预算、取消或其他基础设施失败；保留已开始实验的原始错误包。

编译、输出或分析失败打印 FAIL 并保存非零退出码；工具缺失时记录未完成程序，不写成全部成功。已成功的其他程序继续保留。

可针对登记快照复核执行记录：

```sh
python -B scripts/check_execution_integration.py \
  --registry-root artifacts/evaluation-execution/BATCH_ID/registry-repository \
  --execution artifacts/evaluation-execution/BATCH_ID/experiments/EXPERIMENT_ID/execution.json \
  --experiment artifacts/evaluation-execution/BATCH_ID/experiments/EXPERIMENT_ID/result.json
```

该检查核对原始流、执行状态、固定基线、登记源码/用例和独立 GNU ELF 指标。`evaluate_attribution.py` 仍单列独立字节误差、缺失分母和正式评估资格；报告展示正式资格不成立的具体原因。

## 独立 Ubuntu 复现

工作流 `M2 formal reproduction` 使用全新 Ubuntu 24.04 runner 和已提交的实现执行完整正式语料，不使用 `--diagnostic`。修改该工作流的 PR 自动运行；主线合并后也可从 Actions 手动选择提交运行。它与常规执行 CI 中的三个程序诊断检查分别记录。

工作流核对冻结批次全部文件哈希，调用评估器重验原始执行记录、独立 GNU 字节误差、三档推荐与正式资格，并生成机器评估报告。要求 12 个程序、36 个通过配置、108 个正确用例、24 个有效比较和 48 项独立规则核验完整覆盖；机器通过仍保留 `acceptance_ready=false`，不生成成员标注或签字。

`m2-formal-evidence-提交SHA` artifact 保存原始批次、源码/输入/实现快照、版本、原始编译/QEMU/GNU 输出、ELF、sidecar、摘要与 Markdown 报告。`reproduction.json` 区分实际实现提交与 GitHub 事件 SHA，`bundle-sha256.json` 列出实际上传文件的哈希；保留期 30 天，最终材料须另存长期证据。

独立批次使用新 ID，不替换双方正在标注的原正式批次。下载 artifact 后须核对上传清单；再与本地批次逐程序/档位比较源码、输入、工具版本、ELF 和静态指标，记录环境或输出差异。当前技术基线没有锁定软件包版本，不预先保证不同机器 ELF 逐字节一致。该机器复现不替代双人成员复核、已登记许可范围核对或最终提交审核。
