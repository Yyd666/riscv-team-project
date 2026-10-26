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
| M0 | 3 个登记程序的 CLI、报告、原始执行记录与独立 GNU 指标核对已通过；持续集成结果以本次 PR 的实际检查为准 |
| M1 | 已补齐直接 ELF 校验、执行/分析时哈希绑定；6 个正例比较及 6 类真实负例逐类状态通过，本次负例 PR 的 CI 和审阅待完成 |
| M2 | 清单 under_review：同来源跨集合、类型/输入变体及家族归类需修订；正式冻结、双人标注、最终评估、录屏与材料待完成 |
| 可选 | FastAPI、前端及联调 |

2026-10-26 证据审计修正：此前记录的“12 程序独立评估完成”和 1.0 指标只来自生产者输出及内部恒等式，未独立核验 ELF，不能证明 M2 已完成。原始运行文件保留作诊断数据；原评估报告实际路径为 WSL2 `/home/yyd/work/optipilot-gold/artifacts/evaluation-report.md`，不作为最终验收报告。旧自定义评估运行器还缺少真实版本清单、输入快照和与执行时 ELF 的绑定，须修复后重跑。

本次真实 CLI 检查位于 WSL2 `/home/yyd/work/optipilot-audit-evidence/final-check/check-c439068d55154bfc995acc0ebb8c91f7/`：3 程序、9 配置、27 次主要用例运行，6 个比较逐项与新运行的 GNU 参考核对，原始执行记录、报告和产物 SHA-256 清单齐全。另实测 O2-only 和缺 O2 的强制归因退出码均为 4，未注册程序返回 2。该证据属于登记冒烟语料，不替代留出评估。实施顺序与剩余验收条件见 [集成审计计划](INTEGRATION_AUDIT.md)。

2026-10-26 WSL2 真实 CLI 复核：在 Ubuntu-Dev / Python 3.12.3 / GCC riscv64 13.3.0 / binutils 2.42 / QEMU 8.2.2 中，`sum_u32`、`dot_i32`、`threshold_count` 分别执行 O0/O2/Os 和全部 3 个登记用例，共 27 次 CLI 编排运行；所有方案通过，推荐均为 Os。旧脚本报告 6 个比较 complete、各项比率 1.0；该版本只核对内部恒等式，不计为独立字节误差证据。后续独立核验见本节前述审计记录。原始记录位于 WSL2 `/home/yyd/work/optipilot-attr/artifacts/cli-real/`，未纳入 Git；当前数据只覆盖开发集 3 个程序，不构成留出集效果结论。

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

`INTEG-01` 已建立执行证据、结果投影和独立 GNU ELF 参考检查；参考检查通过 6 项定向用例，包括手写 3 指令/8 字节参考 ELF、缺失符号、未知编码、指标及操作数篡改。SJS 分析模块的后续交付与验证见 PR #5 集成验收记录；报告、归因、评估及第二位成员的独立复核记录仍待交付，M0/M1/M2 全流程尚未验收。

## 维护记录

- 保留 OptiPilot 主线、CLI 必需交付和 mock 不替代实测的要求。
- 整合编码归因、整体/函数范围分离、独立评估与证据约定，修正报告生成器与最终报告的依赖。
- 2026-10-24：按 sjs 60%、yyd 40% 重新分配必需任务；分析、归因、CLI 及评估由 sjs 主责，编译执行和集成复核由 yyd 主责。新增 ADR-013 和并行模块边界，不改变编译基线、Schema 或业务实现状态。

- 2026-10-25：实现 ENV-01、ENG-01、ENG-02，固定执行类型与共享受限执行器；INTEG-01 保持进行中，后续条件见 EXECUTION 和实施计划。

本次公共检查 `check_foundation.py`（27 个本地链接）、`check_design_contracts.py` 与 `git diff --check` 均通过。未执行独立 ELF 指标分析、真实归因、SJS 产品 CLI 或 M2 独立评估。


- 2026-10-26：修复真实 RV64GC 版本化 ISA 解析，拒绝 `.2byte`/`.short` 等伪指令编码；CI 增加真实 ELF 分析和拒判测试，ENG-03 待 yyd 复审。

## PR #5 集成验收

针对已合并的 ENG-03 提交 `d779581b40915000cf8f5311a3c480a1914170bc`，执行/分析边界检查已完成：3 个程序、3 个档位共 27 次 QEMU 校验，9 份 ELF 的静态指标与独立 GNU 参考一致；7 类真实 ELF 负例全部返回 `analysis_error`，不输出指标。候选源码、实际命令、原始输出和产物哈希均已归档。

PR #5 的独立 Ubuntu CI（[运行记录](https://github.com/Yyd666/riscv-team-project/actions/runs/40265388704)）通过 40 项检查、54 次执行回归及上述 27 次集成运行。下载归档后核对 568 份产物哈希、消费方实现和候选源码的 Git 哈希，并验证三份迁移后的执行记录，均通过。该集成检查覆盖执行/分析边界，不等同于 M0/M1/M2 全流程验收；推荐、CLI、报告、归因、独立评估及第二位成员复核仍待交付。

PR #5 已合并 main，合并提交为 `b603efe`。后续修正统一基础设施异常退出码为 5，并区分自动跟踪 sjs 头提交与使用完整 SHA 的最终验收；PR 自动检查的集成证据也纳入 CI artifact 上传。具体检查结果以对应后续提交和 CI 记录为准。

2026-10-26：本地 WSL2 通过 48 项检查，其中新增 CLI 子进程检查覆盖 SyntaxError、TypeError、RuntimeError、OSError 和 ValueError：均返回 5，保留 infrastructure_error 摘要、原始字节及其哈希。基础与设计契约检查、`git diff --check` 均通过。远程验证以本次后续 PR 的实际 CI 为准。

后续修正提交 `f5d4767` 的 [PR #7 CI](https://github.com/Yyd666/riscv-team-project/actions/runs/40292633330) 已通过 48 项检查、54 次执行回归与 27 次候选集成运行、7 类负例，并成功上传自动集成证据。下载后核对全部 568 份产物哈希及实现/候选源码哈希，均通过；实际候选为 `28c89beafe7186ff7b8b24c4b067321f6250de2e`。该运行只加载候选分析模块，不验证其选择器包。

## ENG-04 候选复核（2026-10-26）

PR #6 提交 `7b3e3339298b784384502586e1f89198b52e8699` 的选择函数通过 2,374 组独立组合对照；另对既有真实 ELF 指标运行三程序各六种配置排列，推荐均与独立最小体积结果一致。这些检查直接验证选择函数，不代表包入口或产品 CLI 已通过。

候选包未导出 `validate_baseline_policy`，其自带测试在导入时失败。PR 同时与最新 main 冲突，状态文档仍有“已实现推荐器”与“尚无推荐器”并存的问题。ENG-04 保持待修复、待复核，不标为已验收；未修改 sjs 分支。

SJS 随后提交 `28c89beafe7186ff7b8b24c4b067321f6250de2e` 补齐包导出；按该提交的包入口加载并运行 8 项自带测试，全部通过。选择器实现字节与前次复核版本相同，原有组合对照结果仍适用。主线冲突与文档状态仍待处理，完整 CLI 集成仍未验收。

SJS 提交 `d873312` 已同步主线并修正推荐器状态表述，选择器代码与已复核版本一致。PR #6 在全部 CI 通过后合并到 main（`96ee95b`）；其中 55 项检查、54 次执行回归和执行/分析集成均通过。ENG-04 模块已交付，完整 CLI 流程仍待验收。

## CI 工具安装时限

同步提交 `d83b142` 的执行 PR CI 通过 56 项检查、54 次执行回归及执行/分析集成；同一提交的 push 版 Analysis 也通过。PR 版 Analysis 长时间停留在 apt 安装阶段，原工作流未配置作业时限。后续将 Analysis 作业限定为 10 分钟，两个真实工具安装步骤限定为 3 分钟；apt 使用两次下载重试和 30 秒连接超时。安装失败仍使检查失败，不改为跳过测试或使用替代产物。


- 2026-10-26：CLI-01 已在 sjs 实现真实 run 闭环：执行登记样例、ENG-03 静态分析、ENG-04 有限候选推荐、Schema 结果组装、原子保存和退出码；report 命令保留给 REPORT-01，--require-attribution 保留给 ATTR-01。未提供 mock 回退。


- 2026-10-26：修复 CLI-01 入口回归：包初始化文件使用真实换行，CLI 从 backend.app.pipeline 导入；新增 --help、真实 pipeline 调度和工具链缺失退出码测试。编译诊断记录 status/exit_code，分析失败保留 analysis_argv；Windows 缺少 Linux/RISC-V 工具链时按 TOOLCHAIN_UNAVAILABLE 返回 5，不回退 mock。


- 2026-10-26：REPORT-01 已实现只读 JSON 到 Markdown 报告：校验结果结构、显示 mock/真实来源、推荐、方案状态、诊断、分析命令和结论边界；原子写入报告，非法结果返回 2，不重新执行实验。

- 2026-10-26：ATTR-01 已实现 R001/R002 sidecar、原始分析产物证据、实验 JSON/策略哈希关联、partial/unavailable 拒判和 `--require-attribution` 退出码 4；真实 ELF 正负例与独立评估待完成。

## 归因证据修复验证（2026-10-26）

- 直接读取 ELF64 的函数符号、所属节、地址、文件偏移和原始编码；归档符号表、节表及反汇编须与 ELF 一致。
- 真实 sidecar 绑定 execution.json 中的源码、配置、用例和 ELF 哈希，以及分析时的原始工具输出哈希；缺失或冲突时拒判。
- 报告重新验证 sidecar 的策略、证据、快照和变化分量；篡改不能靠保持恒等式逃过核验。O2-only 不再被误判为已完成归因。
- 评估区分内部恒等式误差与独立 GNU 字节误差，拒收 mock/重复实验，并将缺失程序保留在请求分母中；公布固定 O2/Os、穷举差额、失败和零收益原始计数。
- 初稿语料仍有来源隔离缺陷，冻结命令返回 3 并保留原清单；评估命令输出诊断但不通过验收门槛。自动核验不代替双方独立标注。
- WSL2 本地 `python -B -m unittest discover -s backend/tests -v`：82 项全部通过，无跳过；`check_cli_real.py` 的 27 次主要用例、6 个独立归因比较及实际退出码检查通过。公共基础、设计契约与 `git diff --check` 通过。远程 CI 另行核实，不以本地结果代替。

后续负例补齐：`run_attribution_negatives.py` 使用登记程序的明确派生夹具，执行两档全部原始 oracle 输入，逐类验证未知 16/32 位、截断编码、缺失符号、函数在其他节和证据冲突。12 配置、36 次运行均正确；归因 partial/unavailable 及 R001/R002 状态符合预期。摘要和 668 份证据文件哈希保存于 WSL2 `/home/yyd/work/optipilot-audit-evidence/negative-audit-03.json`。负例属于集成夹具，不计为独立评估语料。工具缺失、编译错误或错误输出不再计为有效拒判，另有两项定向门控回归通过。

独立环境复核：下载 [PR #17 Ubuntu CI 的真实 CLI 归档](https://github.com/Yyd666/riscv-team-project/actions/runs/40343631183)，核对 465 份实际上传文件 SHA-256、三份迁移后的原始执行记录与 6 份 sidecar；与本地 WSL 的九份 ELF 逐份比较，SHA-256 均一致。旧归档另列了 10 个空锁/启动标记，这些操作文件被上传工具排除，不计为收到的证据；已修复后续清单，使其不再列入这两类文件。比较记录保存于 WSL2 `/home/yyd/work/optipilot-audit-evidence/ci-local-comparison.json`。该独立环境结果覆盖登记语料，不覆盖 M2 留出集或双方标注。

负例补齐后的 WSL2 回归：`python -B -m unittest discover -s backend/tests -q` 共 84 项全部通过，无跳过；六份真实负例 sidecar 均另行通过结构及当前证据消费校验，公共基础、设计契约和空白检查通过。远程负例 CI 待本次 PR 核验。
