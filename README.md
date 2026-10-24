# RISC-V OptiLab

面向 RISC-V 的程序编译分析与可验证优化实验平台。两人共同开发的纯软件参赛项目，当前先按此方向建立工程基线；调整方向时记录决策，不把建议当作已取得的成果。

**当前状态：项目约定、接口契约和样例基线已建立；编译引擎、API 和前端尚未实现。仓库没有真实 RISC-V 性能实验结果。**

首版目标：选择内置 C 样例 → 使用固定 RISC-V 目标编译 → QEMU 运行 → 校验预期输出 → 比较代码体积与指令组成 → 展示可追溯报告。

## 朋友从这里接手

1. 阅读 [交接指南](docs/HANDOFF.md)，同步 `main` 到自己的开发分支。
2. 阅读 [范围与约束](docs/PROJECT_SCOPE.md)、[开发规则](CONTRIBUTING.md) 和 [任务板](docs/TASKS.md)。
3. 核心引擎按 [技术基线](docs/BASELINE.md) 开发；前端按 [接口契约](docs/API_CONTRACT.md) 和显式标记的 [mock 数据](contracts/examples/experiment.mock.json) 并行开发。
4. 提交 PR 前运行文档与基线检查，并附上 [验收清单](docs/ACCEPTANCE.md) 中实际完成的证据。

## 文档与资产

| 路径 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | AI 助手必须遵守的项目规则 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 分支、PR、接口变更、验证和协作规则 |
| [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md) | 首版边界、研究方向和不夸大成果的约束 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 模块边界与数据流 |
| [docs/BASELINE.md](docs/BASELINE.md) | 编译、指标、正确性及复现实验口径 |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | 两人并行开发的接口约定 |
| [docs/HANDOFF.md](docs/HANDOFF.md) | 从克隆仓库到领取第一个任务 |
| [docs/TASKS.md](docs/TASKS.md) | 任务依赖、交付物和里程碑 |
| [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) | 验收条件与证据要求 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 技术决策及后续修改记录 |
| [docs/STATUS.md](docs/STATUS.md) | 已实现、未实现与本次检查记录 |
| [config/baseline.json](config/baseline.json) | 机器可读的实验基线 |
| [benchmarks/manifest.json](benchmarks/manifest.json) | 内置程序与固定输入、预期输出 |
| [contracts/experiment.schema.json](contracts/experiment.schema.json) | 实验结果 JSON Schema |

## 当前可执行的检查

仓库根目录，Python 3.10+：

```sh
python -m venv .venv-foundation
# Linux / WSL
.venv-foundation/bin/python -m pip install -r requirements-foundation.txt
.venv-foundation/bin/python scripts/check_foundation.py
# Windows PowerShell 改用 .venv-foundation/Scripts/python.exe
```

这条命令只检查契约、文档链接和样例资产，不代表 RISC-V 编译或项目功能验收。真实工具链安装和手动运行步骤见技术基线。

本机已有 GCC 时，可另行主动执行 `python scripts/check_benchmarks_native.py`，检查三个 C 文件和九个输入输出。它是本机 C 检查，Windows 下仅为此检查归一化输出换行，不替代 Linux 后端严格字节比较或 RISC-V 验收。

## 协作入口

默认分支为 `main`；已有成员分支 `yyd`、`sjs`。可以沿用成员分支，也可以使用短期功能分支，合并前先同步 `main`，具体见开发规则。角色分工是建议，双方可在任务板调整。

赛事入口：[高校赛道](https://rv.cie.org.cn/direction?id=5)。当前工作计划参考 2026-11-08 截止时间，提交要求与具体截止时刻以官方最新通知为准；本仓库尚未完成报名或材料提交。
