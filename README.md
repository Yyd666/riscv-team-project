# RISC-V OptiLab

RISC-V OptiLab 是面向 RISC-V 的程序编译分析与优化实验平台，采用纯软件方案，目标功能包括编译配置对比、程序输出校验、目标代码分析与实验报告。

**开发状态：工程约定、接口契约和样例基线已建立；编译引擎、API 和前端待实现。** 验证范围与结果见 [项目状态](docs/STATUS.md)。

首版处理流程：内置 C 样例 → RISC-V 交叉编译 → QEMU 执行 → 输出校验 → 代码体积与指令组成分析 → 实验报告。

## 开发指南

1. 按 [开发环境与协作流程](docs/HANDOFF.md) 配置环境，并将 `main` 合并到开发分支。
2. 阅读 [范围与约束](docs/PROJECT_SCOPE.md)、[开发规则](CONTRIBUTING.md) 和 [任务板](docs/TASKS.md)。
3. 核心引擎遵循 [技术基线](docs/BASELINE.md)；前端依据 [接口契约](docs/API_CONTRACT.md) 和 [mock 数据](contracts/examples/experiment.mock.json) 开发。
4. 提交 PR 前执行基础检查，并按 [验收清单](docs/ACCEPTANCE.md) 提供验证记录。

## 文档索引

| 路径 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | AI 助手必须遵守的项目规则 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 分支、PR、接口变更、验证和协作规则 |
| [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md) | 功能需求、范围限制与研究计划 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 模块边界与数据流 |
| [docs/BASELINE.md](docs/BASELINE.md) | 编译配置、指标定义、校验与复现规则 |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | API 请求、响应与错误处理约定 |
| [docs/HANDOFF.md](docs/HANDOFF.md) | 环境配置、分支同步与开发流程 |
| [docs/TASKS.md](docs/TASKS.md) | 任务依赖、交付物和里程碑 |
| [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) | 验收条件与证据要求 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 技术决策及后续修改记录 |
| [docs/STATUS.md](docs/STATUS.md) | 实现进度与验证记录 |
| [config/baseline.json](config/baseline.json) | 机器可读的实验基线 |
| [benchmarks/manifest.json](benchmarks/manifest.json) | 内置程序与固定输入、预期输出 |
| [contracts/experiment.schema.json](contracts/experiment.schema.json) | 实验结果 JSON Schema |

## 基础检查

在仓库根目录使用 Python 3.10 或更高版本执行：

```sh
python -m venv .venv-foundation
```

Linux / WSL：

```sh
.venv-foundation/bin/python -m pip install -r requirements-foundation.txt
.venv-foundation/bin/python scripts/check_foundation.py
```

Windows PowerShell：

```powershell
.\.venv-foundation\Scripts\python.exe -m pip install -r requirements-foundation.txt
.\.venv-foundation\Scripts\python.exe scripts/check_foundation.py
```

基础检查覆盖 JSON 契约、文档链接和样例数据。RISC-V 工具链配置与手动执行步骤见技术基线。

已安装宿主 GCC 的环境可执行 `python scripts/check_benchmarks_native.py`，验证三个 C 样例及九组输入输出。该检查在 Windows 下归一化输出换行；Linux 后端仍按原始字节比较结果。RISC-V 编译与 QEMU 执行单独验收。

## 协作方式

默认分支为 `main`，成员分支为 `yyd`、`sjs`。开发使用成员分支或短期功能分支，提交 PR 前同步 `main`。任务负责人及进度统一维护在任务板中。

赛事入口：[高校赛道](https://rv.cie.org.cn/direction?id=5)。项目计划以 2026-11-08 为截止日期参考；材料要求及具体截止时刻以官方通知为准。报名与材料提交状态由参赛团队维护。
