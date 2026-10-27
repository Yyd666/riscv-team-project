# M2 双人独立复核包

该文件是人工复核工作表，不是自动测试结果。两位成员必须分别读取同一批次的原始 ELF、GNU 输出和 sidecar，在不查看对方标注的情况下填写自己的结论。许可证字段仍需作者确认。

## 复核规则

1. 复核人 A 和 B 分别记录姓名/账号、日期、Git 提交、批次目录和工具版本。
2. 对每个程序的 O2、O0、Os 记录 `.text` 大小、`kernel` 起止地址/长度、所属节、16/32 位指令数、未知字节数及 ELF SHA-256。
3. 独立核对 `readelf -sW`、`readelf -SW`、`objdump -d -M no-aliases,numeric` 与原始 ELF 字节；不能只读 sidecar。
4. 分别判定 R001、R002 为 verified、abstained 或 not_applicable，并记录证据定位。
5. 两份标注完成后才合并分歧；裁决记录必须保留原始意见和理由。

## 批次信息

| 字段 | 值 |
| --- | --- |
| 语料版本 | 0.1.0 |
| 语料状态 | frozen（机器门禁）；人工最终确认待完成 |
| 正式批次 | `/home/yyd/work/optipilot-m2-formal-final/evaluation-23d0fbc17db84a1d8379bbc0ca0d2ddf/` |
| 复核人 A | 待填写 |
| 复核人 B | 待填写 |
| 工具版本 | 待从正式批次填写 |

## 程序清单

| 程序 | 划分 | 家族 | 来源 | 源码 SHA-256 | A 状态 | B 状态 | 分歧/裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sum_u32 | development | sum_reduction | repository_authored_development | `f4182020c3d81881b86c8bfbb4e2c1e1cfcf3da49ba784ad6e473be5f8b4b2e6` | 待填写 | 待填写 | 待填写 |
| dot_i32 | development | dot_product | repository_authored_development | `4bcb7c93decb5c84ac23cb1b581b7c50f0bcfcdfc4d7f88883dd48cd565dcd1c` | 待填写 | 待填写 | 待填写 |
| threshold_count | development | threshold_filter | repository_authored_development | `1f2198a293e6692ecaff1788103d52c60f275fc402ed85b6512e76565cab4b63` | 待填写 | 待填写 | 待填写 |
| histogram_count | development | histogram | repository_authored_development | `accbd5f3c37e7d012e98c3b6b2bea6599501acb9fc9e5a2ebbad49240f23bdcd` | 待填写 | 待填写 | 待填写 |
| run_length | development | run_length | repository_authored_development | `d06a711ed165c126d6a86809aec95de96c8341e49fd6f8ccd21c26daa1ffe920` | 待填写 | 待填写 | 待填写 |
| rolling_hash | development | rolling_hash | repository_authored_development | `d6fc8dd2c59c392b6ff6e0f5264755ea7ebb5633e6985f07665bb7fc035e85eb` | 待填写 | 待填写 | 待填写 |
| xor_checksum | held_out | checksum | repository_authored_held_out | `3d67dda39483c4ad4f3389608d8acc53a7cd2ecf603204b231d27d9ded3af151` | 待填写 | 待填写 | 待填写 |
| lookup_switch | held_out | lookup_and_switch | repository_authored_held_out | `585cb3bbf613ae13689c84cdcd6e0a66e479d44aea796c6bf12e286af1dbded0` | 待填写 | 待填写 | 待填写 |
| call_chain | held_out | function_calls | repository_authored_held_out | `cc8a0b815a5ab45639ed7f3f02969f6bfdd5a07a19ca40b84eeb4ae3ba19c035` | 待填写 | 待填写 | 待填写 |
| state_machine | held_out | state_machine | repository_authored_held_out | `12aeb8bc8cba33cbdaa70875edd56fdf2811bd9154e195786bb2d2121b18a582` | 待填写 | 待填写 | 待填写 |
| fixed_point_filter | held_out | fixed_point_filter | repository_authored_held_out | `9f7965c0d205675f5d6a7327beae69efd9929100a000b3a386ce33366a694631` | 待填写 | 待填写 | 待填写 |
| bounded_parser | held_out | bounded_parser | repository_authored_held_out | `d18a69f43c0de2755297cc046f96efb4e041ac2a06243a957205065b0cce06c5` | 待填写 | 待填写 | 待填写 |

## 复核交付物

- `reviewer-sjs.json`、`reviewer-yyd.json`：分别提交的原始计数、证据路径、哈希和结论，不共同编辑同一份标注。
- `adjudication.md`：仅记录分歧、裁决依据和最终状态。
- 两位成员分别确认源码来源、许可证、数值范围和 oracle 生成方式。

填写完成后运行：

```sh
python -B scripts/validate_reviews.py \
  --corpus evaluation/corpus.json \
  --batch /path/to/evaluation-UUID/batch.json \
  --review-a reviewer-sjs.json --review-b reviewer-yyd.json \
  --adjudication adjudication.json
```

每份标注的 `reviewer_id` 使用真实成员账号，`independent_from` 必须包含另一位成员的账号。`review_date` 使用实际完成日期。不得用自动生成的计数文件代替成员独立判断或签署。

`evidence` 列表须分别引用被复核档位的原始 `program.elf`、`analysis/readelf-symbols.txt`、`analysis/readelf-sections.txt`、`analysis/objdump-kernel.txt`。可使用批次根目录、实验目录或档位目录内的相对路径，也可保留包含批次 ID 的原始绝对路径；定位说明可放在 `#` 或 `: ` 后。示例：

```json
[
  "experiments/exec-UUID/O2/program.elf#kernel",
  "experiments/exec-UUID/O2/analysis/readelf-symbols.txt#kernel",
  "experiments/exec-UUID/O2/analysis/readelf-sections.txt#.text",
  "experiments/exec-UUID/O2/analysis/objdump-kernel.txt#kernel"
]
```

证据包迁移到其他 Linux/WSL2 目录后，保留原始 `batch.json`，另生成仅改写 `result_path` 的迁移副本，将 `--batch` 指向批次根目录下的该副本。原始 `corpus.json`、artifact 清单和所有产物字节保持不变。标注中的原始绝对路径按批次 ID 映射到迁移后的同一档位，不能引用其他程序/档位文件。

校验器核对正式非 mock 批次、冻结语料快照、清单内文件哈希、双方独立性声明、12×3 覆盖、绝对函数边界、节号、未知字节、16/32 位计数以及 GNU 输出；裁决必须覆盖 36 对程序/档位各一次。缺失引用、重复裁决或档位互换均失败。校验器不会修改原始标注、选择规则标签或替成员处理分歧。

成功输出的 `declared_signoffs_checked=true` 只表示双方账号出现在裁决声明中，`human_identity_verified=false` 明确表示脚本没有验证实际人员身份；`acceptance_ready=false` 保持不变。成员身份、独立完成过程、来源与许可证、最终报告和材料仍由团队复核，不能把 JSON 中出现两个账号视为双人复核已真实完成。

当前正式批次机器核验已通过；在这些文件完成前，`acceptance_ready` 必须保持 false，报告不得写成一般程序的优化收益。
