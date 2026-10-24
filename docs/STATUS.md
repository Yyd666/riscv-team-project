# 当前状态与检查记录

更新日期：2026-10-24，Asia/Shanghai。

## 已建立

- 项目范围、AI 与团队规则、架构、交接、任务板和验收文档。
- RV64GC / LP64D 配置基线，O0/O2/Os 对照和正确性优先规则。
- 3 个 C 样例、9 组固定输入与独立预期输出。
- API 文字契约、实验结果 JSON Schema、显式 mock。
- 基础检查脚本、GitHub Actions 工作流、Issue/PR 模板与忽略规则。

## 尚未实现或确认

- 没有业务后端、API 服务、前端或自动实验管线。
- 没有真实 RISC-V 编译、QEMU 运行、性能测量或优化收益。
- 没有锁定双方业务环境，没有完成首版功能验收。
- 没有邀请协作者、设置分支保护、选择代码许可证、完成比赛报名或材料提交。
- 角色与内部时间安排为建议，成员尚需认领任务。

## 本次本地验证

参考环境：Windows PowerShell、Python 3.10，独立 `.venv-foundation`；没有配置或执行 RISC-V 工具链。

| 检查 | 结果 | 范围 |
| --- | --- | --- |
| `python scripts/check_foundation.py` | 通过，退出码 0 | 3 个程序登记、9 组独立数学预期值、3 份结果 mock、请求/结果 Schema 及反例、22 个本地链接 |
| `python scripts/check_benchmarks_native.py` | 本机未通过 | 已有 MinGW GCC 8.1 在首个样例编译时退出 1；定向 `-v` 检查显示调用 cc1 后结束，无 C 诊断输出。本次未修复/替换宿主编译器 |
| `git diff --check`、`git diff --cached --check` | 通过，退出码 0 | 工作区及全部待提交文件的空白检查 |
| RISC-V / QEMU / 业务验收 | 未执行 | 不属于本次工程约定交付 |

原生 C 检查是可选的语料验证，Windows 换行仅在该检查中归一化；不改变 Linux 后端的严格字节比较要求。CI 已配置在 Ubuntu 24.04 执行基础检查及宿主 GCC 样例检查，实际远程结果以 GitHub Actions 为准；提交工作流文件不等于已经运行成功。
