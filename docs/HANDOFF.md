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

拟议分工为 yyd 负责核心引擎、sjs 负责前端界面，具体负责人以 `docs/TASKS.md` 的登记结果为准。开发前更新负责人及状态，PR 中标注任务 ID。

- 核心引擎：从 `ENG-01` 开始，按 `docs/BASELINE.md` 配置 Linux / WSL 工具链，实现编译、执行及失败处理。
- 前端界面：从 `UI-01` 开始，依据 Schema、结果 mock 和样例列表 mock 实现方案比较界面。
- 两个模块依据接口契约并行开发。接口变更须先同步公共契约，并完成评审。

## 基础检查环境

基础检查要求 Python 3.10 或更高版本；业务后端目标版本为 Python 3.12。在仓库根目录创建虚拟环境：

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

以上步骤配置并执行公共文件检查。RISC-V 工具链配置见 `docs/BASELINE.md`；后端与前端的安装、启动和测试命令由各模块首个实现 PR 补充。

## UI-01 交付要求

1. 在 `frontend/` 建立 React + TypeScript 工程，提交依赖锁文件及安装、启动和检查命令。
2. 依据 API 契约实现样例选择、三方案比较、错误状态和空结果展示。
3. 使用 `contracts/examples/` 中的 mock 完成初期开发，界面显示“演示数据”标识。
4. 提供显式的 mock / API 模式切换；API 调用失败时展示错误。
5. 涉及公共字段或编译基线调整时，同步 Schema、文档与 mock，并提交评审。
6. 完成相关检查后，更新任务状态并提交 PR。

## 变更提交

提交顺序为：同步 `main`、执行基础与模块检查、审阅 diff、提交改动、推送开发分支、创建面向 `main` 的 PR。PR 按模板填写验证命令与结果；仓库访问权限由所有者管理。
