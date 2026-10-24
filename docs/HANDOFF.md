# 给另一位开发者的交接

先看 `docs/STATUS.md`，这里不会假装已经有后端或页面。当前能直接使用的是规则、契约、样例输入输出和文档检查。

## 同步共同基线

尚未克隆：

```sh
git clone https://github.com/Yyd666/riscv-team-project.git
cd riscv-team-project
git switch -c sjs --track origin/sjs
git merge origin/main
```

已有本地 `sjs` 分支且没有未提交工作：

```sh
git fetch origin
git switch sjs
git merge origin/main
```

如果你使用其他分支名，替换为自己的分支；不要直接覆盖已有文件。合并后将自己的分支正常 push，不用 force。`main` 不会自动同步到成员分支，需要主动 merge。

## 领取第一个任务

建议 yyd 负责引擎、sjs 负责界面；这是可调整分工，未代表双方已确认。先在 `docs/TASKS.md` 标明认领人和状态，PR 中写任务 ID。

- 引擎路线：领取 `ENG-01`，按 `docs/BASELINE.md` 主动准备 Linux / WSL 工具链，然后做最小编译运行与失败处理。
- 界面路线：领取 `UI-01`，从已有 Schema、结果 mock 和样例列表 mock 开始，先做可读的比较界面。
- 不依赖对方已完成服务即可开工。改变接口之前先更新公共契约并沟通。

## 本地检查公共资产

Python 3.10+ 可执行基础检查，业务后端目标仍是 3.12：

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

这不是业务启动命令，也不会自动安装 RISC-V 工具链。首个后端/前端实现 PR 应各自补充真实的安装、启动和测试命令；当前没有 `npm run dev` 或 `uvicorn` 可以直接启动的应用。

## 可直接复制给开发助手的任务说明

> 请先阅读 AGENTS.md、docs/STATUS.md 和 docs/TASKS.md。我负责 UI-01：在 frontend/ 实现 React + TypeScript 界面，按现有 API 契约与 contracts/examples/ 的 mock 开发，必须显示演示数据标记，并保留显式真实 API 模式。先固定依赖与 lock 文件，完成样例选择、三方案比较、错误/空结果展示。不要修改编译基线或后端字段来迁就界面；若确需变更，先同步 Schema、文档及 mock。完成后运行与改动相称的检查，更新状态并提交 PR。

## 提交 PR

同步 `main` → 运行基础检查及本模块检查 → 查看 diff → 提交 → 推送自己分支 → 向 `main` 发 PR。使用 PR 模板，附命令和真实结果。没有 GitHub 权限时向仓库所有者申请协作者权限；本次文档不会自动邀请账户或修改权限。
