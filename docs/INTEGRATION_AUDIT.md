# 集成审计与剩余交付计划

## 范围和顺序

目标保持任务板的必需交付范围，按依赖顺序核实 ENV-01、ENG-01/02 和 INTEG-01，并验证所对接的 CLI、报告、归因、语料、评估和材料。现有原始实验数据保留；自动检查、正式评价和双方标注分别记录。

| 顺序 | 工作 | 当前证据 | 尚需满足的条件 |
| --- | --- | --- | --- |
| 1 | 修复归因证据门控 | PR #17 已合并，CI 通过；直接 ELF 边界/编码核对、执行及分析时哈希、报告消费校验通过 | 后续变更保持回归 |
| 2 | 登记语料集成 | PR #17/18 和 main CI 通过；三程序九配置、27 次主要运行；6 个比较与独立 GNU 一致；Ubuntu CI 归档核对及九份 ELF 跨环境哈希一致 | 后续变更保持回归 |
| 3 | 完整归因负例 | PR #18 已合并，CI 通过；6 类真实派生程序、12 配置、36 用例及逐类状态通过；下载后核对 656 份证据文件和 12 份 ELF | 后续变更保持回归；不计为独立样本 |
| 4 | 修订评估语料 | 机器冻结通过：开发/留出各 6 个不同算法家族，源码、输入和 oracle 哈希齐全；来源标识已分开 | 团队确认许可证、来源声明、数值范围和 oracle 审阅；双人标注仍待完成 |
| 5 | 冻结与执行 | 评估运行器复用正式执行模块；12 程序、36 配置、108 用例正式批次全部通过，保存版本/快照/原始输出 | 正式批次需在提交后的干净实现上重跑，且归档后由独立环境核验 |
| 6 | 双方标注与评估 | 新统计独立核对 24 个 O2→候选比较，字节误差 24/24 为 0，固定 O2/Os/穷举差额与失败计数已生成 | 两位成员独立标注、分歧裁决、B0/B1/B2/A1/A2 分集合计数和最终报告 |
| 7 | 报告及演示材料 | 报告可显示证据路径/哈希/定位；真实成功和非零退出码已实测 | 合格评估最终报告、录屏与材料清单；官方资格、署名、截止时刻及许可由团队核对 |

M2 不因为清单文件有 12 项或摘要输出 1.0 而完成；API/UI 保持任务板原有可选范围。

## 本次修复的判定边界

- `kernel_code_bytes <= text_section_bytes` 不能证明节成员关系；现由 ELF 符号节索引及地址区间确定。
- 文件存在和新计算的文件哈希不能证明与执行时一致；真实 sidecar 必须与执行记录和分析时哈希关联。
- `4*ΔN - 2*ΔN16 + ΔU = ΔK` 是内部恒等式；独立字节误差使用重新运行 GNU 工具获得的 ELF 指标。
- 旧侧文件缺少分析时记录或内容已变化时，不作为完整解释消费。重新运行真实 CLI 会生成可核对的新证据，禁止补造历史版本信息。
- mock、重复实验、缺失程序和不完整配置不填充为实测样本。独立标注缺失时 `acceptance_ready` 不设为 true。

## 复现命令

在安装真实 RISC-V GNU 工具、QEMU 及基础依赖的 Linux/WSL 中：

```sh
python -B -m unittest discover -s backend/tests -v
python -B scripts/check_cli_real.py --output artifacts/cli-check
python -B scripts/check_foundation.py
python -B scripts/check_design_contracts.py
git diff --check
```

`check_cli_real.py` 每次创建新目录，保存全部 CLI 命令、stdout/stderr、执行记录、ELF、分析输出、sidecar、报告、摘要及 SHA-256 清单。主流程覆盖 3×3×3=27 次用例；另有 O2-only、缺 O2 的强制归因和未登记程序退出码检查。原始证据检查复用 `check_execution_integration.py`；GNU 参考不导入产品 ELF 解析器。

当前真实检查目录：WSL2 `/home/yyd/work/optipilot-audit-evidence/final-check/check-c439068d55154bfc995acc0ebb8c91f7/`。主流程 27 次、6 个比较全部通过；强制归因两种退出码为 4，未登记程序为 2。该目录的 summary.json 保存完整哈希清单。两类真实 partial 用例另由 `backend/tests/test_attribution_real.py` 检查，不计入独立评估语料样本数。

六类负例核验摘要位于 WSL2 `/home/yyd/work/optipilot-audit-evidence/negative-audit-03.json`，原始证据目录由摘要的 evidence_root 给出，含 668 份文件哈希。未知 16/32 位及截断编码为 partial/R001 abstained；函数在其他节为 partial/R002 not_applicable；符号缺失与分析证据冲突为 unavailable。证据冲突在真实成功控制实验后篡改归档符号边界，旧 sidecar 被报告拒收，重新归因明确拒判。编译、QEMU 或工具失败会使总检查失败；首次截断夹具出现运行错误的 negative-audit-01 原始记录仍保留，不计为通过。

旧语料的诊断评估命令仍可运行，但当前应返回 3；不会因此通过正式验收：

```sh
python -B scripts/evaluate_attribution.py \
  --corpus evaluation/corpus.json --artifacts artifacts/cli-check/CHECK_ID/experiments \
  --output artifacts/diagnostic-evaluation.json
python -B scripts/render_evaluation_report.py \
  --input artifacts/diagnostic-evaluation.json --output artifacts/diagnostic-evaluation.md
```

新摘要版本为 0.2.0。缺失值显示为缺失；报告列出分母、固定配置和穷举差额、零收益、失败及语料问题。旧 0.1.0 摘要须重新核验后生成报告。

评估执行的输入边界、诊断/正式模式、快照目录及退出码见 [评估执行与证据追溯](EVALUATION_EXECUTION.md)。当前清单缺少冻结用例哈希，正式命令返回 3，不启动编译；诊断命令可显式选择登记程序完成链路复核。
