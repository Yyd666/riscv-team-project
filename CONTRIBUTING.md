# 开发与协作规范

## 分支与提交

`main` 保存共同可用的文档、契约及已验证实现。日常开发在已有 `yyd`、`sjs` 成员分支或短期功能分支进行；AI 新建分支默认 `codex/任务名`。

开始任务前执行 `git fetch origin`，确认工作区无未提交改动后切换至开发分支，再执行 `git merge origin/main`。合并冲突在本地解决；存在未提交改动时不得执行覆盖工作区的 reset。PR 使用普通 merge 或 squash；长期成员分支优先使用普通 merge，保留合并关系。禁止 force push。

每次提交对应一个明确任务。提交信息使用 `docs:`、`feat:`、`fix:`、`test:`、`chore:` 等前缀。暂存文件应逐项核对，提交内容仅包含与任务相关的改动。

功能变更通过 PR 合并，由另一位成员审阅。仓库初始化及公共文档维护在获得明确授权后可直接提交至 `main`。分支保护和必需检查的启用状态由仓库设置管理。

## 任务与文件边界

- yyd：`backend/app/execution/`、`backend/app/execution_types.py` 及对应检查，负责受限子进程执行、编译、QEMU、用例校验和原始执行记录包。
- sjs：`backend/app/analysis/`、`backend/app/attribution/`、`backend/app/selection/`、`backend/app/reporting/`、`backend/app/pipeline.py`、CLI 入口及对应检查，负责分析、归因、推荐、编排和报告。评估程序、语料初稿及可选 API/前端也由 sjs 主责。
- 公共区域：`config/`、`contracts/`、`benchmarks/`、`evaluation/`、`docs/`、CI。改动前在任务或 PR 中说明影响。
- execution 模块、执行类型和对应检查已建立，其他目录及 `optipilot` 入口待实现；sjs 的 CLI-01 首个 PR 负责产品 Python 包布局、依赖锁定和入口配置。执行模块不依赖该入口，内部输入边界见 `docs/EXECUTION.md` 与 `docs/ARCHITECTURE.md`。
- 必需交付预计工作量为 sjs 60%、yyd 40%，权重及独立开发依据以 `docs/TASKS.md` 为准。公共基础、可选增强不计入该比例；金标准和集成复核仍由双方完成。
- 开发前登记任务负责人；涉及相同模块的并行修改应事先协调。

## 接口及基线变更

新增兼容字段时，同步更新 Schema、mock、文档及契约检查。删除或重命名字段，以及改变字段类型或含义时，需在 PR 中确认迁移方案并提升接口版本。

编译选项、样例、输入、指标定义或测量规则变更时，应在 `docs/DECISIONS.md` 中记录原因，提升 `baseline_version` 或语料版本，并保留历史结果对应的版本信息。不同版本的结果应明确标注差异及可比范围。

## PR 内容要求

PR 应使用仓库模板，说明变更目的、实现内容、验证方法及未验证项。功能变更附复现命令或界面截图；性能相关变更附正确性结果、工具版本、原始记录及比较方法。

文档/契约 PR：

```sh
python scripts/check_foundation.py
python scripts/check_design_contracts.py
git diff --check
```

基础检查依赖通过 `requirements-foundation.txt` 安装。业务代码的 lint、测试及构建命令由对应模块的首个实现 PR 添加，验证记录应分别列明基础检查与业务检查结果。

## 文档规范

项目文档采用客观、简洁的工程表述，按用途组织为功能需求、技术约束、操作步骤、接口定义或验证记录。标题应概括内容，避免称呼性标题、聊天回顾、提示词及主观评价。

规划功能、已实现功能与已验证结果应分别说明。操作文档明确前置条件、执行命令及预期结果；状态文档记录环境、日期、结果和证据位置。相同概念使用一致术语，重复说明通过文档引用维护。

## 依赖与许可

后端以 Python 3.12 + FastAPI、前端以 Node.js 22 + React + TypeScript + Vite 为开发目标。具体依赖版本由首个实现 PR 锁定并提交 lock 文件。基础检查兼容 Python 3.10+；成员环境配置情况单独记录。

新增依赖应说明用途与替代方案，首版依赖范围遵循项目范围文档。第三方代码须注明来源与许可证，并保留必要声明。项目代码许可证待作者确认。
