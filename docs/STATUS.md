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
| M0 | 执行模块已实测；ENG-03 静态 ELF 分析已实现并待复核；仍需推荐、产品 CLI、报告生成器与全流程集成 |
| M1 | 原始 ELF 归因引擎、证据解析与实际正负例验证 |
| M2 | 扩展语料、独立留出集、双人标注、实测评价与最终报告 |
| 可选 | FastAPI、前端及联调 |

当前业务后端已实现 execution、执行类型和 ENG-03 静态分析入口；尚无推荐器、产品 CLI、归因引擎或已取得的优化收益。评估计划中的程序数量为建设目标，合成 JSON 不计为真实编译或算法测试结果。

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

`INTEG-01` 已建立执行证据、结果投影和独立 GNU ELF 参考检查；新增参考检查已通过 6 项定向用例，包括手写 3 指令/8 字节参考 ELF、缺失符号、未知编码、指标及操作数篡改。SJS 的分析、CLI、报告、归因及评估模块和第二位成员的独立复核记录均未交付，M0/M1/M2 全流程尚未验收。执行模块验收不构成 M0/M1/M2 全流程验收。

## 维护记录

- 保留 OptiPilot 主线、CLI 必需交付和 mock 不替代实测的要求。
- 整合编码归因、整体/函数范围分离、独立评估与证据约定，修正报告生成器与最终报告的依赖。
- 2026-10-24：按 sjs 60%、yyd 40% 重新分配必需任务；分析、归因、CLI 及评估由 sjs 主责，编译执行和集成复核由 yyd 主责。新增 ADR-013 和并行模块边界，不改变编译基线、Schema 或业务实现状态。

- 2026-10-25：实现 ENV-01、ENG-01、ENG-02，固定执行类型与共享受限执行器；INTEG-01 保持进行中，后续条件见 EXECUTION 和实施计划。

本次公共检查 `check_foundation.py`（27 个本地链接）、`check_design_contracts.py` 与 `git diff --check` 均通过。未执行独立 ELF 指标分析、真实归因、SJS 产品 CLI 或 M2 独立评估。


- 2026-10-26：修复真实 RV64GC 版本化 ISA 解析，拒绝 `.2byte`/`.short` 等伪指令编码；CI 增加真实 ELF 分析和拒判测试，ENG-03 待 yyd 复审。
