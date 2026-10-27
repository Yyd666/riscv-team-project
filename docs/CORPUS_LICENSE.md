# 评估语料来源与许可

## 许可范围

自 2026-10-27 起，以下 12 个仓库自编评估程序的源文件及其登记输入、预期输出采用 [MIT 许可证](../evaluation/LICENSE)，SPDX 标识为 `MIT`。版权声明为 `Copyright (c) 2026 RISC-V OptiPilot contributors`。登记输入与预期输出的具体文件、原始字节哈希以 [评估清单](../evaluation/corpus.json) 的 `cases` 为准，共 36 组输入及 36 份预期输出。复制或分发这些源文件和数据时，应一并保留许可文件及版权声明。

| 程序 | 源文件 | 首次引入提交 |
| --- | --- | --- |
| sum_u32 | `benchmarks/sum_u32/main.c` | `74789e0c7918d73a9d254c8a447acd6c18c64790` |
| dot_i32 | `benchmarks/dot_i32/main.c` | `74789e0c7918d73a9d254c8a447acd6c18c64790` |
| threshold_count | `benchmarks/threshold_count/main.c` | `74789e0c7918d73a9d254c8a447acd6c18c64790` |
| histogram_count | `evaluation/programs/histogram_count/main.c` | `e0ae4bca578a7eedca358f2120f3a66ffaf4d8d8` |
| run_length | `evaluation/programs/run_length/main.c` | `e0ae4bca578a7eedca358f2120f3a66ffaf4d8d8` |
| rolling_hash | `evaluation/programs/rolling_hash/main.c` | `e0ae4bca578a7eedca358f2120f3a66ffaf4d8d8` |
| xor_checksum | `evaluation/programs/xor_checksum/main.c` | `8cda6c35d9c74be1774f9bbb09aed8f417c51240` |
| lookup_switch | `evaluation/programs/lookup_switch/main.c` | `8cda6c35d9c74be1774f9bbb09aed8f417c51240` |
| call_chain | `evaluation/programs/call_chain/main.c` | `8cda6c35d9c74be1774f9bbb09aed8f417c51240` |
| state_machine | `evaluation/programs/state_machine/main.c` | `8cda6c35d9c74be1774f9bbb09aed8f417c51240` |
| fixed_point_filter | `evaluation/programs/fixed_point_filter/main.c` | `8cda6c35d9c74be1774f9bbb09aed8f417c51240` |
| bounded_parser | `evaluation/programs/bounded_parser/main.c` | `8cda6c35d9c74be1774f9bbb09aed8f417c51240` |

上述文件的首次引入提交均记录 Git 作者账号 `Yyd666`。该记录用于追溯仓库内来源，不扩展为已核验自然人身份或双人独立标注的声明。现有 `repository_authored_development` / `repository_authored_held_out` 来源标识及程序家族划分保持不变。

本许可范围限定为表中源文件和登记数据，不对仓库其他源代码、工具链、系统库或第三方内容另行授予许可。ELF 和证据包中包含的第三方组成部分保留其原有版权与许可，不能将整个静态链接 ELF 或工具安装包标注为仅采用 MIT。

## 元数据与历史证据

语料版本由 `0.1.0` 更新为 `0.1.1`，变更仅涉及许可元数据、许可文件哈希和清单的 LF 序列化。12 个源文件、36 组输入及预期输出的字节、哈希、程序家族、开发/留出划分和 oracle 定义不变。当前清单的 `license_file` / `license_sha256` 绑定许可原文；运行器在执行前核对并将原文保存到登记快照的 `LICENSE`，实现快照同时保存许可及本文。

原正式批次 `evaluation-23d0fbc17db84a1d8379bbc0ca0d2ddf` 及已发布的 Ubuntu 复现批次保留各自原始 `0.1.0` 清单、历史许可待确认标记及哈希，不补写历史状态。此次 MIT 授予适用于与当前登记资产字节和哈希一致的历史副本；附加此许可说明即可记录后续授予，不应改写原始归档。

两位成员继续对同一原始 ELF 批次独立标注，验证时 `--corpus` 指向被标注批次内部的原始 `corpus.json`，而非当前 `0.1.1` 清单。新版本运行产生新批次 ID；不得将新旧批次的标注、ELF 或清单哈希混用。许可落地不代替双人标注、数值范围/oracle 复核、分歧裁决或最终材料验收。

许可名称及标准文本参考 [Open Source Initiative 的 MIT License](https://opensource.org/license/mit)。
