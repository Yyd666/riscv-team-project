# 技术与实验基线 0.1.0

编译与执行配置以 `config/baseline.json` 为准，正确性语料以 `benchmarks/manifest.json` 为准。配置、清单及源码的 SHA-256 应写入实验结果。本版本定义配置与语料基线，实测结果单独归档。

## 固定目标

| 项目 | 约定 |
| --- | --- |
| 后端参考环境 | Ubuntu 24.04，原生 Linux 或 WSL2；业务 Python 3.12 |
| 目标架构 | RV64GC，小端 Linux 用户态，ABI LP64D |
| 编译器 | GNU Linux 交叉工具链 `riscv64-linux-gnu-gcc` |
| 分析器 | 同前缀 GNU `objdump`、`readelf`、`size` |
| 执行器 | `qemu-riscv64 -cpu rv64`，每份报告保存实际版本 |
| 编译档位 | `O0`、`O2`、`Os`；请求只传这些 ID |
| 正确性 | 该样例全部登记输入的 stdout、stderr、退出码均符合清单 |
| 推荐目标 | 通过正确性的方案中 `.text` 字节数最小 |

`-march` 与 `-mabi` 显式固定，避免编译器默认值随环境改变。[GCC RISC-V 参数](https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html)

首个实测实验须归档 `gcc -v`、binutils/QEMU 版本、相关已安装包版本、宿主系统及内核、Python 和 libc 信息。Ubuntu 软件包更新后，应按实际版本记录环境差异。镜像或软件包版本锁定方案须另行记录决策；当前复现范围限于命令、输入与工具来源的可追溯性，不包含跨机器二进制逐字节一致性。

## 手动基线验证

以下命令在 Ubuntu / WSL 的仓库根目录执行，用于工具链安装及单用例验证。执行结果以 `docs/STATUS.md` 和实验记录为准。

```sh
sudo apt-get update
sudo apt-get install gcc-riscv64-linux-gnu binutils-riscv64-linux-gnu qemu-user
mkdir -p artifacts/manual-sum/O0
riscv64-linux-gnu-gcc --version
riscv64-linux-gnu-gcc -v
riscv64-linux-gnu-objdump --version
qemu-riscv64 --version
riscv64-linux-gnu-gcc -std=c11 -Wall -Wextra -Werror -static -fno-pie -no-pie -march=rv64gc -mabi=lp64d -O0 benchmarks/sum_u32/main.c -o artifacts/manual-sum/O0/program.elf
riscv64-linux-gnu-readelf -h -A artifacts/manual-sum/O0/program.elf
timeout 3s qemu-riscv64 -cpu rv64 artifacts/manual-sum/O0/program.elf < benchmarks/sum_u32/cases/mixed.in > artifacts/manual-sum/O0/mixed.out 2> artifacts/manual-sum/O0/mixed.err
diff -u benchmarks/sum_u32/cases/mixed.out artifacts/manual-sum/O0/mixed.out
test ! -s artifacts/manual-sum/O0/mixed.err
riscv64-linux-gnu-size -A artifacts/manual-sum/O0/program.elf
riscv64-linux-gnu-objdump -d -M no-aliases,numeric --disassemble=kernel artifacts/manual-sum/O0/program.elf > artifacts/manual-sum/O0/kernel.asm
```

每条命令执行后均应检查退出状态，发生超时或编译失败时停止，并排除旧产物。上述步骤覆盖单个样例的一组输入；完整基线验证须覆盖全部语料、全部输入和三个编译档位，并保存命令、版本与哈希。后端执行器还须实现输出限额及进程清理。

## 正确性校验规则

输入和预期输出都是 UTF-8、LF 文件，按原始字节比较，不 `strip()`，不忽略空格或末尾换行；默认退出码 0、stderr 为空。清单内的文件是独立预期值，不是从 `-O0` 输出复制得到。

后端为编译、分析和运行子进程显式设置 `LC_ALL=C`、`LANG=C`，报告记录实际生效的 locale，避免工具输出格式随宿主语言变化。

`sum_u32` 使用明确的无符号 32 位模加法；`dot_i32` 将乘法提升为有符号 64 位，输入限制保证不溢出；`threshold_count` 统计大于等于阈值的元素。每个样例有空输入集合、混合值、边界/特殊值共三例。初始共 3 个程序、9 个用例。

初始用例用于验证登记输入下的输出正确性和处理流程。语义等价性及性能评估需另设验证方案；测试点、数据规模、随机种子和独立评估集应单独版本化。

## 指标定义

| JSON 字段 | 定义 | 使用限制 |
| --- | --- | --- |
| `elf_file_bytes` | ELF 整个文件的字节数 | 仅表示文件大小 |
| `text_section_bytes` | `size -A` 中名称恰为 `.text` 的节大小，含静态链接库 | 用于静态代码体积比较 |
| `kernel_code_bytes` | ELF 符号 `kernel` 对应函数的机器码字节数 | 统计范围限定为该函数 |
| `kernel_static_instruction_count` | 该符号反汇编内实际机器指令条数 | 仅用于静态指令组成分析 |
| `kernel_compressed_instruction_count` | 其中编码长度为 2 字节的条数 | 依据机器编码长度判定 |
| `wall_time_ms` | 单次 QEMU 进程的宿主单调时钟耗时 | 仅用于执行诊断 |
| `dynamic_instruction_count` | 首版固定为 `null` | 待接入独立的动态指令统计 |
| `target_cycles` | 首版固定为 `null` | 待接入目标周期测量 |

反汇编使用 `-M no-aliases,numeric`，按实际编码及函数边界解析，排除标签、注释与数据行。符号缺失、解析失败或不满足 ISA 时返回 `analysis_error`。`kernel` 指标仅统计该函数，源码保留 `noinline` 属性以便定位。

保留原始反汇编、节表、符号表和命令。缺失指标用 `null`，不输出推测数字；失败方案不参与推荐。

## 比较与推荐

`-O0` 仅作为易观察的教学对照。正式比较至少列出 `-O2`、`-Os`。所有档位共用同一源码、输入、工具版本、ISA、ABI 和公共参数，不使用 LTO、PGO、`fast-math`、RVV 或未登记选项。

推荐范围限定为通过全部用例的方案，目标为 `.text` 字节数最小；并列时按 `O2`、`Os`、`O0` 顺序选择。仅有 `O0` 通过时仍可推荐，但结果须列明其他方案的失败原因。无通过方案时 `selection` 为 `null`。

推荐目标是完整 `.text`，函数指标用于单独诊断，不能替代排序目标。新增归因的 R001/R002 定义见 [ATTRIBUTION_DESIGN.md](ATTRIBUTION_DESIGN.md)。原编译配置与实验指标保持原版本，归因结果通过独立文件关联。

体积变化率按 `(候选字节数 - O2 字节数) / O2 字节数 × 100%` 计算，负数表示减少；O2 缺失、失败或分母为零时显示“不可比较”。该推荐属于固定候选配置选择，技术说明应与后续自研优化算法区分。

单次宿主耗时仅用于超时和执行异常诊断。后续引入性能测时，须规定预热、重复次数、统计量、宿主负载、I/O 与仿真开销的处理方法；目标周期及硬件实验单独设计。

## 结果留存

每次实验在 `artifacts/<experiment_id>/` 保存：配置原件、源码与输入哈希清单、环境清单、各方案编译日志、ELF、汇编、原始 stdout/stderr、`result.json`、`report.md`。实验 ID 由后端生成，不复用旧目录。JSON 以 `contracts/experiment.schema.json` 为准。

`artifacts/` 默认排除在 Git 跟踪范围之外。实验数据通过 PR 附件、CI artifact 或压缩包共享，并提供 SHA-256。共享前检查个人路径及凭据，保留可复核的原始数据。

实现归因后按配置对增加 `attribution/O2-<candidate>/attribution.json` 与其证据产物。环境复现、独立评估和统计分母遵循 [EVALUATION.md](EVALUATION.md)。文件哈希按原始字节计算，换行变化也会改变标识；不得静默规范化后冒用旧哈希。
