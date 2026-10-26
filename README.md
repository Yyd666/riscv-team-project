# RISC-V OptiPilot

面向 RV64GC 的程序校验、代码体积分析与有限编译配置推荐工具。项目的核心开发目标是函数级代码体积变化归因，区分指令数量、16/32 位编码组成以及函数外代码对整体体积变化的影响。

**开发状态：编译执行、静态 ELF 分析和有限候选选择模块已合并；执行模块完成两轮共 54 次真实 QEMU 校验，执行/分析边界检查覆盖 27 次运行及 7 类负例。归因、报告生成器及 Web 界面待实现；CLI-01 已实现但仍需 yyd 完成真实端到端复核，尚无真实归因评估或优化收益结论。** 详细记录见 [项目状态](docs/STATUS.md)。

## 技术目标

- 使用 O0/O2/Os 编译固定语料，通过 QEMU 校验全部登记输入。
- 从通过用例的配置中按完整 `.text` 最小推荐，平局规则沿用基线。
- 对 O2 与其他通过配置的 `kernel` 函数字节变化进行可核对的编码分解。
- 分离 `.text` 中函数内外的体积变化，明确推荐目标与解释范围。
- 为每条解释关联原始产物与证据位置；证据不足时输出部分结果或拒判。

固定三档推荐属于基础能力，自研贡献拟集中在 RV64GC 编码归因与证据关联。有效性须使用独立评估集验证；当前不宣称自研编译优化算法或已取得性能收益。

## 交付分层

| 层次 | 交付内容 | 条件 |
| --- | --- | --- |
| 基础流程 | 真实交叉编译、QEMU 校验、静态指标、CLI、JSON/Markdown 报告 | 必需 |
| 核心分析 | R001 编码分解、R002 函数内外分离、证据引用与拒判 | 核心模块验收必需 |
| 独立评估 | 程序家族隔离、人工复核、原始计数、失败和无收益结果 | 技术效果结论必需 |
| 交互增强 | FastAPI、前端与对照视图 | 可选 |

初始 3 个程序、9 组输入用于流程检查。扩展开发集和独立评估集尚待建立，目标和划分规则见评估协议。宿主耗时仅作诊断，动态指令数、目标周期和能耗需另设测量方案。

## 文档索引

| 文档 | 用途 |
| --- | --- |
| [开发规范](CONTRIBUTING.md) | 分支、PR、验证与文档规范 |
| [AI 协作规范](AGENTS.md) | 开发助手执行约束 |
| [项目范围](docs/PROJECT_SCOPE.md) | 需求、阶段与结论边界 |
| [归因设计](docs/ATTRIBUTION_DESIGN.md) | 数学定义、证据和拒判规则 |
| [评估协议](docs/EVALUATION.md) | 对照、数据隔离、指标与复现 |
| [技术基线](docs/BASELINE.md) | RV64GC/LP64D 编译与运行规则 |
| [架构](docs/ARCHITECTURE.md) | 模块及数据流 |
| [执行模块](docs/EXECUTION.md) | 已实现接口、运行检查及集成边界 |
| [执行任务计划](docs/YYD_EXECUTION_PLAN.md) | yyd 实施阶段及完成证据 |
| [接口与 CLI 契约](docs/API_CONTRACT.md) | 命令、结果与可选 API |
| [开发流程](docs/HANDOFF.md) | 环境、分支及任务登记 |
| [任务板](docs/TASKS.md) | 依赖、责任模块与交付物 |
| [验收清单](docs/ACCEPTANCE.md) | 分层验收条件 |
| [决策记录](docs/DECISIONS.md) | 稳定编号的 ADR |
| [样例说明](benchmarks/README.md) | 已登记语料及输入定义 |

## 基础检查

使用 Python 3.10+ 在仓库根目录创建环境：

```sh
python -m venv .venv-foundation
```

Linux / WSL：

```sh
.venv-foundation/bin/python -m pip install -r requirements-foundation.txt
.venv-foundation/bin/python scripts/check_foundation.py
.venv-foundation/bin/python scripts/check_design_contracts.py
```

Windows PowerShell：

```powershell
.\.venv-foundation\Scripts\python.exe -m pip install -r requirements-foundation.txt
.\.venv-foundation\Scripts\python.exe scripts/check_foundation.py
.\.venv-foundation\Scripts\python.exe scripts/check_design_contracts.py
```

检查覆盖配置、Schema、合成示例的算术与引用一致性，以及文档链接。真实执行模块的运行命令和范围见执行模块说明；ELF 分析、归因与全流程验收另行记录。已有宿主 GCC 时，可使用 `python scripts/check_benchmarks_native.py` 检查 C 样例；其 Windows 换行适配不影响 Linux 后端的严格字节比较。

默认分支为 `main`，成员分支为 `yyd`、`sjs`。开发前同步主线，变更通过 PR 合并。赛事入口：[高校赛道](https://rv.cie.org.cn/direction?id=5)，材料与提交要求以官方通知为准。
