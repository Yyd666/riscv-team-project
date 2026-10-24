# 项目状态与验证记录

更新日期：2026-10-24，Asia/Shanghai。

## 已完成内容

- 项目范围、开发规范、架构、环境配置、任务板与验收文档。
- RV64GC / LP64D 配置基线，O0/O2/Os 对照和正确性优先规则。
- 3 个 C 样例、9 组固定输入与独立预期输出。
- API 契约、请求及结果 JSON Schema、带演示标识的 mock 数据。
- 基础检查脚本、GitHub Actions 工作流、Issue/PR 模板与忽略规则。

## 待完成内容

- 业务后端、API 服务、前端及自动实验流程待实现。
- RISC-V 交叉编译、QEMU 执行及性能实验待开展。
- 业务依赖与环境待锁定，首版功能待验收。
- 任务负责人、内部排期及代码许可证待确认。

仓库访问权限与分支保护由所有者管理；赛事报名与材料提交状态由参赛团队维护。

## 本地验证记录（2026-10-24）

验证环境：Windows PowerShell、Python 3.10、独立虚拟环境 `.venv-foundation`。验证范围为公共文件及宿主 C 样例。

以下记录对应初始基线提交 `74789e0`。

| 检查 | 结果 | 范围 |
| --- | --- | --- |
| `python scripts/check_foundation.py` | 通过，退出码 0 | 3 个程序登记、9 组独立数学预期值、3 份结果 mock、请求/结果 Schema 及反例、22 个本地链接 |
| `python scripts/check_benchmarks_native.py` | 未通过 | MinGW GCC 8.1 在首个样例编译时退出 1；`-v` 日志显示调用 cc1 后结束，无 C 诊断输出。宿主编译器问题待处理 |
| `git diff --check`、`git diff --cached --check` | 通过，退出码 0 | 工作区及全部待提交文件的空白检查 |
| RISC-V / QEMU / 业务验收 | 未执行 | 待对应模块实现后开展 |

宿主 C 检查在 Windows 下归一化输出换行；Linux 后端按原始字节比较结果。CI 在 Ubuntu 24.04 执行公共文件检查及宿主 GCC 样例检查，执行结果以对应工作流记录为准。

## 远程验证记录（2026-10-24）

[GitHub Actions #40077900985](https://github.com/Yyd666/riscv-team-project/actions/runs/40077900985)，对应提交 `74789e0c7918d73a9d254c8a447acd6c18c64790`，结论 **success**。

- Ubuntu 24.04、Python 3.12 下基础检查通过：3 个程序、9 个独立预期值、3 份实验 mock、Schema 约束反例和 22 个本地链接。
- 宿主 GCC 13.3.0：三个样例均以 `-O2 -Wall -Wextra -Werror` 编译成功，九次用例执行全部符合预期。
- 验证范围为 Linux 宿主 C 与公共配置、契约和样例文件。RISC-V 交叉编译、QEMU 执行及业务验收尚未开展；Windows MinGW 问题单独跟踪。

## 文档维护记录

- 2026-10-24：统一 README、开发指南、范围、基线、架构、接口、任务及验证文档的工程表述；补充文档规范。代码、接口字段、编译配置与样例数据保持原版本。
- 审校后基础检查通过：3 个程序、9 组预期值、3 份实验 mock、Schema 约束检查及 23 个本地链接；空白检查通过。
