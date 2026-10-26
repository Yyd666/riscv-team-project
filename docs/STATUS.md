# 项目状态与验证记录

## 当前定位

RISC-V OptiPilot 面向 RV64GC，基础能力为程序校验、静态分析与三档配置推荐；自研模块开发目标为函数级代码体积变化归因。阶段定义以 PROJECT_SCOPE、ATTRIBUTION_DESIGN 和 EVALUATION 为准。

## 已完成内容

- 项目范围、稳定 ADR、CLI 优先的任务依赖、开发与分层验收规范。
- 必需交付工作量分配（sjs 60%、yyd 40%）、模块文件责任、执行记录包边界及独立开发/集成验收依赖；各模块实际状态见下方记录。
- 原有 RV64GC/LP64D、O0/O2/Os 基线和实验请求/结果契约 0.1.0。
- 3 个可信 C 样例及 9 组独立预期输入输出。
- R001/R002 的统计定义、推荐/解释范围、证据与拒判契约，以及合成联调示例。
- 独立评估计划、对照及消融定义、样本隔离、标注与复现要求。
- 公共配置/契约检查脚本、CI、PR/Issue 模板。
- Linux 受限子进程执行器、固定基线编译、QEMU 全部用例校验、源码/输入快照及执行记录包。
- 单进程实验互斥、产物根目录跨进程锁、超时/输出限额/取消/中断清理、原始日志和失败归档。
- 真实三程序三档两轮共 54 次运行与重复 ELF 哈希检查；执行证据及结果投影检查已建立。

## 待完成内容

| 阶段 | 待完成工作 |
| --- | --- |
| M0 | 执行模块已实测；仍需完整 ISA/ELF 解析、推荐、产品 CLI、报告生成器与全流程集成 |
| M1 | 原始 ELF 归因引擎、证据解析与实际正负例验证 |
| M2 | 扩展语料、独立留出集、双人标注、实测评价与最终报告 |
| 可选 | FastAPI、前端及联调 |

当前 main 业务后端包含 execution 和执行类型；SJS 的 ENG-03 候选位于 PR #4，提交 d779581 的执行/分析边界正负例已通过，尚未合并。产品 CLI、归因引擎和效果评估待交付，尚无优化收益结论。评估计划中的程序数量为建设目标，合成 JSON 不计为真实编译或算法测试结果。

## 基线与兼容性

完整 `.text` 仍为唯一推荐目标，`kernel` 为单独诊断对象。编译配置、现有实验 Schema 及已登记 C 程序保持原版本，新增归因文件独立版本化。宿主耗时仅作诊断。

## 验证记录

既有基线的 Ubuntu CI 已验证公共文件与宿主 GCC 样例，记录见 [基线工作流](https://github.com/Yyd666/riscv-team-project/actions/runs/40102619442)。该历史记录未执行 RISC-V 交叉编译、QEMU、实际归因算法或独立评估；当前执行实测见下方记录。

设计整合本地检查环境为 Windows / Python 3.10，使用现有独立基础检查环境：

| 检查 | 结果 | 覆盖范围 |
| --- | --- | --- |
| `check_foundation.py` | 通过 | 3 个程序、9 组预期值、5 份实验 mock、请求/结果 Schema、23 个本地链接 |
| `check_design_contracts.py` | 通过 | 5 份归因 mock、10 个拒绝反例、字节恒等式、实验/策略哈希、证据引用与评估隔离 |
| 合成示例重新生成 | 通过 | 两次生成的 7 份新增示例逐字节一致 |
| `git diff --check` | 通过 | 文档及脚本空白检查 |
| 设计整合阶段的 RISC-V / QEMU / ELF 归因 / 独立评价 | 当时未执行 | 当前执行实测见下；归因和独立评价仍待实现 |

合并前远程 CI 以对应 PR 的实际检查结果为准。契约反例检查不计为实际归因准确率。

2026-10-24 分工调整的本地验证（Windows / Python 3.10）：`check_foundation.py`、`check_design_contracts.py` 和 `git diff --check` 均通过；任务权重核对为 yyd 40、sjs 60，总计 100。此次仅修改文档，未执行 RISC-V 编译、QEMU 或业务集成。

## 执行模块验证（2026-10-25）

本地环境：WSL2 Ubuntu-Dev / Ubuntu 24.04、Python 3.12.3；真实 GCC riscv64 13.3.0、GNU binutils 2.42、QEMU 8.2.2、跨架构 libc 2.39。执行工作副本位于 Linux 文件系统，原始记录保存于 `/home/yyd/optipilot-yyd-execution/artifacts/execution-final/`，不进入 Git。

已完成 `scripts/check_execution_real.py` 的两轮全语料运行：3 个程序、3 个档位、每程序 3 组输入，共 54 次真实 QEMU 校验，输出匹配且两轮各档 ELF 哈希一致。宿主耗时仅用于诊断，不作为目标性能结论。

执行行为检查覆盖 Linux 进程组、双流限额、输入/输出并行、超时、取消、KeyboardInterrupt、失败路径、路径/选项拒绝、原始字节、用例继续执行及记录投影。本地运行 `$HOME/.venvs/optipilot-check/bin/python -m unittest discover -s backend/tests -v`，30 项检查均通过且无跳过；远程证据以提交后的 CI 实际结果为准。

执行实现提交为 `d79a6bf`，交付见 [PR #2](https://github.com/Yyd666/riscv-team-project/pull/2)。[Linux 实测 CI](https://github.com/Yyd666/riscv-team-project/actions/runs/40178085276) 与 [公共基础 CI](https://github.com/Yyd666/riscv-team-project/actions/runs/40178085266) 均通过；独立 Ubuntu CI 中同样通过 30 项检查及 54 次 QEMU 校验。已下载该 CI 的运行产物，核对 504 份文件 SHA-256、实现/检查脚本哈希，并对 6 份迁移后的执行记录逐份运行原始证据检查。记录包验证范围仍限于执行数据。原始数据见该 CI 的 `execution-evidence-d79a6bf94e1b29b32e52922d4de930b6151d4403` artifact，保留期 30 天。

`INTEG-01` 已建立执行证据、结果投影和独立 GNU ELF 参考检查；新增参考检查已通过 6 项定向用例，包括手写 3 指令/8 字节参考 ELF、缺失符号、未知编码、指标及操作数篡改。后续候选分析器对接见下方记录；产品 CLI、报告、归因、评估及第二位成员的独立复核记录仍待交付，M0/M1/M2 全流程尚未验收。

## 候选分析器集成验证（2026-10-25）

PR #2 已合并 main，合并提交为 `bcbf8c6`。针对 PR #4 的 SJS 提交 `c1f5a66ba5ed16892348e6fc0e6e00a71a42944c`，已完成正常路径真实对接：3 个程序、3 个档位、27 次 QEMU 校验通过；9 份 ELF 的候选分析指标与独立 GNU 参考一致。

新增开发检查 `scripts/check_analysis_integration.py` 固定候选源码版本，并保存实际命令、原始流、分析结果和产物哈希。真实负例 7 类中 6 类通过，`unknown_32` 未通过：原始 `0000000b` 被 objdump 显示为 `.word`，候选仍输出 `passed`、1 条静态指令；检查整体返回 1 并将摘要标为 `failed`。这是实际 ELF 拒判缺陷，不以正常路径通过抵消。

记录位于仓库内 `artifacts/analysis-integration/`，每次运行独立目录，以其中的 `summary.json` 及候选源码快照为准。16 位全零负例被实际 objdump 省略成 `...`，候选因覆盖不完整拒绝；该结果不证明所有未知 16 位编码均已正确处理。手写负例不计为独立评估样本。

随后针对修复提交 `d779581b40915000cf8f5311a3c480a1914170bc` 重跑同一检查：9 份正常 ELF 指标一致，27 次 QEMU 输出匹配，7 类负例全部拒判，整体退出码为 0。`unknown_32` 已返回 `analysis_error` 且不输出指标。原始记录位于 `artifacts/analysis-integration/integration-24de478cc4b74bc792e1c30706f743a4/summary.json`；该结论限定于实际覆盖的边界用例，不代表所有 ELF 或指令编码已验证。

消费方提交 `8d18fa4` 的[独立 Ubuntu 集成 CI](https://github.com/Yyd666/riscv-team-project/actions/runs/40265388704) 已通过 40 项检查、54 次执行回归及上述候选的 27 次集成运行、7 类负例。原始集成证据为该运行的 `analysis-integration-evidence-8d18fa4f428972755ba9c8d26abaa97bcd49ed55` artifact，保留 30 天。下载后核对 568 份文件哈希、消费方实现和候选源码的 Git 哈希，并验证三份迁移后的执行记录，均通过。此独立环境复跑仍仅验证执行/分析边界，不计为 M2 留出集评估或第二位成员审阅。

INTEG-01 的执行/分析接口已有可重复检查；最终验收仍需交付推荐/CLI/报告/归因/评估模块并完成双人复核。

## 维护记录

- 保留 OptiPilot 主线、CLI 必需交付和 mock 不替代实测的要求。
- 整合编码归因、整体/函数范围分离、独立评估与证据约定，修正报告生成器与最终报告的依赖。
- 2026-10-24：按 sjs 60%、yyd 40% 重新分配必需任务；分析、归因、CLI 及评估由 sjs 主责，编译执行和集成复核由 yyd 主责。新增 ADR-013 和并行模块边界，不改变编译基线、Schema 或业务实现状态。

- 2026-10-25：实现 ENV-01、ENG-01、ENG-02，固定执行类型与共享受限执行器；INTEG-01 保持进行中，后续条件见 EXECUTION 和实施计划。

执行模块初次交付的公共检查 `check_foundation.py`（27 个本地链接）、`check_design_contracts.py` 与 `git diff --check` 均通过。当时未执行产品 ELF 分析、真实归因、SJS 产品 CLI 或 M2 独立评估；后续执行/分析候选对接结果见相应验证记录。
