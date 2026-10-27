# OptiPilot M2 评估报告（草稿）

状态：机器评估、双人复核和裁决已完成，本文档仍是最终报告草稿，不作为一般程序优化收益声明。

## 评估目标

评估固定 O0/O2/Os 编译流程、QEMU 正确性门控、完整 `.text` 推荐，以及 R001/R002 静态字节归因。归因统计解释静态字节变化，不推断优化 pass 因果、动态指令数、周期、能耗或目标性能。

## 语料与追溯

语料版本 `0.1.0`，机器状态 `frozen`。开发集和留出集各 6 个不同程序家族：

| 划分 | 家族 |
| --- | --- |
| development | sum_reduction、dot_product、threshold_filter、histogram、run_length、rolling_hash |
| held_out | checksum、lookup_and_switch、function_calls、state_machine、fixed_point_filter、bounded_parser |

每个程序登记源码、输入和预期输出的 SHA-256，并保存来源标识。本文引用的历史 0.1.0 批次保留当时的许可待确认字段；2026-10-27 授予的 MIT 及相同资产关联见 [语料来源与许可](CORPUS_LICENSE.md)，当前清单版本为 0.1.1。原始批次、清单和数据不改写。批次使用提交后干净实现，保存 Git 提交、实现源码哈希、工具版本、源码/输入快照、原始编译/QEMU 输出、ELF、分析输出和归因 sidecar。

## 环境与命令

正式批次在 WSL2 Ubuntu-Dev 执行，工具为 GCC riscv64 13.3、GNU binutils 2.42、QEMU 8.2；完整原始批次位于：

```text
/home/yyd/work/optipilot-m2-formal-final/evaluation-23d0fbc17db84a1d8379bbc0ca0d2ddf/
```

## 机器核验结果

| 指标 | 结果 |
| --- | ---: |
| 程序数 | 12 |
| 配置数 | 36 |
| QEMU 用例数 | 108 |
| O2→候选比较对 | 24 |
| 独立字节误差为零 | 24/24 |
| R001 独立验证率 | 1.0 |
| R002 独立覆盖率 | 1.0 |
| 配置通过率 | 1.0 |
| 用例通过率 | 1.0 |
| 固定推荐相对三档穷举差额 | 0 bytes |
| 相对 O2 零收益程序数 | 0 |
| 相对 Os 零收益程序数 | 12 |
| 编译失败数 | 0 |
| 用例失败/超时数 | 0 |

原始批次生成时，双人标注与裁决尚未完成；后续 PR #26、#28 完成标注，签字补充 PR #30 先合并到 sjs，PR #29 随后将裁决合并到 main。历史批次仍保留 `automated_checks_passed=true`、`formal_ineligible_programs=[]`、`acceptance_ready=false`；MIT 后续授予不重写这些历史标志，也不代替最终报告、录屏和官方材料验收。

## 独立环境复现

[Ubuntu 正式复现](https://github.com/Yyd666/riscv-team-project/actions/runs/40464387344) 完成同一语料的 12 程序、36 配置、108 用例及 24 个比较。下载后核对 1,419 份上传文件，并在 WSL2 重新核验 12 份执行记录；36 份 ELF SHA-256 和 GNU 静态指标均与本地原正式批次相同，源码/输入、推荐和评估汇总一致。

宿主内核和 Python 版本不同，编译器、binutils、QEMU 及跨架构 libc 版本相同。原始清单分别使用 CRLF 和 LF，因此文件哈希不同；JSON 内容及 LF 归一化字节一致，两份原始清单及哈希分别保留。完整版本、哈希与比较记录见 STATUS。软件包尚未锁定，不据此保证未来环境二进制一致；该机器复现也不替代双方独立标注。

## 解释边界

- R001 是静态字节统计恒等式；独立 GNU ELF 重新核对的误差为零，但这不证明优化 pass 的因果作用。
- R002 只分离 `kernel` 与 `.text` 其他字节；函数外变化不进一步归因到具体库、填充或编译步骤。
- 当前语料不能支持对一般 C 程序的普遍优化收益结论。
- 动态指令、目标周期、功耗和硬件性能没有测量协议，保持缺失。

## 最终验收缺口

双人复核包已完成：reviewer-a.json、reviewer-b.json 和 adjudication.json 均已合并，并使用原批次内部清单完成验证。命令核对了独立性声明、12×3 覆盖、ELF 哈希、GNU 指标和逐项裁决理由，但不验证实际人员身份。当前剩余工作是补齐正式证据索引、最终报告结论限制、录屏和参赛材料；在这些完成前不将 acceptance_ready 写为 true。
