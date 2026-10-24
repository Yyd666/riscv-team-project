# RISC-V OptiPilot

RISC-V OptiPilot 是面向 RV64GC 的正确性校验、目标代码分析与有限编译配置推荐工具。平台针对同一份已登记的 C 程序比较 O0、O2、Os 三种 GCC 优化档位，先用 QEMU 验证程序行为，再比较目标代码体积、函数机器码和静态指令组成，输出可复现的配置推荐与差异解释。

参赛初稿目标：在 2026-11-08 前交付一条可运行的 CLI 实验闭环。当前初稿只使用 O0/O2/Os 基线；新增候选参数须等编译引擎实现后，通过新的决策记录和版本变更加入。

## 当前创新点

项目的创新点是“正确性门控、可解释分析和可复现推荐流程”：

1. 三种配置都必须通过全部登记用例后才参与推荐；
2. 按函数级反汇编和静态指标解释配置差异；
3. 保存源码、输入、配置、工具版本和输出哈希，使结果可复核。

当前项目不宣称自研编译优化算法。有限候选配置推荐基于现有 GCC 优化档位，后续策略搜索需要独立评估和新的版本决策。

## 初稿范围

- 3 个内置 C 样例、9 组固定输入和独立预期输出；
- O0、O2、Os 三种基准配置；
- riscv64-linux-gnu-gcc 交叉编译与 qemu-riscv64 执行；
- ELF、节表、符号表和反汇编分析；
- 按 .text 静态代码体积优先的配置推荐；
- 契约一致的 JSON 结果与 Markdown 实验报告；
- CLI 演示一条完整实验流程。

wall_time_ms 只用于超时和执行异常诊断，不作为性能排名依据。静态指令数量不等于动态执行数量，.text 大小包含静态链接影响，QEMU 宿主时间不等于目标 RISC-V 处理器性能。

所有实验结论只适用于登记语料和明确的工具链环境，不外推到一般 C 程序。

## 数据流

C 样例 → O0/O2/Os 编译 → RV64GC ELF → QEMU 正确性校验 → 静态分析 → 配置推荐 → 报告

后端模块边界、超时、输出上限和进程清理要求见 docs/ARCHITECTURE.md，编译与指标定义见 docs/BASELINE.md。

## 开发与验证

开发环境要求 Linux/WSL2，并需要 riscv64-linux-gnu-gcc、binutils 和 qemu-riscv64。Windows 本机 MinGW 检查不能替代 RISC-V 验证。

1. 阅读 docs/PROJECT_SCOPE.md、CONTRIBUTING.md 和 docs/TASKS.md。
2. 按 docs/HANDOFF.md 准备并记录工具链版本。
3. 依据 docs/API_CONTRACT.md 和 contracts/examples/experiment.mock.json 开发后端与演示界面。
4. 提交前执行基础检查，并按照 docs/ACCEPTANCE.md 保存实验和演示证据。