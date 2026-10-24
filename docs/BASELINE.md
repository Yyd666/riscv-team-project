# 技术与实验基线 0.1.0

机器配置以 `config/baseline.json` 为准；正确性语料以 `benchmarks/manifest.json` 为准。二者与源码均计算 SHA-256，写进真实实验结果。当前这是配置与语料基线，尚不是实测性能基线。

## 固定目标

| 项目 | 约定 |
| --- | --- |
| 后端参考环境 | Ubuntu 24.04，原生 Linux 或 WSL2；业务 Python 3.12 |
| 目标架构 | RV64GC，小端 Linux 用户态，ABI LP64D |
| 编译器 | `riscv64-linux-gnu-gcc`，不是裸机 `unknown-elf` 工具链 |
| 分析器 | 同前缀 GNU `objdump`、`readelf`、`size` |
| 执行器 | `qemu-riscv64 -cpu rv64`，每份报告保存实际版本 |
| 编译档位 | `O0`、`O2`、`Os`；请求只传这些 ID |
| 正确性 | 该样例全部登记输入的 stdout、stderr、退出码均符合清单 |
| 推荐目标 | 通过正确性的方案中 `.text` 字节数最小 |

`-march` 与 `-mabi` 显式固定，避免编译器默认值随环境改变。[GCC RISC-V 参数](https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html)

当前不把 Ubuntu 软件包更新后的工具链视为完全相同环境。首个真实实验须归档 `gcc -v`、binutils/QEMU 版本、相关已安装包版本、宿主系统及内核、Python 和 libc 信息；后续固定镜像/包版本的工作需另记决策。未提交环境锁定文件之前，只有“命令和来源可追溯”，不保证跨机器二进制逐字节相同。

## 手动建立第一个真实基线

以下在 Ubuntu / WSL 的仓库根目录执行，是接手者主动运行的操作；当前提交没有执行这些安装或 RISC-V 构建：

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

应当检查每条命令的退出状态；超时或编译失败时停止，不继续拿旧文件作新结果。上述只演示一个样例的一条输入，不能据此填写整个验收清单。完整真实基线需所有语料 × 所有输入 × 三个档位，并保存命令/版本/哈希。手动命令也不替代后端的输出限额和进程清理实现。

## 正确性口径

输入和预期输出都是 UTF-8、LF 文件，按原始字节比较，不 `strip()`，不忽略空格或末尾换行；默认退出码 0、stderr 为空。清单内的文件是独立预期值，不是从 `-O0` 输出复制得到。

后端为编译、分析和运行子进程显式设置 `LC_ALL=C`、`LANG=C`，报告记录实际生效的 locale，避免工具输出格式随宿主语言变化。

`sum_u32` 使用明确的无符号 32 位模加法；`dot_i32` 将乘法提升为有符号 64 位，输入限制保证不溢出；`threshold_count` 统计大于等于阈值的元素。每个样例有空输入集合、混合值、边界/特殊值共三例。初始共 3 个程序、9 个用例。

这些小输入用于正确性和流水线检查，不能证明对所有 C 程序语义等价，也不足以形成性能结论。测试点、规模、随机种子和独立评估集扩展应单独版本化。

## 指标定义

| JSON 字段 | 定义 | 禁止推论 |
| --- | --- | --- |
| `elf_file_bytes` | ELF 整个文件的字节数 | 不能直接当作代码段大小 |
| `text_section_bytes` | `size -A` 中名称恰为 `.text` 的节大小，含静态链接库 | 不能直接当作程序执行工作量 |
| `kernel_code_bytes` | ELF 符号 `kernel` 对应函数的机器码字节数 | 不能冒充整个程序体积 |
| `kernel_static_instruction_count` | 该符号反汇编内实际机器指令条数 | 不等于动态执行条数 |
| `kernel_compressed_instruction_count` | 其中编码长度 2 字节的条数 | 助记符行数或别名不足以判定 |
| `wall_time_ms` | 单次 QEMU 进程的宿主单调时钟耗时 | 不是目标处理器运行时间或加速比 |
| `dynamic_instruction_count` | 首版固定为 `null` | 不能用静态计数、TB 日志条数填充 |
| `target_cycles` | 首版固定为 `null` | 没有测量时不能填 0 或估算周期 |

反汇编使用 `-M no-aliases,numeric`，按真实编码及函数边界解析，排除标签、注释与数据行；符号缺失、无法解析或不满足 ISA 时返回 `analysis_error`。不要把整个静态链接 libc 的指令当作 `kernel`。源代码保留 `noinline`，确保目标函数可定位。

保留原始反汇编、节表、符号表和命令。缺失指标用 `null`，不输出推测数字；失败方案不参与推荐。

## 比较与推荐

`-O0` 仅作为易观察的教学对照。正式比较至少列出 `-O2`、`-Os`。所有档位共用同一源码、输入、工具版本、ISA、ABI 和公共参数，不使用 LTO、PGO、`fast-math`、RVV 或未登记选项。

首版只选择体积最小的通过方案；并列时按配置的 `O2`、`Os`、`O0` 顺序选择。即使只剩 `O0` 通过，也要在结果说明其他失败方案，不声称优化已成功。无通过方案时 `selection` 为 `null`。

体积变化率按 `(候选字节数 - O2 字节数) / O2 字节数 × 100%`，负数表示减少；O2 缺失、失败或分母为零时显示“不可比较”。推荐是固定候选中的选择，不等于自研编译优化算法。

单次宿主耗时只用于发现超时或执行异常；首版不据此排名或生成速度收益。以后引入测时实验需明确预热、重复次数、统计量、主机负载、I/O 与仿真开销；真实周期或硬件结论另行设计。

## 结果留存

每次实验在 `artifacts/<experiment_id>/` 保存：配置原件、源码与输入哈希清单、环境清单、各方案编译日志、ELF、汇编、原始 stdout/stderr、`result.json`、`report.md`。实验 ID 由后端生成，不复用旧目录。JSON 以 `contracts/experiment.schema.json` 为准。

`artifacts/` 默认不入 Git。需要分享证据时在 PR 附可访问的 CI artifact 或压缩包并给出 SHA-256；先检查不含个人路径或凭据。不要提交大二进制，也不要只有截图没有原始数据。
