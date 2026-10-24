# RISC-V OptiPilot

RISC-V OptiPilot 是面向 RV64GC 的正确性约束编译优化与可解释分析平台。平台针对同一份已登记的 C 程序生成多组编译方案，先用 QEMU 验证程序行为，再比较目标代码体积、函数机器码和静态指令组成，输出可复现的优化推荐与差异解释。

参赛初稿目标：在 2026-11-08 前交付一条可运行的实验闭环。初稿聚焦固定可信语料和有限候选配置，后续可扩展到更大的策略搜索、动态指令统计和真实 RISC-V 板卡验证。当前实现状态见 docs/STATUS.md。

## 核心创新点

平台采用“正确性门控 + 有限策略搜索 + 可解释结果”的流程：

1. 从候选编译配置生成 RV64GC / LP64D 静态 ELF；
2. 使用 QEMU 运行全部登记用例，校验 stdout、stderr 和退出码；
3. 淘汰输出错误、编译失败或超时的方案；
4. 对通过方案计算 ELF、.text、目标函数机器码和指令组成指标；
5. 展示体积与执行诊断之间的 Pareto 前沿，并给出可追溯的推荐理由。

推荐结果只来自通过全部正确性检查的方案，报告同时保留失败原因和原始证据。

## 初稿范围

- 3 个内置 C 样例、9 组固定输入和独立预期输出；
- O0、O2、Os 基准组，以及少量安全的候选配置；
- riscv64-linux-gnu-gcc 交叉编译与 qemu-riscv64 执行；
- ELF、节表、符号表和反汇编分析；
- 体积优先和性能诊断两种推荐视图；
- 契约一致的 JSON 结果与 Markdown 实验报告；
- 通过 CLI 或前端完成一条可录制的演示流程。

初稿不接受任意源码上传，不执行 shell 参数，不承诺硬件周期或能耗结论。后端仅运行仓库注册的可信样例，前端不直接调用编译器和 QEMU。

## 数据流

C 样例 → 候选编译配置 → RV64GC ELF → QEMU 正确性校验 → 静态分析 → Pareto/推荐 → 报告

后端模块边界、超时、输出上限和进程清理要求见 docs/ARCHITECTURE.md，编译与指标定义见 docs/BASELINE.md。

## 开发与验证

1. 阅读 docs/PROJECT_SCOPE.md、CONTRIBUTING.md 和 docs/TASKS.md。
2. 按 docs/HANDOFF.md 准备 Linux/WSL2 工具链。
3. 依据 docs/API_CONTRACT.md 和 contracts/examples/experiment.mock.json 开发前后端。
4. 提交前执行基础检查，并按照 docs/ACCEPTANCE.md 保存实验和演示证据。

赛事材料、报名状态和最终截止时刻以官方通知为准：https://rv.cie.org.cn/