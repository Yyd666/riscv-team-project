# 开发环境与协作流程

本文规定环境配置、分支同步、任务登记与提交流程。项目实现进度及验证记录见 `docs/STATUS.md`。

## 仓库获取与分支同步

首次克隆并建立本地 `sjs` 跟踪分支：

```sh
git clone https://github.com/Yyd666/riscv-team-project.git
cd riscv-team-project
git switch -c sjs --track origin/sjs
git merge origin/main
```

已存在本地 `sjs` 分支时，确认工作区无未提交改动后执行：

```sh
git fetch origin
git switch sjs
git merge origin/main
```

上述命令以 `sjs` 为例，其他开发分支使用对应名称。成员分支通过 `git merge origin/main` 同步公共基线；合并后按正常流程推送，禁止强制推送及覆盖未提交改动。

## 任务登记与模块分工

必需交付按预计工作量分为 yyd 40%、sjs 60%，具体任务、权重、模块责任和验收依赖见 `docs/TASKS.md`，PR 中标注任务 ID。此比例为计划值，不代表实际完成情况。

- 编译执行（yyd）：负责 `ENV-01`、`ENG-01/02`，交付受限执行器、全部用例校验和原始执行记录包；通过 `INTEG-01` 完成接口、集成和金标准交叉复核。
- 分析与编排（sjs）：负责 `ENG-03/04`、`ATTR-01`、`CLI-01`。先用自备真实 ELF、契约样例和隔离测试适配器开发，不等待 yyd 完成整个执行模块；正式入口对接真实执行器后验收。
- 报告与评估（sjs）：负责报告生成器、语料与标注初稿、评估程序、最终报告和演示；独立双人复核由双方完成，实际评估结果须等待真实模块集成。
- 前端界面：按可选任务执行，依据原实验 mock 与新增归因 mock 展示整体推荐、函数诊断、证据与拒判。
- 执行记录包和文件责任边界见 `docs/ARCHITECTURE.md`。首批 PR 固定内部类型和调用签名；接口变更须先同步契约并完成评审。模块 PR 可独立提交，M0/M1/M2 的最终验收依赖仍须满足。

## 基础检查环境

基础检查要求 Python 3.10 或更高版本；业务后端目标版本为 Python 3.12。在仓库根目录创建虚拟环境：

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

以上步骤配置并执行公共文件检查。RISC-V 工具链配置见 `docs/BASELINE.md`；后端与前端的安装、启动和测试命令由各模块首个实现 PR 补充。

归因 mock 可通过 `python scripts/generate_attribution_mocks.py` 重新生成。该命令只构造合成数据，不运行编译器或解析 ELF。修改策略或原实验 mock 后，应显式重新生成并审阅差异，CI 只做校验，不自动重建示例以掩盖漂移。

## UI-01 交付要求

1. 在 `frontend/` 建立 React + TypeScript 工程，提交依赖锁文件及安装、启动和检查命令。
2. 依据 API 契约实现样例选择、三方案比较、错误状态和空结果展示。
3. 使用 `contracts/examples/` 中的 mock 完成初期开发，界面显示“演示数据”标识。
4. 提供显式的 mock / API 模式切换；API 调用失败时展示错误。
5. 涉及公共字段或编译基线调整时，同步 Schema、文档与 mock，并提交评审。
6. 完成相关检查后，更新任务状态并提交 PR。

## 变更提交

提交顺序为：同步 `main`、执行基础与模块检查、审阅 diff、提交改动、推送开发分支、创建面向 `main` 的 PR。PR 按模板填写验证命令与结果；仓库访问权限由所有者管理。
